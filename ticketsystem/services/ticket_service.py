"""Service layer for Ticket management.

Provides CRUD operations, status transitions, assignment logic,
approval workflow, checklist handling, and dashboard queries.
"""

import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from dateutil.relativedelta import relativedelta

from flask import current_app
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload, selectinload

from enums import ApprovalStatus, TicketPriority, TicketStatus, WorkerRole
from extensions import db
from models import (
    Attachment,
    ChecklistItem,
    Comment,
    Notification,
    Tag,
    Ticket,
    Worker,
)
from utils import get_utc_now

from .email_service import EmailService

_logger = logging.getLogger(__name__)

_ELEVATED_ROLES = frozenset({
    WorkerRole.ADMIN.value,
    WorkerRole.HR.value,
    WorkerRole.MANAGEMENT.value,
})

_ALLOWED_EXTENSIONS = frozenset({
    "png", "jpg", "jpeg", "gif", "pdf",
    "doc", "docx", "xls", "xlsx", "txt",
})

_OPEN_STATUSES = [
    TicketStatus.OFFEN.value,
    TicketStatus.IN_BEARBEITUNG.value,
    TicketStatus.WARTET.value,
]


# ---------------------------------------------------------------------------
# Urgency scoring (module-level for reuse)
# ---------------------------------------------------------------------------

def _urgency_score(ticket: Ticket, now: Optional[datetime] = None) -> int:
    """Combined urgency value.  Lower score = more urgent."""
    if now is None:
        now = get_utc_now()
    prio = ticket.priority
    if ticket.due_date is None:
        return 500 + prio * 100
    due = ticket.due_date
    if due.tzinfo is not None:
        due = due.astimezone(timezone.utc).replace(tzinfo=None)
    days_left = (due.date() - now.date()).days
    if days_left < 0:
        return max(0, 50 + days_left) + prio * 5
    if days_left == 0:
        return 150 + prio * 5
    if days_left <= 7:
        return 200 + days_left * 10 + prio * 5
    return 300 + min(100, days_left) + prio * 20


# ---------------------------------------------------------------------------
# Workload helpers (extracted from nested functions)
# ---------------------------------------------------------------------------

def _is_critical_ticket(ticket: Ticket, week_end: date) -> bool:
    """Return ``True`` if a ticket requires immediate attention.

    Critical means: high priority OR overdue OR due within the current
    calendar week.  'wartet' tickets are never critical (consciously parked).
    """
    if ticket.status == TicketStatus.WARTET.value:
        return False
    if ticket.priority == TicketPriority.HOCH.value:
        return True
    if ticket.due_date:
        due = ticket.due_date.date() if hasattr(ticket.due_date, "date") else ticket.due_date
        if due <= week_end:
            return True
    return False


def _workload_sort_key(ticket: Ticket, today: date) -> Tuple[int, int]:
    """Sort key: overdue first, then by priority."""
    if ticket.due_date:
        due = ticket.due_date.date() if hasattr(ticket.due_date, "date") else ticket.due_date
        days_left = (due - today).days
    else:
        days_left = 999
    return (days_left, ticket.priority)


# ---------------------------------------------------------------------------
# Date formatting helper (replaces inline lambdas)
# ---------------------------------------------------------------------------

def _format_date(dt: Optional[datetime], fallback: str = "Keines") -> str:
    """Format a datetime for audit log entries."""
    return dt.strftime("%d.%m.%Y") if dt else fallback


# ---------------------------------------------------------------------------
# Confidential-filter builder (DRY across dashboard queries)
# ---------------------------------------------------------------------------

def _confidential_filter(
    worker_id: int,
    team_ids: Optional[List[int]],
) -> list:
    """Build SQLAlchemy OR-clauses for confidential ticket visibility."""
    author_sub = (
        db.session.query(Comment.ticket_id)
        .filter(
            Comment.event_type == "TICKET_CREATED",
            Comment.author_id == worker_id,
        )
        .subquery()
    )
    clauses = [
        Ticket.is_confidential == False,  # noqa: E712
        Ticket.id.in_(author_sub),
        Ticket.assigned_to_id == worker_id,
        Ticket.checklists.any(ChecklistItem.assigned_to_id == worker_id),
    ]
    if team_ids:
        clauses.append(Ticket.assigned_team_id.in_(team_ids))
        clauses.append(
            Ticket.checklists.any(ChecklistItem.assigned_team_id.in_(team_ids))
        )
    return clauses


def _team_clauses(team_ids: Optional[List[int]]) -> list:
    """Build team-based OR-clauses for ticket assignment filters."""
    if not team_ids:
        return []
    return [
        Ticket.assigned_team_id.in_(team_ids),
        Ticket.checklists.any(
            db.and_(
                ChecklistItem.assigned_team_id.in_(team_ids),
                ChecklistItem.is_completed == False,  # noqa: E712
            )
        ),
    ]


# ---------------------------------------------------------------------------
# Attachment handling (extracted from create_ticket)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# OOO admin notification (extracted from assign_ticket)
# ---------------------------------------------------------------------------

