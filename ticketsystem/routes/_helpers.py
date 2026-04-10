"""Shared helpers for route modules.

Contains session helpers, access checks, form parsing utilities,
and constants used across multiple ticket route sub-modules.
"""

from datetime import date, datetime, timezone
from typing import Any

from flask import Response, jsonify, request, session
from zoneinfo import ZoneInfo

from enums import ApprovalStatus
from extensions import db
from models import ChecklistItem, Ticket
from services._helpers import api_error

_PRIO_LABELS: dict[int, str] = {1: "Hoch", 2: "Mittel", 3: "Niedrig"}


# ------------------------------------------------------------------
# Session helpers
# ------------------------------------------------------------------

def _session_author() -> str:
    """Return the current session's worker name or ``'System'``."""
    return session.get("worker_name", "System")


def _session_worker_id() -> int | None:
    """Return the current session's worker id."""
    return session.get("worker_id")


# ------------------------------------------------------------------
# Access checks
# ------------------------------------------------------------------

def _check_ticket_access(ticket_id: int) -> Ticket | None:
    """Load a ticket and verify access; return ``None`` on failure."""
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or not ticket.is_accessible_by(
        _session_worker_id(), session.get("role"),
    ):
        return None
    return ticket


def check_approval_lock(
    ticket_id: int | None = None,
    item_id: int | None = None,
) -> tuple[Response, int] | None:
    """Return a 403 JSON response if the ticket is approval-locked."""
    ticket: Ticket | None = None
    if item_id:
        item = db.session.get(ChecklistItem, item_id)
        if not item:
            return None
        ticket = item.ticket
    elif ticket_id:
        ticket = db.session.get(Ticket, ticket_id)

    if ticket and ticket.approval and ticket.approval.status == ApprovalStatus.PENDING.value:
        return api_error("Ticket ist für die Freigabe gesperrt.", 403)
    return None


# ------------------------------------------------------------------
# Form parsing helpers
# ------------------------------------------------------------------

def _parse_callback_due(raw: str) -> datetime | None:
    """Parse a callback-due datetime string to naive UTC."""
    if not raw:
        return None
    local_tz = ZoneInfo("Europe/Berlin")
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            dt_local = datetime.strptime(raw, fmt)
            return (
                dt_local.replace(tzinfo=local_tz)
                .astimezone(timezone.utc)
                .replace(tzinfo=None)
            )
        except ValueError:
            continue
    return None


def _parse_assignment_ids(
    raw_worker: str | None,
    raw_team: str | None,
) -> tuple[int | None, int | None]:
    """Parse the combined worker/team assignment form fields.

    Returns:
        ``(assigned_to_id, assigned_team_id)``
    """
    assigned_to_id: int | None = None
    assigned_team_id: int | None = None

    if raw_worker and raw_worker.startswith("team_"):
        assigned_team_id = _safe_int(raw_worker[5:])
    elif raw_worker and raw_worker.isdigit():
        assigned_to_id = int(raw_worker)
    elif _session_worker_id():
        assigned_to_id = _session_worker_id()

    if raw_team and not assigned_team_id:
        if raw_team.startswith("team_"):
            assigned_team_id = _safe_int(raw_team[5:])
        elif raw_team.isdigit():
            assigned_team_id = int(raw_team)

    return assigned_to_id, assigned_team_id


def _safe_int(val: str | None) -> int | None:
    """Convert *val* to ``int`` or return ``None``."""
    if not val:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _parse_date(raw: str | None, fmt: str = "%Y-%m-%d") -> date | None:
    """Parse a date string; return ``None`` on failure."""
    if not raw:
        return None
    try:
        clean = raw.split("T")[0]
        return datetime.strptime(clean, fmt).date()
    except (ValueError, TypeError, IndexError):
        return None
