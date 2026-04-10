"""CSV export and bulk action endpoints."""

import csv
import io
from typing import Any

from flask import Blueprint, Response, request, session, stream_with_context

from enums import ELEVATED_ROLES, ApprovalStatus, TicketPriority, TicketStatus
from extensions import db, limiter
from models import Comment, Team, Ticket, TicketContact
from routes.auth import worker_required, write_required
from services import TicketService
from services._helpers import api_endpoint, api_error, api_ok
from utils import get_utc_now

from ._helpers import (
    _PRIO_LABELS,
    _parse_date,
    _safe_int,
    _session_author,
    _session_worker_id,
)


# ------------------------------------------------------------------
# Bulk actions
# ------------------------------------------------------------------

@worker_required
@write_required
@api_endpoint
def _bulk_action_api() -> tuple[Response, int] | Response:
    """Handle bulk operations on multiple tickets."""
    data: dict[str, Any] = request.get_json(silent=True) or {}
    ticket_ids: list[int] = data.get("ticket_ids", [])
    action: str | None = data.get("action")

    if not ticket_ids or not action:
        return api_error("Keine Tickets oder Aktion angegeben.", 400)

    updated = _execute_bulk_action(ticket_ids, action, data)
    db.session.commit()
    return api_ok(updated=updated)


def _execute_bulk_action(
    ticket_ids: list[int],
    action: str,
    data: dict[str, Any],
) -> int:
    """Apply *action* to each ticket in *ticket_ids*.  Returns count."""
    updated = 0
    worker_id = _session_worker_id()
    worker_role = session.get("role")
    for tid in ticket_ids:
        ticket = db.session.get(Ticket, tid)
        if not ticket or ticket.is_deleted:
            continue
        if not ticket.is_accessible_by(worker_id, worker_role):
            continue

        if action == "status_change":
            updated += _bulk_status_change(ticket, data)
        elif action == "reassign":
            updated += _bulk_reassign(ticket, data)
        elif action == "soft_delete":
            if ticket.approval and ticket.approval.status == ApprovalStatus.PENDING.value:
                ticket.approval.status = ApprovalStatus.REJECTED.value
                db.session.add(Comment(
                    ticket_id=ticket.id,
                    author="System",
                    text=(
                        "Freigabe-Anfrage automatisch abgelehnt: "
                        "Ticket wurde gelöscht."
                    ),
                    is_system_event=True,
                ))
            TicketService.delete_ticket(
                ticket.id,
                author_name=_session_author(),
                author_id=_session_worker_id(),
            )
            updated += 1
        elif action == "set_due_date":
            updated += _bulk_set_due_date(ticket, data)
        elif action == "set_priority":
            updated += _bulk_set_priority(ticket, data)
    return updated


def _bulk_status_change(ticket: Ticket, data: dict[str, Any]) -> int:
    """Apply a status change to *ticket*.  Returns 1 on success, 0 otherwise."""
    new_status = data.get("new_status")
    valid = {s.value for s in TicketStatus}
    if new_status and new_status in valid:
        TicketService.update_status(
            ticket.id, new_status, _session_author(), _session_worker_id(),
        )
        return 1
    return 0


def _bulk_reassign(ticket: Ticket, data: dict[str, Any]) -> int:
    """Reassign *ticket*.  Returns 1 on success."""
    worker_id = _safe_int(data.get("worker_id"))
    team_id = _safe_int(data.get("team_id"))
    TicketService.assign_ticket(
        ticket.id, worker_id, _session_author(),
        _session_worker_id(), team_id=team_id,
    )
    return 1


def _bulk_set_due_date(ticket: Ticket, data: dict[str, Any]) -> int:
    """Set the due date on *ticket*.  Returns 1 on success, 0 otherwise."""
    due_str = data.get("due_date", "")
    due_date = _parse_date(due_str)
    if due_date:
        ticket.due_date = due_date
        ticket.updated_at = get_utc_now()
        return 1
    return 0


def _bulk_set_priority(ticket: Ticket, data: dict[str, Any]) -> int:
    """Set the priority on *ticket*.  Returns 1 on success, 0 otherwise."""
    try:
        new_prio = int(data.get("priority", 0))
        TicketPriority(new_prio)
    except (ValueError, TypeError):
        return 0
    if ticket.priority != new_prio:
        ticket.priority = new_prio
        ticket.updated_at = get_utc_now()
        return 1
    return 0


