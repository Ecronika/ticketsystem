"""Database Models for the Ticket System."""

import logging
import os
from typing import Any, List, Optional, Set

from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import object_session

from enums import ELEVATED_ROLES, TicketPriority, TicketStatus, WorkerRole
from extensions import Config, db
from utils import get_utc_now

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System Settings
# ---------------------------------------------------------------------------

class SystemSettings(db.Model):
    """Key-value store for system-wide configuration.

    Used for backup schedules, retention policy, feature flags, etc.
    """

    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.String(200), nullable=True)

    @staticmethod
    def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
        """Retrieve a setting value, returning *default* on any failure."""
        try:
            setting = db.session.get(SystemSettings, key)
            return setting.value if setting else default
        except SQLAlchemyError:
            return default

    @staticmethod
    def set_setting(key: str, value: str) -> None:
        """Create or update a system setting."""
        try:
            setting = (
                SystemSettings.query.filter_by(key=key)
                .with_for_update()
                .first()
            )
            if not setting:
                setting = SystemSettings(key=key, value=str(value))
                db.session.add(setting)
            else:
                setting.value = str(value)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class Worker(db.Model):
    """Worker model representing staff members in the enterprise."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    pin_hash = db.Column(db.String(128), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    role = db.Column(db.String(20), nullable=True)
    needs_pin_change = db.Column(db.Boolean, default=True)
    last_active = db.Column(db.DateTime, nullable=True)

    # Brute-force protection
    failed_login_count = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    email = db.Column(db.String(120), nullable=True)

    # Absence management
    is_out_of_office = db.Column(db.Boolean, default=False)
    delegate_to_id = db.Column(
        db.Integer, db.ForeignKey("worker.id"), nullable=True
    )
    delegate_to = db.relationship(
        "Worker", remote_side=[id], foreign_keys=[delegate_to_id]
    )

    # UI preferences
    ui_theme = db.Column(db.String(20), nullable=True, default="auto")
    email_notifications_enabled = db.Column(db.Boolean, default=True, nullable=False, server_default="1")
    push_notifications_enabled = db.Column(db.Boolean, default=True, nullable=False, server_default="1")

    def __repr__(self) -> str:
        return f"<Worker {self.name}>"


# ---------------------------------------------------------------------------
# Association Tables
# ---------------------------------------------------------------------------

ticket_tags = db.Table(
    "ticket_tags",
    db.Column(
        "ticket_id", db.Integer, db.ForeignKey("ticket.id"), primary_key=True
    ),
    db.Column(
        "tag_id", db.Integer, db.ForeignKey("tag.id"), primary_key=True
    ),
)

worker_team = db.Table(
    "worker_team",
    db.Column(
        "worker_id", db.Integer, db.ForeignKey("worker.id"), primary_key=True
    ),
    db.Column(
        "team_id", db.Integer, db.ForeignKey("team.id"), primary_key=True
    ),
)


# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------

class Team(db.Model):
    """Team model for grouping workers."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    members = db.relationship(
        "Worker",
        secondary=worker_team,
        backref=db.backref("teams", lazy="dynamic"),
        cascade="all, delete",
    )

    @staticmethod
    def team_ids_for_worker(worker_id: int) -> List[int]:
        """Return list of team IDs the given worker belongs to."""
        rows = (
            db.session.query(worker_team.c.team_id)
            .filter(worker_team.c.worker_id == worker_id)
            .all()
        )
        return [r[0] for r in rows]

    def __repr__(self) -> str:
        return f"<Team {self.name}>"


# ---------------------------------------------------------------------------
# Tag
# ---------------------------------------------------------------------------

