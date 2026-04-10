"""Ticket assignment and OOO delegation logic.

Extracted from the monolithic ``ticket_service.py`` to isolate
assignment, delegation chain resolution, and reassignment into a
dedicated service module.
"""

import logging
from typing import Any, List, Optional, Set, Tuple

from flask import current_app

from exceptions import WorkerNotFoundError
from extensions import db
from models import Comment, Ticket, Worker
from utils import get_utc_now

from ._helpers import db_transaction
from ._ticket_helpers import _get_ticket_or_raise
from .email_service import EmailService

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-private helpers
# ---------------------------------------------------------------------------

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
    if assignee and assignee.email and assignee.email_notifications_enabled:
        EmailService.send_notification(
            worker_name, ticket.id, ticket.priority,
            recipient_email=assignee.email,
        )


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
        # Lazy import to avoid circular dependency
        from services.ticket_core_service import TicketCoreService

        admins = Worker.query.filter_by(is_active=True, role="admin").all()
        for admin in admins:
            if admin.id != author_id:
                TicketCoreService.create_notification(
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

class TicketAssignmentService:
    """Ticket assignment, OOO delegation, and reassignment."""

    # ------------------------------------------------------------------
    # OOO delegation chain
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

    # ------------------------------------------------------------------
    # Assign
    # ------------------------------------------------------------------

    @staticmethod
    @db_transaction
    def assign_ticket(
        ticket_id: int,
        worker_id: Optional[int],
        author_name: str,
        author_id: Optional[int] = None,
        team_id: Optional[int] = None,
    ) -> Ticket:
        """Assign a ticket to a worker (with OOO delegation)."""
        from services.ticket_core_service import TicketCoreService

        ticket = _get_ticket_or_raise(ticket_id)

        old_name = (
            ticket.assigned_to.name if ticket.assigned_to else "Niemand"
        )
        path_logs: List[str] = []
        if worker_id and worker_id != author_id:
            worker_id, path_logs = TicketAssignmentService._resolve_delegation(
                worker_id
            )

        new_name = "Niemand"
        if worker_id:
            worker = db.session.get(Worker, worker_id)
            if not worker:
                raise WorkerNotFoundError()
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
            TicketCoreService.create_notification(
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

    # ------------------------------------------------------------------
    # Reassign (admin, no OOO)
    # ------------------------------------------------------------------

    @staticmethod
    @db_transaction
    def reassign_ticket(
        ticket_id: int,
        to_worker_id: int,
        author_name: str,
        author_id: int,
    ) -> Ticket:
        """Direct admin reassignment (no OOO delegation)."""
        from services.ticket_core_service import TicketCoreService

        ticket = _get_ticket_or_raise(ticket_id)

        to_worker = db.session.get(Worker, to_worker_id)
        if not to_worker or not to_worker.is_active:
            raise WorkerNotFoundError(
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
        TicketCoreService.create_notification(
            user_id=to_worker_id,
            message=(
                f"Ticket #{ticket.id} wurde Ihnen zugewiesen "
                f"(von {from_name})."
            ),
            link=f"/ticket/{ticket.id}",
        )
        db.session.commit()
        return ticket
