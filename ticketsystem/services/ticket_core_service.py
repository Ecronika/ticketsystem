"""Core ticket CRUD operations, notifications, comments, and status changes.

Extracted from the monolithic ``ticket_service.py`` to keep each service
module focused on a single responsibility.
"""

import logging
import os
import re
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from dateutil.relativedelta import relativedelta
from flask import current_app

from enums import TicketPriority, TicketStatus
from extensions import db
from models import (
    Attachment,
    ChecklistItem,
    Comment,
    Notification,
    Tag,
    Ticket,
    TicketContact,
    Worker,
)
from utils import get_utc_now

from ._helpers import db_transaction
from ._ticket_helpers import (
    ContactInfo,
    _ALLOWED_EXTENSIONS,
    _OPEN_STATUSES,
    _RECURRENCE_INCREMENTS,
    _format_date,
    _get_ticket_or_none,
    _get_ticket_or_raise,
)
from .email_service import EmailService

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-private helpers
# ---------------------------------------------------------------------------

def _build_ticket(
    title: str,
    description: Optional[str],
    priority: Any,
    assigned_to_id: Optional[int],
    assigned_team_id: Optional[int],
    is_confidential: bool,
    recurrence_rule: Optional[str],
    due_date: Optional[date],
    order_reference: Optional[str],
    reminder_date: Optional[datetime],
    contact: Optional[ContactInfo] = None,
) -> Ticket:
    """Construct a Ticket ORM object with satellite records."""
    ticket = Ticket(
        title=title,
        description=description,
        priority=int(priority.value if hasattr(priority, "value") else priority),
        status=TicketStatus.OFFEN.value,
        assigned_to_id=assigned_to_id,
        assigned_team_id=assigned_team_id,
        is_confidential=is_confidential,
        due_date=due_date,
        order_reference=order_reference,
        reminder_date=reminder_date,
    )
    if contact:
        c = ticket.ensure_contact()
        c.name = contact.name
        c.phone = contact.phone
        c.email = contact.email
        c.channel = contact.channel
        c.callback_requested = contact.callback_requested
        c.callback_due = contact.callback_due
    if recurrence_rule:
        increment = _RECURRENCE_INCREMENTS.get(
            recurrence_rule.lower(), relativedelta(months=1)
        )
        ticket.ensure_recurrence(
            rule=recurrence_rule,
            next_date=get_utc_now() + increment,
        )
    return ticket


def _attach_tags(ticket: Ticket, tags: Optional[List[str]]) -> None:
    """Resolve or create tags and attach them to the ticket."""
    if not tags:
        return
    for tag_name in tags:
        tag = Tag.query.filter_by(name=tag_name).first()
        if not tag:
            tag = Tag(name=tag_name)
            db.session.add(tag)
        ticket.tags.append(tag)


def _save_attachments(
    ticket_id: int,
    attachments: list,
) -> None:
    """Save uploaded files and create ``Attachment`` records."""
    from extensions import Config

    data_dir = current_app.config.get("DATA_DIR", Config.get_data_dir())
    attachments_dir = os.path.join(data_dir, "attachments")
    os.makedirs(attachments_dir, exist_ok=True)

    if "pending_files" not in db.session.info:
        db.session.info["pending_files"] = []

    for file_obj in attachments:
        if not file_obj.filename:
            continue
        ext = (
            file_obj.filename.rsplit(".", 1)[-1].lower()
            if "." in file_obj.filename
            else ""
        )
        if ext not in _ALLOWED_EXTENSIONS:
            current_app.logger.warning(
                "Upload blocked: Illegal extension '%s' for file %s",
                ext, file_obj.filename,
            )
            continue
        try:
            mime_type = file_obj.mimetype or "application/octet-stream"
            new_filename = f"ticket_{ticket_id}_{uuid.uuid4().hex[:8]}.{ext}"
            filepath = os.path.join(attachments_dir, new_filename)
            file_obj.save(filepath)
            db.session.info["pending_files"].append(filepath)
            attachment = Attachment(
                ticket_id=ticket_id,
                path=new_filename,
                filename=file_obj.filename,
                mime_type=mime_type,
            )
            db.session.add(attachment)
            current_app.logger.info(
                "Saved attachment %s for ticket %s", new_filename, ticket_id
            )
        except OSError as err:
            current_app.logger.error(
                "Error saving attachment %s: %s", file_obj.filename, err
            )