def _notify_admins_ooo_exhausted(
    ticket_id: int, author_id: Optional[int], path_logs: List[str]
) -> None:
    """Notify all admins when the OOO delegation chain is exhausted."""
    ooo_exhausted = (
        path_logs
        and any("kein Vertreter" in log or "Zirkuläre" in log for log in path_logs)
    )
    if not ooo_exhausted:
        return
    try:
        admins = Worker.query.filter_by(is_active=True, role="admin").all()
        for admin in admins:
            if admin.id != author_id:
                TicketService.create_notification(
                    user_id=admin.id,
                    message=(
                        f"Ticket #{ticket_id} konnte nicht zugewiesen werden "
                        "(OOO-Kette erschöpft). Manuelle Zuweisung erforderlich."
                    ),
                    link=f"/ticket/{ticket_id}",
                )
    except Exception as exc:
        current_app.logger.warning(
            "Admin OOO notification failed: %s", exc
        )



# ---------------------------------------------------------------------------
# Main Service Class
# ---------------------------------------------------------------------------

class TicketService:
    """Service for ticket and comment operations."""

    _urgency_score = staticmethod(_urgency_score)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    @staticmethod
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
        contact_name: Optional[str] = None,
        contact_phone: Optional[str] = None,
        contact_email: Optional[str] = None,
        contact_channel: Optional[str] = None,
        callback_requested: bool = False,
        callback_due: Optional[datetime] = None,
        commit: bool = True,
    ) -> Ticket:
        """Create a new ticket with an initial audit comment.

        Args:
            commit: When ``True`` (default), commits immediately.
                    Pass ``False`` in batch / scheduler contexts.
        """
        try:
            path_logs: List[str] = []
            if assigned_to_id:
                assigned_to_id, path_logs = TicketService._resolve_delegation(
                    assigned_to_id
                )

            ticket = _build_ticket(
                title, description, priority, assigned_to_id,
                assigned_team_id, is_confidential, recurrence_rule,
                due_date, order_reference, reminder_date,
                contact_name, contact_phone, contact_email, contact_channel,
                callback_requested, callback_due,
            )
            _attach_tags(ticket, tags)
            db.session.add(ticket)
            db.session.flush()

            if checklist_template_id:
                TicketService.apply_checklist_template(
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
        except SQLAlchemyError as exc:
            db.session.rollback()
            current_app.logger.error("Database error creating ticket: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    @staticmethod
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
        try:
            ticket = db.session.get(Ticket, ticket_id)
            if not ticket or ticket.is_deleted:
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
        except SQLAlchemyError as exc:
            db.session.rollback()
            current_app.logger.error("Database error updating ticket: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Delete (soft)
    # ------------------------------------------------------------------

    @staticmethod
    def delete_ticket(
        ticket_id: int,
        author_name: str = "System",
        author_id: Optional[int] = None,
    ) -> bool:
        """Soft-delete a ticket."""
        try:
            ticket = db.session.get(Ticket, ticket_id)
            if not ticket or ticket.is_deleted:
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
        except SQLAlchemyError as exc:
            db.session.rollback()
            current_app.logger.error("Database error deleting ticket: %s", exc)
            raise

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
    def add_comment(
        ticket_id: int,
        author_name: str,
        author_id: Optional[int],
        text: str,
    ) -> Comment:
        """Add a comment and process ``@mentions``."""
        try:
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
        except Exception as exc:
            db.session.rollback()
            current_app.logger.error("Error adding comment: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @staticmethod
    def update_status(
        ticket_id: int,
        status: Any,
        author_name: str = "System",
        author_id: Optional[int] = None,
        commit: bool = True,
    ) -> Optional[Ticket]:
        """Update ticket status and add a system comment."""
        try:
            ticket = db.session.get(Ticket, ticket_id)
            if not ticket or ticket.is_deleted:
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
        except Exception as exc:
            db.session.rollback()
            current_app.logger.error("Error updating status: %s", exc)
            raise


    # ------------------------------------------------------------------
    # Dashboard query
    # ------------------------------------------------------------------

    @staticmethod
    def get_dashboard_tickets(
        worker_id: Optional[int] = None,
        search: Optional[str] = None,
        status_filter: Optional[str] = None,
        page: int = 1,
        per_page: int = 25,
        assigned_to_me: bool = False,
        unassigned_only: bool = False,
        callback_pending: bool = False,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        author_name: Optional[str] = None,
        worker_role: Optional[str] = None,
        team_ids: Optional[List[int]] = None,
        assigned_worker_id: Optional[int] = None,
        sort_by: Optional[str] = None,
        sort_dir: str = "asc",
        due_within_days: int = 0,
    ) -> Dict[str, Any]:
        """Fetch tickets for the dashboard with filtering and pagination."""
        query = _base_ticket_query()
        tc = _team_clauses(team_ids)
        is_elevated = worker_role in _ELEVATED_ROLES

        # Confidential filter
        if not is_elevated and worker_id is not None:
            query = query.filter(
                db.or_(*_confidential_filter(worker_id, team_ids))
            )

        # Assignment filters
        query = _apply_assignment_filters(
            query, worker_id, team_ids,
            assigned_to_me, unassigned_only, assigned_worker_id,
        )

        # Callback filter
        if callback_pending:
            query = query.filter(
                Ticket.callback_requested == True,  # noqa: E712
                Ticket.status != TicketStatus.ERLEDIGT.value,
            )

        # Date range
        if start_date:
            query = query.filter(Ticket.created_at >= start_date)
        if end_date:
            query = query.filter(Ticket.created_at <= end_date)

        # Due-within-days filter (show tickets due within N days or overdue)
        if due_within_days > 0:
            from datetime import timedelta
            cutoff = get_utc_now() + timedelta(days=due_within_days)
            query = query.filter(
                Ticket.due_date.isnot(None),
                Ticket.due_date <= cutoff,
            )

        # Author filter
        if author_name:
            author_sub = (
                db.session.query(Comment.ticket_id)
                .filter(
                    Comment.event_type == "TICKET_CREATED",
                    Comment.author.ilike(f"%{author_name}%"),
                )
                .subquery()
            )
            query = query.filter(Ticket.id.in_(author_sub))

        # Full-text search
        if search:
            query = _apply_search_filter(query, search)

        # Status filter
        if status_filter:
            query = query.filter(Ticket.status == status_filter)
        elif not search and not assigned_to_me:
            query = query.filter(
                Ticket.status != TicketStatus.ERLEDIGT.value
            )

        # Dynamic sorting
        _SORT_COLUMNS = {
            "id": Ticket.id,
            "title": Ticket.title,
            "priority": Ticket.priority,
            "status": Ticket.status,
            "created_at": Ticket.created_at,
            "due_date": Ticket.due_date,
            "order_reference": Ticket.order_reference,
        }
        if sort_by and sort_by in _SORT_COLUMNS:
            col = _SORT_COLUMNS[sort_by]
            if sort_dir == "asc":
                order = col.asc().nullslast()
            else:
                order = col.desc().nullslast()
            focus_pagination = query.order_by(
                order, Ticket.id.desc()
            ).paginate(page=page, per_page=per_page, error_out=False)
        else:
            focus_pagination = query.order_by(
                Ticket.priority.asc(), Ticket.created_at.desc()
            ).paginate(page=page, per_page=per_page, error_out=False)

        summary_counts = _fetch_summary_counts(
            worker_id, worker_role, team_ids,
        )

        return {
            "focus_pagination": focus_pagination,
            "summary_counts": summary_counts,
        }

    # ------------------------------------------------------------------
    # Approvals
    # ------------------------------------------------------------------

    @staticmethod
    def get_pending_approvals(page: int = 1, per_page: int = 15) -> Any:
        """Fetch tickets pending approval."""
        return (
            Ticket.query.filter_by(
                is_deleted=False, approval_status="pending"
            )
            .options(
                joinedload(Ticket.assigned_to), selectinload(Ticket.tags)
            )
            .order_by(Ticket.updated_at.desc())
            .paginate(page=page, per_page=per_page, error_out=False)
        )

    @staticmethod
    def request_approval(
        ticket_id: int, worker_id: int, worker_name: str
    ) -> Tuple[bool, str]:
        """Request approval for a ticket."""
        try:
            ticket = db.session.get(Ticket, ticket_id)
            if not ticket or ticket.is_deleted:
                raise ValueError("Ticket nicht gefunden.")
            if ticket.approval_status == ApprovalStatus.PENDING.value:
                return False, "Freigabe bereits angefragt."

            ticket.approval_status = ApprovalStatus.PENDING.value
            ticket.updated_at = get_utc_now()
            db.session.add(Comment(
                ticket_id=ticket.id,
                author=worker_name,
                author_id=worker_id,
                text="Freigabe wurde angefordert. Das Ticket ist nun gesperrt.",
                is_system_event=True,
                event_type="APPROVAL_REQUEST",
            ))
            db.session.commit()
            _send_approval_emails(ticket.id, worker_name)
            return True, "Freigabe angefragt."
        except Exception as exc:
            db.session.rollback()
            current_app.logger.error("Error requesting approval: %s", exc)
            raise

    @staticmethod
    def approve_ticket(
        ticket_id: int, worker_id: int, worker_name: str
    ) -> Any:
        """Approve a ticket."""
        try:
            ticket = db.session.get(Ticket, ticket_id)
            if not ticket or ticket.is_deleted:
                raise ValueError("Ticket nicht gefunden.")
            if ticket.approval_status == ApprovalStatus.APPROVED.value:
                return False, "Ticket bereits freigegeben."

            ticket.approval_status = ApprovalStatus.APPROVED.value
            ticket.approved_by_id = worker_id
            ticket.approved_at = get_utc_now()
            ticket.updated_at = get_utc_now()
            db.session.add(Comment(
                ticket_id=ticket.id,
                author="System",
                author_id=None,
                text=f"Freigegeben durch {worker_name}",
                is_system_event=True,
                event_type="APPROVAL",
            ))
            db.session.commit()
            _send_approval_result_email(ticket, approved=True)
            return ticket
        except Exception as exc:
            db.session.rollback()
            current_app.logger.error("Error approving ticket: %s", exc)
            raise

    @staticmethod
    def reject_ticket(
        ticket_id: int, worker_id: int, worker_name: str, reason: str
    ) -> Ticket:
        """Reject a ticket with a reason."""
        try:
            ticket = db.session.get(Ticket, ticket_id)
            if not ticket or ticket.is_deleted:
                raise ValueError("Ticket nicht gefunden.")

            ticket.approval_status = ApprovalStatus.REJECTED.value
            ticket.rejected_by_id = worker_id
            ticket.reject_reason = reason
            ticket.status = TicketStatus.OFFEN.value
            ticket.updated_at = get_utc_now()
            db.session.add(Comment(
                ticket_id=ticket.id,
                author="System",
                author_id=None,
                text=f"Freigabe abgelehnt durch {worker_name}. Grund: {reason}",
                is_system_event=True,
                event_type="APPROVAL_REJECTED",
            ))
            db.session.commit()
            _send_approval_result_email(ticket, approved=False, reason=reason)
            return ticket
        except Exception as exc:
            db.session.rollback()
            current_app.logger.error("Error rejecting ticket: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Assignment
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_delegation(
        worker_id: int,
    ) -> Tuple[Optional[int], List[str]]:
        """Resolve OOO delegation chain, detecting circular loops."""
        if not worker_id:
            return None, []

        visited: Set[int] = set()
        path_logs: List[str] = []
        current_id: Optional[int] = worker_id

        while current_id:
            if current_id in visited:
                path_logs.append(
                    "Zirkuläre Vertretung erkannt. Fallback: Unzugewiesen."
                )
                return None, path_logs

            visited.add(current_id)
            worker = db.session.get(Worker, current_id)
            if not worker:
                return None, path_logs

            if not worker.is_out_of_office:
                return current_id, path_logs

            if worker.delegate_to_id:
                delegate = db.session.get(Worker, worker.delegate_to_id)
                delegate_name = delegate.name if delegate else "Unbekannt"
                path_logs.append(
                    f"{worker.name} abwesend -> delegiert an {delegate_name}"
                )
                current_id = worker.delegate_to_id
            else:
                path_logs.append(
                    f"{worker.name} abwesend (kein Vertreter). "
                    "Fallback: Unzugewiesen."
                )
                return None, path_logs

        return None, path_logs

    @staticmethod
    def assign_ticket(
        ticket_id: int,
        worker_id: Optional[int],
        author_name: str,
        author_id: Optional[int] = None,
        team_id: Optional[int] = None,
    ) -> Ticket:
        """Assign a ticket to a worker (with OOO delegation)."""
        try:
            ticket = db.session.get(Ticket, ticket_id)
            if not ticket or ticket.is_deleted:
                raise ValueError("Ticket nicht gefunden.")

            old_name = (
                ticket.assigned_to.name if ticket.assigned_to else "Niemand"
            )
            path_logs: List[str] = []
            if worker_id and worker_id != author_id:
                worker_id, path_logs = TicketService._resolve_delegation(
                    worker_id
                )

            new_name = "Niemand"
            if worker_id:
                worker = db.session.get(Worker, worker_id)
                if not worker:
                    raise ValueError("Mitarbeiter nicht gefunden.")
                new_name = worker.name

            if (
                ticket.assigned_to_id == worker_id
                and ticket.assigned_team_id == team_id
                and not path_logs
            ):
                return ticket

            ticket.assigned_to_id = worker_id
            ticket.assigned_team_id = team_id
            ticket.updated_at = get_utc_now()

            if worker_id and worker_id != author_id:
                TicketService.create_notification(
                    user_id=worker_id,
                    message=f"Ihnen wurde Ticket #{ticket_id} zugewiesen.",
                    link=f"/ticket/{ticket_id}",
                )

            comment_text = _build_assignment_comment(
                author_name, old_name, new_name, path_logs
            )
            _notify_admins_ooo_exhausted(ticket_id, author_id, path_logs)

            db.session.add(Comment(
                ticket_id=ticket.id,
                author=author_name,
                author_id=author_id,
                text=comment_text,
                is_system_event=True,
                event_type="ASSIGNMENT",
            ))

            if worker_id:
                _send_assignment_email(worker_id, new_name, ticket)

            db.session.commit()
            return ticket
        except Exception as exc:
            db.session.rollback()
            current_app.logger.error("Error assigning ticket: %s", exc)
            raise

    @staticmethod
    def reassign_ticket(
        ticket_id: int,
        to_worker_id: int,
        author_name: str,
        author_id: int,
    ) -> Ticket:
        """Direct admin reassignment (no OOO delegation)."""
        try:
            ticket = db.session.get(Ticket, ticket_id)
            if not ticket or ticket.is_deleted:
                raise ValueError("Ticket nicht gefunden.")

            to_worker = db.session.get(Worker, to_worker_id)
            if not to_worker or not to_worker.is_active:
                raise ValueError(
                    "Ziel-Mitarbeiter nicht gefunden oder inaktiv."
                )

            from_name = (
                ticket.assigned_to.name
                if ticket.assigned_to
                else "Nicht zugewiesen"
            )
            ticket.assigned_to_id = to_worker_id
            ticket.updated_at = get_utc_now()

            db.session.add(Comment(
                ticket_id=ticket.id,
                author=author_name,
                author_id=author_id,
                text=(
                    f"Umgezuweisen durch {author_name}: "
                    f"{from_name} → {to_worker.name}"
                ),
                is_system_event=True,
                event_type="ASSIGNMENT",
            ))
            TicketService.create_notification(
                user_id=to_worker_id,
                message=(
                    f"Ticket #{ticket.id} wurde Ihnen zugewiesen "
                    f"(von {from_name})."
                ),
                link=f"/ticket/{ticket.id}",
            )
            db.session.commit()
            return ticket
        except Exception as exc:
            db.session.rollback()
            current_app.logger.error(
                "Error reassigning ticket %s: %s", ticket_id, exc
            )
            raise


    # ------------------------------------------------------------------
    # Ticket meta update
    # ------------------------------------------------------------------

    @staticmethod
    def update_ticket_meta(
        ticket_id: int,
        title: str,
        priority: Optional[int],
        author_name: str,
        author_id: Optional[int],
        due_date: Optional[datetime] = None,
        order_reference: Optional[str] = None,
        reminder_date: Optional[datetime] = None,
        tags: Optional[List[str]] = None,
        recurrence_rule: Optional[str] = None,
    ) -> Ticket:
        """Update ticket metadata with an audit trail."""
        try:
            ticket = db.session.get(Ticket, ticket_id)
            if not ticket:
                raise ValueError("Ticket nicht gefunden")

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

            old_rule = ticket.recurrence_rule
            new_rule = recurrence_rule or None
            if old_rule != new_rule:
                old_label = (old_rule or "Einmalig").capitalize()
                new_label = (new_rule or "Einmalig").capitalize()
                changes.append(f"Serie: {old_label} -> {new_label}")
                ticket.recurrence_rule = new_rule
                if new_rule:
                    increment = _RECURRENCE_INCREMENTS.get(
                        new_rule.lower(), relativedelta(months=1)
                    )
                    ticket.next_recurrence_date = get_utc_now() + increment
                else:
                    ticket.next_recurrence_date = None

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
        except SQLAlchemyError as exc:
            db.session.rollback()
            current_app.logger.error(
                "Database error updating ticket meta: %s", exc
            )
            raise

    # ------------------------------------------------------------------
    # Checklists
    # ------------------------------------------------------------------

    @staticmethod
    def add_checklist_item(
        ticket_id: int,
        title: str,
        assigned_to_id: Optional[int] = None,
        assigned_team_id: Optional[int] = None,
        due_date: Optional[datetime] = None,
        depends_on_item_id: Optional[int] = None,
    ) -> ChecklistItem:
        """Add a checklist item to a ticket."""
        try:
            item = ChecklistItem(
                ticket_id=ticket_id,
                title=title,
                assigned_to_id=assigned_to_id,
                assigned_team_id=assigned_team_id,
                due_date=due_date,
                depends_on_item_id=depends_on_item_id,
            )
            db.session.add(item)
            db.session.commit()
            return item
        except Exception as exc:
            db.session.rollback()
            current_app.logger.error("Error adding checklist item: %s", exc)
            raise

    @staticmethod
    def toggle_checklist_item(
        item_id: int,
        worker_name: str = "System",
        worker_id: Optional[int] = None,
    ) -> Optional[ChecklistItem]:
        """Toggle a checklist item and auto-close the ticket if all done."""
        try:
            item = db.session.get(ChecklistItem, item_id)
            if not item:
                return None

            _check_dependency(item)
            item.is_completed = not item.is_completed
            ticket = item.ticket

            if (
                item.is_completed
                and ticket.status != TicketStatus.ERLEDIGT.value
                and ticket.checklists
                and all(c.is_completed for c in ticket.checklists)
            ):
                ticket.status = TicketStatus.ERLEDIGT.value
                db.session.add(Comment(
                    ticket_id=ticket.id,
                    author=worker_name,
                    author_id=worker_id,
                    text=(
                        "Status automatisch auf ERLEDIGT gesetzt "
                        "(alle Unteraufgaben beendet)."
                    ),
                    is_system_event=True,
                    event_type="STATUS_CHANGE",
                ))

            db.session.commit()
            return item
        except Exception as exc:
            db.session.rollback()
            raise

    @staticmethod
    def delete_checklist_item(item_id: int) -> bool:
        """Delete a checklist item (clears dependencies first)."""
        try:
            item = db.session.get(ChecklistItem, item_id)
            if item:
                ChecklistItem.query.filter_by(
                    depends_on_item_id=item.id
                ).update({"depends_on_item_id": None})
                db.session.delete(item)
                db.session.commit()
            return True
        except Exception as exc:
            db.session.rollback()
            raise

    @staticmethod
    def apply_checklist_template(
        ticket_id: int, template_id: int, commit: bool = True
    ) -> bool:
        """Apply a checklist template to a ticket."""
        from models import ChecklistTemplate

        try:
            ticket = db.session.get(Ticket, ticket_id)
            template = db.session.get(ChecklistTemplate, template_id)
            if not ticket or not template:
                raise ValueError("Ticket oder Vorlage nicht gefunden.")

            ticket.checklist_template_id = template_id
            for t_item in template.items:
                db.session.add(ChecklistItem(
                    ticket_id=ticket.id,
                    title=t_item.title,
                    is_completed=False,
                ))
            db.session.add(Comment(
                ticket_id=ticket.id,
                author="System",
                text=f"Checklisten-Vorlage '{template.title}' angewendet.",
                is_system_event=True,
                event_type="CHECKLIST_TEMPLATE_APPLIED",
            ))
            if commit:
                db.session.commit()
            return True
        except Exception as exc:
            if commit:
                db.session.rollback()
            current_app.logger.error("Error applying template: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    @staticmethod
    def get_projects_summary() -> List[Dict[str, Any]]:
        """Fetch projects grouped by order_reference with progress."""
        tickets = (
            Ticket.query.filter(
                Ticket.is_deleted == False,  # noqa: E712
                Ticket.order_reference.isnot(None),
                Ticket.order_reference != "",
            )
            .options(selectinload(Ticket.checklists))
            .all()
        )
        projects: Dict[str, Dict[str, Any]] = {}

        for ticket in tickets:
            ref = ticket.order_reference.strip()
            if not ref:
                continue
            project = projects.setdefault(ref, _new_project_entry(ref, ticket))
            _accumulate_ticket(project, ticket)

        return _finalize_projects(projects)

    # ------------------------------------------------------------------
    # Workload overview
    # ------------------------------------------------------------------

    @staticmethod
    def get_workload_overview() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Return workload entries split into absent and present workers."""
        now = get_utc_now()
        today = now.date()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=4)

        tickets = (
            Ticket.query.filter(
                Ticket.is_deleted == False,  # noqa: E712
                Ticket.status.in_(_OPEN_STATUSES),
                db.or_(
                    Ticket.assigned_to_id.isnot(None),
                    Ticket.assigned_team_id.isnot(None),
                ),
            )
            .all()
        )

        tickets_by_worker = _group_tickets_by_worker(tickets)
        workers = Worker.query.filter_by(is_active=True).all()

        absent: List[Dict[str, Any]] = []
        present: List[Dict[str, Any]] = []

        for worker in workers:
            worker_tickets = list(tickets_by_worker.get(worker.id, []))
            if not worker_tickets:
                continue

            entry = _build_workload_entry(
                worker, worker_tickets, today, week_end
            )
            if worker.is_out_of_office:
                absent.append(entry)
            else:
                present.append(entry)

        absent.sort(
            key=lambda x: (-x["critical_count"], -x["open_count"])
        )
        present.sort(key=lambda x: -x["open_count"])
        return absent, present


# ---------------------------------------------------------------------------
# Module-private helpers for TicketService methods
# ---------------------------------------------------------------------------

_RECURRENCE_INCREMENTS: Dict[str, relativedelta] = {
    "monthly": relativedelta(months=1),
    "quarterly": relativedelta(months=3),
    "yearly": relativedelta(years=1),
}


def _build_ticket(
    title: str,
    description: Optional[str],
    priority: Any,
    assigned_to_id: Optional[int],
    assigned_team_id: Optional[int],
    is_confidential: bool,
    recurrence_rule: Optional[str],
    due_date: Optional[datetime],
    order_reference: Optional[str],
    reminder_date: Optional[datetime],
    contact_name: Optional[str],
    contact_phone: Optional[str],
    contact_email: Optional[str],
    contact_channel: Optional[str],
    callback_requested: bool,
    callback_due: Optional[datetime],
) -> Ticket:
    """Construct a Ticket ORM object."""
    next_recurrence_date = None
    if recurrence_rule:
        increment = _RECURRENCE_INCREMENTS.get(
            recurrence_rule.lower(), relativedelta(months=1)
        )
        next_recurrence_date = get_utc_now() + increment

    return Ticket(
        title=title,
        description=description,
        priority=int(priority.value if hasattr(priority, "value") else priority),
        status=TicketStatus.OFFEN.value,
        assigned_to_id=assigned_to_id,
        assigned_team_id=assigned_team_id,
        is_confidential=is_confidential,
        recurrence_rule=recurrence_rule,
        next_recurrence_date=next_recurrence_date,
        due_date=due_date,
        order_reference=order_reference,
        reminder_date=reminder_date,
        contact_name=contact_name,
        contact_phone=contact_phone,
        contact_email=contact_email,
        contact_channel=contact_channel,
        callback_requested=bool(callback_requested),
        callback_due=callback_due,
    )


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
        TicketService.create_notification(
            user_id=mentioned.id,
            message=msg,
            link=link,
        )
        if mentioned.email and getattr(mentioned, "email_notifications_enabled", True):
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


def _check_dependency(item: ChecklistItem) -> None:
    """Raise if the item's dependency is not yet completed."""
    if not item.is_completed and item.depends_on_item_id:
        parent = db.session.get(ChecklistItem, item.depends_on_item_id)
        if parent and not parent.is_completed:
            raise ValueError(
                f"Abhängigkeit nicht erfüllt: '{parent.title}' "
                "muss zuerst abgeschlossen werden."
            )


def _build_assignment_comment(
    author_name: str,
    old_name: str,
    new_name: str,
    path_logs: List[str],
) -> str:
    """Build the assignment-change audit comment."""
    if author_name == new_name:
        text = (
            f"Mitarbeiter {new_name} hat sich das Ticket "
            "selbst zugewiesen."
        )
    else:
        text = f"Zuständigkeit geändert: {old_name} -> {new_name}."
    if path_logs:
        text += "\nDelegation:\n- " + "\n- ".join(path_logs)
    return text


def _send_assignment_email(
    worker_id: int, worker_name: str, ticket: Ticket
) -> None:
    """Send an email notification for assignment."""
    assignee = db.session.get(Worker, worker_id)
    if assignee and assignee.email and getattr(assignee, "email_notifications_enabled", True):
        EmailService.send_notification(
            worker_name, ticket.id, ticket.priority,
            recipient_email=assignee.email,
        )


def _send_approval_emails(ticket_id: int, worker_name: str) -> None:
    """Notify admins/management about a pending approval."""
    try:
        admin_workers = Worker.query.filter(
            Worker.is_active == True,  # noqa: E712
            Worker.role.in_(["admin", "hr", "management"]),
            Worker.email.isnot(None),
        ).all()
        emails = [w.email for w in admin_workers if w.email]
        if emails:
            EmailService.send_approval_request(emails, ticket_id, worker_name)
    except Exception as exc:
        current_app.logger.warning("Approval request email failed: %s", exc)


def _send_approval_result_email(
    ticket: Ticket,
    approved: bool,
    reason: Optional[str] = None,
) -> None:
    """Email the assignee about an approval decision."""
    try:
        if ticket.assigned_to and ticket.assigned_to.email:
            EmailService.send_approval_result(
                ticket.assigned_to.name, ticket.id,
                approved=approved, reason=reason,
                recipient_email=ticket.assigned_to.email,
            )
    except Exception as exc:
        current_app.logger.warning("Approval result email failed: %s", exc)


# ---------------------------------------------------------------------------
# Meta-update helpers
# ---------------------------------------------------------------------------

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
        if worker and worker.email:
            try:
                from services.email_service import EmailService
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
# Dashboard query helpers
# ---------------------------------------------------------------------------

def _base_ticket_query() -> Any:
    """Return the base query with eager-loading for dashboard use.

    Uses selectinload for one-to-many relations (comments, checklists, tags)
    to avoid row multiplication that breaks LIMIT/OFFSET pagination.
    joinedload is safe for many-to-one (assigned_to, assigned_team).
    """
    return Ticket.query.filter_by(is_deleted=False).options(
        selectinload(Ticket.comments),
        joinedload(Ticket.assigned_to),
        joinedload(Ticket.assigned_team),
        selectinload(Ticket.tags),
        selectinload(Ticket.checklists),
    )


def _apply_assignment_filters(
    query: Any,
    worker_id: Optional[int],
    team_ids: Optional[List[int]],
    assigned_to_me: bool,
    unassigned_only: bool,
    assigned_worker_id: Optional[int],
) -> Any:
    """Apply assignment-related filters to a ticket query."""
    if assigned_to_me and worker_id:
        tc = _team_clauses(team_ids)
        query = query.filter(
            db.or_(
                Ticket.assigned_to_id == worker_id,
                Ticket.checklists.any(
                    db.and_(
                        ChecklistItem.assigned_to_id == worker_id,
                        ChecklistItem.is_completed == False,  # noqa: E712
                    )
                ),
                *tc,
            )
        )
    elif unassigned_only:
        query = query.filter(
            Ticket.assigned_to_id.is_(None),
            Ticket.assigned_team_id.is_(None),
        )

    if assigned_worker_id:
        query = query.filter(
            Ticket.assigned_to_id == int(assigned_worker_id)
        )
    return query


def _apply_search_filter(query: Any, search: str) -> Any:
    """Apply full-text search across title, description, order ref, comments.

    Splits the search string into tokens and requires ALL tokens to match
    (in any of the searchable fields) via AND logic.
    """
    tokens = search.split()
    if not tokens:
        return query

    for token in tokens:
        pattern = f"%{token}%"
        comment_ids = (
            db.session.query(Comment.ticket_id)
            .filter(Comment.text.ilike(pattern))
            .subquery()
        )
        query = query.filter(
            Ticket.title.ilike(pattern)
            | Ticket.description.ilike(pattern)
            | Ticket.order_reference.ilike(pattern)
            | Ticket.contact_name.ilike(pattern)
            | Ticket.id.in_(comment_ids)
        )
    return query


def _fetch_self_tickets(
    worker_id: Optional[int],
    worker_role: Optional[str],
    team_ids: Optional[List[int]],
    tc: list,
) -> Tuple[List[Ticket], int]:
    """Fetch the 'My Tickets' sidebar (top 5 + total count)."""
    if not worker_id:
        return [], 0

    stc = _team_clauses(team_ids)
    self_query = (
        Ticket.query.filter_by(is_deleted=False)
        .options(
            joinedload(Ticket.comments),
            joinedload(Ticket.assigned_to),
            selectinload(Ticket.tags),
            selectinload(Ticket.checklists),
        )
        .filter(Ticket.status != TicketStatus.ERLEDIGT.value)
        .filter(
            db.or_(
                Ticket.assigned_to_id == worker_id,
                Ticket.checklists.any(
                    db.and_(
                        ChecklistItem.assigned_to_id == worker_id,
                        ChecklistItem.is_completed == False,  # noqa: E712
                    )
                ),
                *stc,
            )
        )
    )

    if worker_role not in _ELEVATED_ROLES:
        self_query = self_query.filter(
            db.or_(*_confidential_filter(worker_id, team_ids))
        )

    total = self_query.count()
    tickets = self_query.order_by(Ticket.updated_at.desc()).limit(5).all()
    return tickets, total


def _fetch_summary_counts(
    worker_id: Optional[int],
    worker_role: Optional[str],
    team_ids: Optional[List[int]],
) -> Dict[str, Any]:
    """Fetch status counts and action-driven counts for the dashboard."""
    base_filter = Ticket.is_deleted == False  # noqa: E712
    confidential = (
        db.or_(*_confidential_filter(worker_id, team_ids))
        if worker_role not in _ELEVATED_ROLES and worker_id is not None
        else None
    )

    # Status counts
    counts_query = (
        db.session.query(Ticket.status, func.count(Ticket.id))
        .filter(base_filter)
        .filter(Ticket.status.in_(_OPEN_STATUSES))
    )
    if confidential is not None:
        counts_query = counts_query.filter(confidential)
    counts = counts_query.group_by(Ticket.status).all()
    summary: Dict[str, Any] = {s: 0 for s in _OPEN_STATUSES}
    for status, count in counts:
        summary[status] = count

    # Unassigned count (no worker AND no team assigned, open statuses)
    unassigned_q = (
        db.session.query(func.count(Ticket.id))
        .filter(base_filter)
        .filter(Ticket.status.in_(_OPEN_STATUSES))
        .filter(Ticket.assigned_to_id.is_(None))
        .filter(Ticket.assigned_team_id.is_(None))
    )
    if confidential is not None:
        unassigned_q = unassigned_q.filter(confidential)
    summary["unassigned"] = unassigned_q.scalar() or 0

    # Callback pending count
    callback_q = (
        db.session.query(func.count(Ticket.id))
        .filter(base_filter)
        .filter(Ticket.status.in_(_OPEN_STATUSES))
        .filter(Ticket.callback_requested == True)  # noqa: E712
    )
    if confidential is not None:
        callback_q = callback_q.filter(confidential)
    summary["callback_pending"] = callback_q.scalar() or 0

    return summary


# ---------------------------------------------------------------------------
# Project helpers
# ---------------------------------------------------------------------------

def _new_project_entry(ref: str, ticket: Ticket) -> Dict[str, Any]:
    """Initialise a project accumulator dict."""
    return {
        "order_reference": ref,
        "total_tickets": 0,
        "completed_tickets": 0,
        "last_updated": ticket.updated_at or ticket.created_at,
        "ticket_progress_sum": 0.0,
        "status_counts": {s.value: 0 for s in TicketStatus},
    }


def _accumulate_ticket(project: Dict[str, Any], ticket: Ticket) -> None:
    """Add a ticket's contribution to a project accumulator."""
    project["total_tickets"] += 1
    t_time = ticket.updated_at or ticket.created_at
    if t_time and (
        not project["last_updated"] or t_time > project["last_updated"]
    ):
        project["last_updated"] = t_time

    project["status_counts"].setdefault(ticket.status, 0)
    project["status_counts"][ticket.status] += 1

    is_done = ticket.status == TicketStatus.ERLEDIGT.value
    if is_done:
        project["completed_tickets"] += 1

    if ticket.checklists:
        done = sum(1 for c in ticket.checklists if c.is_completed)
        total = len(ticket.checklists)
        progress = done / total if total > 0 else 0.0
    else:
        progress = 1.0 if is_done else 0.0
    project["ticket_progress_sum"] += progress


def _finalize_projects(
    projects: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Compute progress percentages and sort the project list."""
    result: List[Dict[str, Any]] = []
    for project in projects.values():
        total = project["total_tickets"]
        project["progress"] = (
            int((project["ticket_progress_sum"] / total) * 100)
            if total > 0
            else 0
        )
        project["is_completed"] = project["progress"] == 100
        result.append(project)

    result.sort(
        key=lambda x: (
            x["is_completed"],
            -(x["last_updated"].timestamp() if x["last_updated"] else 0),
        )
    )
    return result


# ---------------------------------------------------------------------------
# Workload helpers
# ---------------------------------------------------------------------------

def _group_tickets_by_worker(
    tickets: List[Ticket],
) -> Dict[int, Set[Ticket]]:
    """Group tickets by assigned worker (including team members)."""
    by_worker: Dict[int, Set[Ticket]] = {}
    for ticket in tickets:
        if ticket.assigned_to_id:
            by_worker.setdefault(ticket.assigned_to_id, set()).add(ticket)
        if ticket.assigned_team_id and ticket.assigned_team:
            for member in ticket.assigned_team.members:
                by_worker.setdefault(member.id, set()).add(ticket)
    return by_worker


def _build_workload_entry(
    worker: Worker,
    worker_tickets: List[Ticket],
    today: date,
    week_end: date,
) -> Dict[str, Any]:
    """Build a workload summary dict for a single worker."""
    critical = [t for t in worker_tickets if _is_critical_ticket(t, week_end)]
    other = [t for t in worker_tickets if not _is_critical_ticket(t, week_end)]

    critical.sort(key=lambda t: _workload_sort_key(t, today))
    other.sort(key=lambda t: _workload_sort_key(t, today))

    return {
        "worker": worker,
        "open_count": len(worker_tickets),
        "critical_count": len(critical),
        "tickets": critical + other,
        "critical_tickets": critical,
        "other_tickets": other,
    }