class Tag(db.Model):
    """Tag model for categorizing tickets."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True, nullable=False)

    def __repr__(self) -> str:
        return f"<Tag {self.name}>"


# ---------------------------------------------------------------------------
# Checklist
# ---------------------------------------------------------------------------

class ChecklistItem(db.Model):
    """Sub-task belonging to a ticket."""

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(
        db.Integer, db.ForeignKey("ticket.id"), nullable=False
    )
    title = db.Column(db.String(150), nullable=False)
    is_completed = db.Column(db.Boolean, default=False)
    assigned_to_id = db.Column(
        db.Integer, db.ForeignKey("worker.id"), nullable=True
    )
    assigned_to = db.relationship("Worker", foreign_keys=[assigned_to_id])
    assigned_team_id = db.Column(
        db.Integer, db.ForeignKey("team.id"), nullable=True
    )
    assigned_team = db.relationship("Team", foreign_keys=[assigned_team_id])
    due_date = db.Column(db.Date, nullable=True)
    depends_on_item_id = db.Column(
        db.Integer, db.ForeignKey("checklist_item.id"), nullable=True
    )
    depends_on_item = db.relationship(
        "ChecklistItem",
        remote_side="ChecklistItem.id",
        backref="dependent_items",
    )
    sort_order = db.Column(db.Integer, default=0, nullable=False, server_default="0")

    def __repr__(self) -> str:
        return f"<ChecklistItem {self.title}>"


class ChecklistTemplate(db.Model):
    """Template for standardised checklist items (e.g. recurring maintenance)."""

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)

    items = db.relationship(
        "ChecklistTemplateItem",
        backref="template",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ChecklistTemplate {self.title}>"


class ChecklistTemplateItem(db.Model):
    """Individual item within a ``ChecklistTemplate``."""

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(
        db.Integer, db.ForeignKey("checklist_template.id"), nullable=False
    )
    title = db.Column(db.String(150), nullable=False)

    def __repr__(self) -> str:
        return f"<ChecklistTemplateItem {self.title}>"


# ---------------------------------------------------------------------------
# Ticket satellite tables (extracted from Ticket to normalize the schema)
# ---------------------------------------------------------------------------

class TicketContact(db.Model):
    """Customer contact information associated with a ticket (1-to-1)."""

    __tablename__ = "ticket_contact"

    ticket_id = db.Column(
        db.Integer, db.ForeignKey("ticket.id", ondelete="CASCADE"),
        primary_key=True,
    )
    name = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(150), nullable=True)
    channel = db.Column(db.String(20), nullable=True)
    callback_requested = db.Column(db.Boolean, default=False, nullable=False)
    callback_due = db.Column(db.DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<TicketContact ticket={self.ticket_id} name={self.name!r}>"


class TicketApproval(db.Model):
    """Approval workflow state for a ticket (1-to-1)."""

    __tablename__ = "ticket_approval"

    ticket_id = db.Column(
        db.Integer, db.ForeignKey("ticket.id", ondelete="CASCADE"),
        primary_key=True,
    )
    status = db.Column(db.String(20), default="none", nullable=False)
    approved_by_id = db.Column(
        db.Integer, db.ForeignKey("worker.id"), nullable=True,
    )
    approved_by = db.relationship("Worker", foreign_keys=[approved_by_id])
    approved_at = db.Column(db.DateTime, nullable=True)
    rejected_by_id = db.Column(
        db.Integer, db.ForeignKey("worker.id"), nullable=True,
    )
    rejected_by = db.relationship("Worker", foreign_keys=[rejected_by_id])
    reject_reason = db.Column(db.Text, nullable=True)

    def __repr__(self) -> str:
        return f"<TicketApproval ticket={self.ticket_id} status={self.status!r}>"


class TicketRecurrence(db.Model):
    """Recurrence schedule for a ticket (1-to-1)."""

    __tablename__ = "ticket_recurrence"

    ticket_id = db.Column(
        db.Integer, db.ForeignKey("ticket.id", ondelete="CASCADE"),
        primary_key=True,
    )
    rule = db.Column(db.String(50), nullable=False)
    next_date = db.Column(db.DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<TicketRecurrence ticket={self.ticket_id} rule={self.rule!r}>"


# ---------------------------------------------------------------------------
# Ticket
# ---------------------------------------------------------------------------

class Ticket(db.Model):
    """Main Ticket model for tracking issues and tasks."""

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)

    status = db.Column(
        db.String(20), default=TicketStatus.OFFEN.value, nullable=False
    )
    priority = db.Column(db.Integer, default=2, nullable=False)

    assigned_to_id = db.Column(
        db.Integer, db.ForeignKey("worker.id"), nullable=True
    )
    assigned_to = db.relationship(
        "Worker", backref="tickets", foreign_keys=[assigned_to_id]
    )

    due_date = db.Column(db.Date, nullable=True)
    order_reference = db.Column(db.String(50), nullable=True)
    reminder_date = db.Column(db.DateTime, nullable=True)
    reminder_notified_at = db.Column(db.DateTime, nullable=True)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)

    # Team & confidentiality
    assigned_team_id = db.Column(
        db.Integer, db.ForeignKey("team.id"), nullable=True
    )
    assigned_team = db.relationship("Team", backref="tickets")
    is_confidential = db.Column(db.Boolean, default=False, nullable=False)
    checklist_template_id = db.Column(
        db.Integer, db.ForeignKey("checklist_template.id", ondelete="SET NULL"), nullable=True
    )
    checklist_template = db.relationship(
        "ChecklistTemplate", backref="legacy_tickets"
    )
    last_escalated_at = db.Column(db.DateTime, nullable=True)

    # 1-to-1 satellite relationships
    contact = db.relationship(
        "TicketContact", uselist=False, backref="ticket",
        cascade="all, delete-orphan",
    )
    approval = db.relationship(
        "TicketApproval", uselist=False, backref="ticket",
        cascade="all, delete-orphan",
    )
    recurrence = db.relationship(
        "TicketRecurrence", uselist=False, backref="ticket",
        cascade="all, delete-orphan",
    )

    checklists = db.relationship(
        "ChecklistItem", backref="ticket", cascade="all, delete-orphan"
    )
    tags = db.relationship(
        "Tag",
        secondary=ticket_tags,
        backref=db.backref("tickets", lazy="dynamic"),
    )

    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(
        db.DateTime, default=get_utc_now, onupdate=get_utc_now
    )

    def __repr__(self) -> str:
        return f"<Ticket {self.title} ({self.status})>"

    # ------------------------------------------------------------------
    # Access Control
    # ------------------------------------------------------------------

    def is_accessible_by(self, worker_id: Optional[int], role: Optional[str]) -> bool:
        """Return ``True`` if the given worker may view this ticket.

        Non-confidential tickets are always accessible.  Confidential
        tickets are restricted to elevated roles, the assignee, checklist
        participants, team members, and the original author.
        """
        if not self.is_confidential:
            return True
        if role in ELEVATED_ROLES:
            return True
        if self.assigned_to_id == worker_id:
            return True
        if self._worker_on_checklist(worker_id):
            return True
        if self._worker_in_assigned_team(worker_id):
            return True
        if self._worker_is_author(worker_id):
            return True
        return False

    def _worker_on_checklist(self, worker_id: Optional[int]) -> bool:
        """Check whether *worker_id* is assigned to any open checklist item."""
        return any(c.assigned_to_id == worker_id for c in self.checklists)

    def _worker_in_assigned_team(self, worker_id: Optional[int]) -> bool:
        """Check whether *worker_id* belongs to the ticket's or a checklist's team."""
        if not worker_id:
            return False
        team_ids = Team.team_ids_for_worker(worker_id)
        if not team_ids:
            return False
        if self.assigned_team_id in team_ids:
            return True
        return any(c.assigned_team_id in team_ids for c in self.checklists)

    def _worker_is_author(self, worker_id: Optional[int]) -> bool:
        """Check authorship via a targeted COUNT query (avoids lazy-loading)."""
        sess = object_session(self)
        if sess is None:
            return False
        return (
            sess.query(Comment)
            .filter(
                Comment.ticket_id == self.id,
                Comment.author_id == worker_id,
                Comment.event_type == "TICKET_CREATED",
            )
            .limit(1)
            .count()
            > 0
        )


# ---------------------------------------------------------------------------
# Notification
# ---------------------------------------------------------------------------

class Notification(db.Model):
    """In-app notification (mentions, assignments, SLA alerts)."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("worker.id"), nullable=False
    )
    user = db.relationship(
        "Worker",
        backref=db.backref(
            "notifications", lazy="dynamic", cascade="all, delete-orphan"
        ),
    )

    message = db.Column(db.String(255), nullable=False)
    link = db.Column(db.String(255), nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=get_utc_now)

    def __repr__(self) -> str:
        return f"<Notification for Worker {self.user_id}: {self.message[:20]}>"