def _add_creation_comment(
    ticket_id: int,
    author_name: str,
    author_id: Optional[int],
    description: Optional[str],
    path_logs: List[str],
) -> None:
    """Add the initial 'Ticket erstellt' comment."""
    text = (
        f"Ticket erstellt von {author_name}. Beschreibung: {description}"
        if description
        else f"Ticket erstellt von {author_name}."
    )
    if path_logs:
        text += "\nDelegation:\n- " + "\n- ".join(path_logs)
    db.session.add(Comment(
        ticket_id=ticket_id,
        author=author_name,
        author_id=author_id,
        text=text,
        is_system_event=True,
        event_type="TICKET_CREATED",
    ))


def _process_mentions(
    ticket_id: int, text: str, author_name: str
) -> None:
    """Detect @mentions in text and create notifications + emails."""
    mentions = set(re.findall(r"@(\w+)", text))
    for mention in mentions:
        if mention.lower() == author_name.lower():
            continue
        mentioned = Worker.query.filter(Worker.name.ilike(mention)).first()
        if not mentioned:
            continue
        msg = f"{author_name} hat Sie in Ticket #{ticket_id} erwähnt."
        link = f"/ticket/{ticket_id}"
        TicketCoreService.create_notification(
            user_id=mentioned.id,
            message=msg,
            link=link,
        )
        if mentioned.email and mentioned.email_notifications_enabled:
            EmailService.send_mention(
                mentioned.name, ticket_id, author_name,
                recipient_email=mentioned.email,
            )
        # WebPush (fire-and-forget; errors are logged but not raised)
        try:
            from services.push_service import send_push_to_worker
            send_push_to_worker(mentioned.id, "Neue Erwähnung", msg, link)
        except Exception as _push_exc:
            current_app.logger.debug("WebPush mention failed: %s", _push_exc)


def _collect_meta_changes(
    ticket: Ticket,
    title: str,
    priority: Optional[int],
    due_date: Optional[datetime],
    order_reference: Optional[str],
    reminder_date: Optional[datetime],
) -> List[str]:
    """Compare old vs new metadata and return change descriptions."""
    changes: List[str] = []
    if ticket.title != title:
        changes.append(f"Titel: '{ticket.title}' -> '{title}'")
    if priority is not None and int(ticket.priority) != int(priority):
        changes.append(f"Priorität: {ticket.priority} -> {priority}")
    if ticket.due_date != due_date:
        changes.append(
            f"Fälligkeit: {_format_date(ticket.due_date)} "
            f"-> {_format_date(due_date)}"
        )
    if ticket.order_reference != order_reference:
        changes.append(
            f"Auftragsreferenz: '{ticket.order_reference or 'Keine'}' "
            f"-> '{order_reference or 'Keine'}'"
        )
    if ticket.reminder_date != reminder_date:
        changes.append(
            f"Wiedervorlage: {_format_date(ticket.reminder_date, 'Keine')} "
            f"-> {_format_date(reminder_date, 'Keine')}"
        )
    return changes


