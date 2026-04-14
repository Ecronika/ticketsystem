"""Shared helpers, constants, and dataclasses used across ticket services.

This module is the single source of truth for low-level ticket utilities
that are consumed by ``ticket_core_service``, ``ticket_assignment_service``,
and ``dashboard_service``.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from dateutil.relativedelta import relativedelta

from enums import TicketPriority, TicketStatus
from exceptions import TicketNotFoundError
from extensions import db
from models import ChecklistItem, Comment, Ticket, TicketContact
from utils import get_utc_now

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS = frozenset({
    "png", "jpg", "jpeg", "gif", "pdf",
    "doc", "docx", "xls", "xlsx", "txt",
})

MAX_UPLOAD_FILES = 10
MAX_UPLOAD_FILE_SIZE = 15 * 1024 * 1024    # 15 MB per file
MAX_UPLOAD_TOTAL_SIZE = 50 * 1024 * 1024   # 50 MB total per request

_OPEN_STATUSES = [
    TicketStatus.OFFEN.value,
    TicketStatus.IN_BEARBEITUNG.value,
    TicketStatus.WARTET.value,
]

_RECURRENCE_INCREMENTS: Dict[str, relativedelta] = {
    "monthly": relativedelta(months=1),
    "quarterly": relativedelta(months=3),
    "yearly": relativedelta(years=1),
}


# ---------------------------------------------------------------------------
# Dataclasses (re-exported by the facade for backward compatibility)
# ---------------------------------------------------------------------------

@dataclass
class TicketFilterSpec:
    """Filter and pagination criteria for dashboard queries."""

    worker_id: Optional[int] = None
    search: Optional[str] = None
    status_filter: Optional[str] = None
    page: int = 1
    per_page: int = 25
    assigned_to_me: bool = False
    unassigned_only: bool = False
    callback_pending: bool = False
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    author_name: Optional[str] = None
    worker_role: Optional[str] = None
    team_ids: Optional[List[int]] = field(default=None)
    assigned_worker_id: Optional[int] = None
    sort_by: Optional[str] = None
    sort_dir: str = "asc"
    due_within_days: int = 0


@dataclass
class ContactInfo:
    """Customer contact details passed into ticket creation/update."""

    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    channel: Optional[str] = None
    callback_requested: bool = False
    callback_due: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Urgency scoring
# ---------------------------------------------------------------------------

def _urgency_score(ticket: Ticket, now: Optional[datetime] = None) -> int:
    """Combined urgency value.  Lower score = more urgent."""
    if now is None:
        now = get_utc_now()
    prio = ticket.priority
    if ticket.due_date is None:
        return 500 + prio * 100
    days_left = (ticket.due_date - now.date()).days
    if days_left < 0:
        return max(0, 50 + days_left) + prio * 5
    if days_left == 0:
        return 150 + prio * 5
    if days_left <= 7:
        return 200 + days_left * 10 + prio * 5
    return 300 + min(100, days_left) + prio * 20


# ---------------------------------------------------------------------------
# Workload helpers
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
        if ticket.due_date <= week_end:
            return True
    return False


def _workload_sort_key(ticket: Ticket, today: date) -> Tuple[int, int]:
    """Sort key: overdue first, then by priority."""
    if ticket.due_date:
        days_left = (ticket.due_date - today).days
    else:
        days_left = 999
    return (days_left, ticket.priority)


# ---------------------------------------------------------------------------
# Date formatting helper
# ---------------------------------------------------------------------------

def _format_date(dt: Optional[datetime], fallback: str = "Keines") -> str:
    """Format a datetime for audit log entries."""
    return dt.strftime("%d.%m.%Y") if dt else fallback


# ---------------------------------------------------------------------------
# Ticket loaders
# ---------------------------------------------------------------------------

def _get_ticket_or_raise(ticket_id: int) -> Ticket:
    """Load a non-deleted ticket or raise ``TicketNotFoundError``."""
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.is_deleted:
        raise TicketNotFoundError()
    return ticket


def _get_ticket_or_none(ticket_id: int) -> Optional[Ticket]:
    """Load a non-deleted ticket or return ``None``."""
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.is_deleted:
        return None
    return ticket


# ---------------------------------------------------------------------------
# Confidential-filter builder
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
        .scalar_subquery()
    )
    clauses = [
        Ticket.is_confidential.is_(False),
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
                ChecklistItem.is_completed.is_(False),
            )
        ),
    ]


# ---------------------------------------------------------------------------
# Full-text search filter
# ---------------------------------------------------------------------------

def apply_search_filter(query: Any, search: str) -> Any:
    """Apply full-text search across ticket fields and comments.

    Searches title, description, order reference, contact name/email/phone,
    and comment text.  Multiple tokens are AND-combined.
    """
    tokens = search.split()
    if not tokens:
        return query

    for token in tokens:
        pattern = f"%{token}%"
        comment_ids = (
            db.session.query(Comment.ticket_id)
            .filter(Comment.text.ilike(pattern))
            .scalar_subquery()
        )
        query = query.filter(
            Ticket.title.ilike(pattern)
            | Ticket.description.ilike(pattern)
            | Ticket.order_reference.ilike(pattern)
            | Ticket.contact.has(TicketContact.name.ilike(pattern))
            | Ticket.contact.has(TicketContact.email.ilike(pattern))
            | Ticket.contact.has(TicketContact.phone.ilike(pattern))
            | Ticket.id.in_(comment_ids)
        )
    return query