# ------------------------------------------------------------------
# CSV exports
# ------------------------------------------------------------------

@worker_required
def _export_archive_csv() -> Response:
    """Export archive tickets as a streaming CSV download."""
    search = request.args.get("q", "").strip()
    author = request.args.get("author", "").strip()
    worker_id = _session_worker_id()
    worker_role = session.get("role")
    is_elevated = worker_role in ELEVATED_ROLES

    query = Ticket.query.filter(
        Ticket.is_deleted.is_(False),
        Ticket.status == TicketStatus.ERLEDIGT.value,
    )

    if not is_elevated and worker_id is not None:
        from services.ticket_service import _confidential_filter
        team_ids = Team.team_ids_for_worker(worker_id)
        query = query.filter(db.or_(*_confidential_filter(worker_id, team_ids)))

    if author:
        author_sub = (
            db.session.query(Comment.ticket_id)
            .filter(
                Comment.event_type == "TICKET_CREATED",
                Comment.author.ilike(f"%{author}%"),
            )
            .subquery()
        )
        query = query.filter(Ticket.id.in_(author_sub))

    if search:
        tokens = search.split()
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
                | Ticket.contact.has(TicketContact.name.ilike(pattern))
                | Ticket.contact.has(TicketContact.email.ilike(pattern))
                | Ticket.contact.has(TicketContact.phone.ilike(pattern))
                | Ticket.id.in_(comment_ids)
            )

    query = query.order_by(Ticket.priority.asc(), Ticket.created_at.desc())

    @stream_with_context
    def generate():
        buf = io.StringIO()
        buf.write("\ufeff")  # BOM for Excel UTF-8
        writer = csv.writer(buf, delimiter=";")
        writer.writerow([
            "ID", "Titel", "Beschreibung", "Status", "Priorität",
            "Erstellt am", "Aktualisiert am", "Auftragsnummer",
        ])
        yield buf.getvalue()

        for ticket in query.yield_per(100):
            buf = io.StringIO()
            writer = csv.writer(buf, delimiter=";")
            writer.writerow(_archive_csv_row(ticket))
            yield buf.getvalue()

    return Response(
        generate(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=archiv_export.csv",
            "X-Accel-Buffering": "no",
        },
    )


def _archive_csv_row(ticket: Ticket) -> list[str]:
    """Build a single CSV row for an archive ticket."""
    return [
        str(ticket.id),
        ticket.title,
        (ticket.description or "")[:200],
        ticket.status,
        _PRIO_LABELS.get(ticket.priority, str(ticket.priority)),
        ticket.created_at.strftime("%d.%m.%Y %H:%M") if ticket.created_at else "",
        ticket.updated_at.strftime("%d.%m.%Y %H:%M") if ticket.updated_at else "",
        ticket.order_reference or "",
    ]


@worker_required
def _export_projects_csv() -> Response:
    """Export projects summary as CSV download."""
    projects = TicketService.get_projects_summary()

    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "Auftragsnummer", "Gesamt Tickets", "Offen", "In Bearbeitung",
        "Wartet", "Erledigt", "Fortschritt %", "Status",
    ])

    for proj in projects:
        sc = proj.status_counts
        get = sc.get if hasattr(sc, "get") else lambda k, d=0: getattr(sc, k, d)
        writer.writerow([
            proj.order_reference,
            proj.total_tickets,
            get("offen", 0),
            get("in_bearbeitung", 0),
            get("wartet", 0),
            proj.completed_tickets,
            proj.progress,
            "Abgeschlossen" if proj.is_completed else "Aktiv",
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=projekte_export.csv",
        },
    )


def register_routes(bp: Blueprint) -> None:
    """Register export and bulk-action routes."""
    bp.add_url_rule(
        "/api/tickets/bulk", "bulk_action_api",
        view_func=_bulk_action_api, methods=["POST"],
    )
    bp.add_url_rule(
        "/api/export/archive", "export_archive_csv",
        view_func=_export_archive_csv,
    )
    bp.add_url_rule(
        "/api/export/projects", "export_projects_csv",
        view_func=_export_projects_csv,
    )