# ---------------------------------------------------------------------------
# Push Subscription (WebPush / VAPID)
# ---------------------------------------------------------------------------

class PushSubscription(db.Model):
    """Stores browser WebPush subscription data per worker."""

    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(
        db.Integer, db.ForeignKey("worker.id"), nullable=False
    )
    worker = db.relationship(
        "Worker",
        backref=db.backref(
            "push_subscriptions", lazy="dynamic", cascade="all, delete-orphan"
        ),
    )

    endpoint = db.Column(db.Text, nullable=False, unique=True)
    p256dh = db.Column(db.Text, nullable=False)
    auth = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=get_utc_now)

    def as_subscription_info(self) -> dict:
        """Return the dict expected by pywebpush."""
        return {
            "endpoint": self.endpoint,
            "keys": {"p256dh": self.p256dh, "auth": self.auth},
        }

    def __repr__(self) -> str:
        return f"<PushSubscription worker={self.worker_id}>"


# ---------------------------------------------------------------------------
# Attachment
# ---------------------------------------------------------------------------

class Attachment(db.Model):
    """Metadata for an uploaded file attached to a ticket."""

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(
        db.Integer, db.ForeignKey("ticket.id"), nullable=False
    )
    ticket = db.relationship(
        "Ticket",
        backref=db.backref("attachments", cascade="all, delete-orphan"),
    )

    path = db.Column(db.String(255), nullable=False)
    filename = db.Column(db.String(100), nullable=False)
    mime_type = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=get_utc_now)

    def __repr__(self) -> str:
        return f"<Attachment {self.filename} for Ticket {self.ticket_id}>"