def _notify_meta_change(
    ticket: Ticket,
    author_name: str,
    author_id: Optional[int],
    changes: List[str],
) -> None:
    """Send in-app notifications to assigned worker when ticket meta changes."""
    recipients: List[int] = []
    # Notify assigned worker (if not the editor)
    if ticket.assigned_to_id and ticket.assigned_to_id != author_id:
        recipients.append(ticket.assigned_to_id)

    change_text = ", ".join(changes)
    for wid in recipients:
        try:
            db.session.add(Notification(
                user_id=wid,
                message=(
                    f"{author_name} hat Ticket #{ticket.id} bearbeitet: "
                    f"{change_text[:200]}"
                ),
                link=f"/ticket/{ticket.id}",
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()

    # Also send email notification to assigned worker
    if ticket.assigned_to_id and ticket.assigned_to_id != author_id:
        worker = db.session.get(Worker, ticket.assigned_to_id)
        if worker and worker.email and worker.email_notifications_enabled:
            try:
                EmailService.send_meta_change(
                    worker.name, ticket.id, author_name,
                    changes, worker.email,
                )
            except Exception:
                pass


def _sync_tags(ticket: Ticket, tags: List[str]) -> Optional[str]:
    """Synchronise ticket tags and return a change description or ``None``."""
    old_tags = [t.name for t in ticket.tags]
    new_tags = [t.strip() for t in tags if t.strip()]
    if set(old_tags) == set(new_tags):
        return None
    ticket.tags = []
    for tag_name in new_tags:
        tag = Tag.query.filter_by(name=tag_name).first()
        if not tag:
            tag = Tag(name=tag_name)
            db.session.add(tag)
        ticket.tags.append(tag)
    return (
        f"Tags: {', '.join(old_tags) or 'Keine'} "
        f"-> {', '.join(new_tags) or 'Keine'}"
    )


# ---------------------------------------------------------------------------
# Main Service Class
# ---------------------------------------------------------------------------

class TicketCoreService:
    """Core ticket operations: CRUD, notifications, comments, status."""

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    @staticmethod
    @db_transaction
    def create_ticket(
        title: str,
        description: Optional[str] = None,
        priority: Any = TicketPriority.MITTEL,
        author_name: str = "System",
        author_id: Optional[int] = None,
        assigned_to_id: Optional[int] = None,
        assigned_team_id: Optional[int] = None,
        due_date: Optional[datetime] = None,
        tags: Optional[List[str]] = None,
        attachments: Optional[list] = None,
        order_reference: Optional[str] = None,
        reminder_date: Optional[datetime] = None,
        is_confidential: bool = False,
        recurrence_rule: Optional[str] = None,
        checklist_template_id: Optional[int] = None,
        contact: Optional[ContactInfo] = None,
        commit: bool = True,
    ) -> Ticket:
        """Create a new ticket with an initial audit comment.

        Args:
            commit: When ``True`` (default), commits immediately.
                    Pass ``False`` in batch / scheduler contexts.
        """
        from services.ticket_assignment_service import TicketAssignmentService
        from services.checklist_service import ChecklistService

        path_logs: List[str] = []
        if assigned_to_id:
            assigned_to_id, path_logs = TicketAssignmentService._resolve_delegation(
                assigned_to_id
            )

        ticket = _build_ticket(
            title, description, priority, assigned_to_id,
            assigned_team_id, is_confidential, recurrence_rule,
            due_date, order_reference, reminder_date, contact,
        )
        _attach_tags(ticket, tags)
        db.session.add(ticket)
        db.session.flush()

        if checklist_template_id:
            ChecklistService.apply_checklist_template(
                ticket.id, checklist_template_id, commit=False
            )

        _add_creation_comment(
            ticket.id, author_name, author_id, description, path_logs
        )

        if attachments:
            _save_attachments(ticket.id, attachments)

        if commit:
            db.session.commit()
        else:
            db.session.flush()

        return ticket

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    @staticmethod
    @db_transaction
    def update_ticket(
        ticket_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        priority: Optional[int] = None,
        due_date: Optional[datetime] = None,
        author_name: str = "System",
        author_id: Optional[int] = None,
    ) -> Optional[Ticket]:
        """Update ticket basic details."""
        ticket = _get_ticket_or_none(ticket_id)
        if not ticket:
            return None

        changes: List[str] = []
        if title and ticket.title != title:
            changes.append(f"Titel: {ticket.title} -> {title}")
            ticket.title = title
        if description and ticket.description != description:
            changes.append("Beschreibung aktualisiert")
            ticket.description = description
        if priority and ticket.priority != int(priority):
            changes.append(f"Priorität: {ticket.priority} -> {priority}")
            ticket.priority = int(priority)
        if due_date is not None and ticket.due_date != due_date:
            changes.append(
                f"Fälligkeit: {_format_date(ticket.due_date)} "
                f"-> {_format_date(due_date)}"
            )
            ticket.due_date = due_date

        if changes:
            ticket.updated_at = get_utc_now()
            comment = Comment(
                ticket_id=ticket.id,
                author=author_name,
                author_id=author_id,
                text=f"Ticket aktualisiert: {', '.join(changes)}",
                is_system_event=True,
                event_type="TICKET_UPDATE",
            )
            db.session.add(comment)
            db.session.commit()

        return ticket

    # ------------------------------------------------------------------
    # Delete (soft)
    # ------------------------------------------------------------------

    @staticmethod
    @db_transaction
    def delete_ticket(
        ticket_id: int,
        author_name: str = "System",
        author_id: Optional[int] = None,
    ) -> bool:
        """Soft-delete a ticket."""
        ticket = _get_ticket_or_none(ticket_id)
        if not ticket:
            return False

        ticket.is_deleted = True
        ticket.updated_at = get_utc_now()
        comment = Comment(
            ticket_id=ticket.id,
            author=author_name,
            author_id=author_id,
            text="Ticket wurde vom System archiviert.",
            is_system_event=True,
            event_type="TICKET_DELETED",
        )
        db.session.add(comment)
        db.session.commit()
        return True

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    @staticmethod
    def create_notification(
        user_id: int, message: str, link: Optional[str] = None
    ) -> None:
        """Create an in-app notification (best-effort)."""
        try:
            db.session.add(
                Notification(user_id=user_id, message=message, link=link)
            )
        except Exception as exc:
            current_app.logger.error(
                "Failed to create notification: %s", exc
            )

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------

    @staticmethod
    @db_transaction
    def add_comment(
        ticket_id: int,
        author_name: str,
        author_id: Optional[int],
        text: str,
    ) -> Comment:
        """Add a comment and process ``@mentions``."""
        comment = Comment(
            ticket_id=ticket_id,
            author=author_name,
            author_id=author_id,
            text=text,
            is_system_event=False,
        )
        db.session.add(comment)

        ticket = db.session.get(Ticket, ticket_id)
        if ticket:
            ticket.updated_at = get_utc_now()

        _process_mentions(ticket_id, text, author_name)
        db.session.commit()
        return comment

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @staticmethod
    @db_transaction
    def update_status(
        ticket_id: int,
        status: Any,
        author_name: str = "System",
        author_id: Optional[int] = None,
        commit: bool = True,
    ) -> Optional[Ticket]:
        """Update ticket status and add a system comment."""
        ticket = _get_ticket_or_none(ticket_id)
        if not ticket:
            return None

        old_status = ticket.status
        new_status = status.value if hasattr(status, "value") else status

        if old_status != new_status:
            ticket.status = new_status
            ticket.updated_at = get_utc_now()
            comment = Comment(
                ticket_id=ticket_id,
                author=author_name,
                author_id=author_id,
                text=f"Status geändert: {old_status} -> {new_status}",
                is_system_event=True,
                event_type="STATUS_CHANGE",
            )
            db.session.add(comment)
            if commit:
                db.session.commit()
            else:
                db.session.flush()

        return ticket

    # ------------------------------------------------------------------
    # Ticket meta update
    # ------------------------------------------------------------------

    @staticmethod
    @db_transaction
    def update_ticket_meta(
        ticket_id: int,
        title: str,
        priority: Optional[int],
        author_name: str,
        author_id: Optional[int],
        due_date: Optional[date] = None,
        order_reference: Optional[str] = None,
        reminder_date: Optional[datetime] = None,
        tags: Optional[List[str]] = None,
        recurrence_rule: Optional[str] = None,
    ) -> Ticket:
        """Update ticket metadata with an audit trail."""
        ticket = _get_ticket_or_raise(ticket_id)

        changes = _collect_meta_changes(
            ticket, title, priority, due_date,
            order_reference, reminder_date,
        )
        ticket.title = title
        if priority is not None:
            ticket.priority = int(priority)
        ticket.due_date = due_date
        ticket.order_reference = order_reference
        if ticket.reminder_date != reminder_date:
            ticket.reminder_notified_at = None
        ticket.reminder_date = reminder_date
        ticket.updated_at = get_utc_now()

        old_rule = ticket.recurrence.rule if ticket.recurrence else None
        new_rule = recurrence_rule or None
        if old_rule != new_rule:
            old_label = (old_rule or "Einmalig").capitalize()
            new_label = (new_rule or "Einmalig").capitalize()
            changes.append(f"Serie: {old_label} -> {new_label}")
            if new_rule:
                increment = _RECURRENCE_INCREMENTS.get(
                    new_rule.lower(), relativedelta(months=1)
                )
                rec = ticket.ensure_recurrence(rule=new_rule)
                rec.rule = new_rule
                rec.next_date = get_utc_now() + increment
            else:
                ticket.recurrence = None

        if tags is not None:
            tag_changes = _sync_tags(ticket, tags)
            if tag_changes:
                changes.append(tag_changes)

        if changes:
            db.session.add(Comment(
                ticket_id=ticket.id,
                author=author_name,
                author_id=author_id,
                text="Metadaten geändert: " + ", ".join(changes),
                is_system_event=True,
                event_type="META_UPDATE",
            ))
            db.session.commit()

            # Notify assigned worker and watchers about changes
            _notify_meta_change(ticket, author_name, author_id, changes)

        return ticket
