"""Ticket approval workflow: request, approve, and reject.

Extracted from the monolithic ``ticket_service.py`` to isolate the
approval lifecycle into a dedicated service module.
"""

import logging
from typing import Any, Optional, Tuple

from flask import current_app
from sqlalchemy.orm import joinedload, selectinload

from enums import ApprovalStatus, TicketStatus
from extensions import db
from models import Comment, Ticket, TicketApproval, Worker
from utils import get_utc_now

from ._helpers import db_transaction
from ._ticket_helpers import _get_ticket_or_raise
from .email_service import EmailService

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-private helpers
# ---------------------------------------------------------------------------

def _send_approval_emails(ticket_id: int, worker_name: str) -> None:
    """Notify admins/management about a pending approval."""
    try:
        admin_workers = Worker.query.filter(
            Worker.is_active.is_(True),
            Worker.role.in_(["admin", "hr", "management"]),
            Worker.email.isnot(None),
        ).all()
        emails = [
            w.email for w in admin_workers
            if w.email and w.email_notifications_enabled
        ]
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
        assignee = ticket.assigned_to
        if assignee and assignee.email and assignee.email_notifications_enabled:
            EmailService.send_approval_result(
                assignee.name, ticket.id,
                approved=approved, reason=reason,
                recipient_email=assignee.email,
            )
    except Exception as exc:
        current_app.logger.warning("Approval result email failed: %s", exc)


# ---------------------------------------------------------------------------
# Main Service Class
# ---------------------------------------------------------------------------

class TicketApprovalService:
    """Approval workflow: request, approve, and reject tickets."""

    # ------------------------------------------------------------------
    # Pending approvals list
    # ------------------------------------------------------------------

    @staticmethod
    def get_pending_approvals(page: int = 1, per_page: int = 15) -> Any:
        """Fetch tickets pending approval."""
        return (
            Ticket.query.filter(
                Ticket.is_deleted.is_(False),
                Ticket.approval.has(TicketApproval.status == "pending"),
            )
            .options(
                joinedload(Ticket.assigned_to), selectinload(Ticket.tags)
            )
            .order_by(Ticket.updated_at.desc())
            .paginate(page=page, per_page=per_page, error_out=False)
        )

    # ------------------------------------------------------------------
    # Request approval
    # ------------------------------------------------------------------

    @staticmethod
    @db_transaction
    def request_approval(
        ticket_id: int, worker_id: int, worker_name: str
    ) -> Tuple[bool, str]:
        """Request approval for a ticket."""
        ticket = _get_ticket_or_raise(ticket_id)
        if ticket.approval and ticket.approval.status == ApprovalStatus.PENDING.value:
            return False, "Freigabe bereits angefragt."

        ticket.ensure_approval().status = ApprovalStatus.PENDING.value
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

    # ------------------------------------------------------------------
    # Approve
    # ------------------------------------------------------------------

    @staticmethod
    @db_transaction
    def approve_ticket(
        ticket_id: int, worker_id: int, worker_name: str
    ) -> Any:
        """Approve a ticket."""
        ticket = _get_ticket_or_raise(ticket_id)
        if ticket.approval and ticket.approval.status == ApprovalStatus.APPROVED.value:
            return False, "Ticket bereits freigegeben."

        approval = ticket.ensure_approval()
        approval.status = ApprovalStatus.APPROVED.value
        approval.approved_by_id = worker_id
        approval.approved_at = get_utc_now()
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

    # ------------------------------------------------------------------
    # Reject
    # ------------------------------------------------------------------

    @staticmethod
    @db_transaction
    def reject_ticket(
        ticket_id: int, worker_id: int, worker_name: str, reason: str
    ) -> Ticket:
        """Reject a ticket with a reason."""
        ticket = _get_ticket_or_raise(ticket_id)

        approval = ticket.ensure_approval()
        approval.status = ApprovalStatus.REJECTED.value
        approval.rejected_by_id = worker_id
        approval.reject_reason = reason
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