# ---------------------------------------------------------------------------
# Comment
# ---------------------------------------------------------------------------

class Comment(db.Model):
    """Comment model documenting the ticket audit trail."""

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(
        db.Integer, db.ForeignKey("ticket.id"), nullable=False
    )
    ticket = db.relationship(
        "Ticket",
        backref=db.backref("comments", cascade="all, delete-orphan"),
    )

    author = db.Column(db.String(50), nullable=False)
    author_id = db.Column(
        db.Integer, db.ForeignKey("worker.id"), nullable=True
    )
    author_worker = db.relationship("Worker", foreign_keys=[author_id])

    text = db.Column(db.Text, nullable=False)
    is_system_event = db.Column(db.Boolean, default=False)
    event_type = db.Column(db.String(30), nullable=True)

    created_at = db.Column(db.DateTime, default=get_utc_now)

    def __repr__(self) -> str:
        return f"<Comment by {self.author} on Ticket {self.ticket_id}>"


# ---------------------------------------------------------------------------
# Attachment File-Deletion Hooks
# ---------------------------------------------------------------------------

def _safe_attachment_path(target: Attachment) -> Optional[str]:
    """Resolve and validate an attachment's filesystem path."""
    safe_filename = os.path.basename(target.path)
    if not safe_filename or safe_filename in (".", ".."):
        return None
    data_dir = Config.get_data_dir()
    return os.path.join(data_dir, "attachments", safe_filename)


@event.listens_for(Attachment, "after_delete")
def queue_file_deletion(
    _mapper: Any, _connection: Any, target: Attachment
) -> None:
    """Queue the physical file for deletion after a successful commit."""
    if not target.path:
        return
    sess = object_session(target)
    if not sess:
        return
    if "pending_deletions" not in sess.info:
        sess.info["pending_deletions"] = set()
    filepath = _safe_attachment_path(target)
    if filepath:
        sess.info["pending_deletions"].add(filepath)


@event.listens_for(db.session, "after_commit")
def process_file_deletions(session: Any) -> None:
    """Physically delete files queued during the session."""
    pending: Set[str] = session.info.get("pending_deletions", set())
    for filepath in pending:
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                _logger.info(
                    "Deleted attachment file after commit: %s", filepath
                )
        except OSError as exc:
            _logger.error(
                "Failed to delete attachment %s: %s", filepath, exc
            )
    session.info.pop("pending_deletions", None)


@event.listens_for(db.session, "after_rollback")
def clear_pending_deletions(session: Any) -> None:
    """Clear the deletion queue when the transaction is rolled back."""
    session.info.pop("pending_deletions", None)
