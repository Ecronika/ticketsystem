"""CSV export and bulk action endpoints."""

import csv
import io
from typing import Any

from flask import Blueprint, Response, request, session, stream_with_context

from enums import ELEVATED_ROLES, ApprovalStatus, TicketPriority, TicketStatus
from extensions import db, limiter
from models import Comment, Team, Ticket
from routes.auth import worker_required, write_required
from services._helpers import api_endpoint, api_error, api_ok
from services.dashboard_service import DashboardService
from services.ticket_assignment_service import TicketAssignmentService
from services.ticket_core_service import TicketCoreService
from utils import get_utc_now

from ._helpers import (
    _PRIO_LABELS,
    _check_ticket_access,
    _parse_date,
    _safe_int,
    is_approval_locked,
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

    worker_id = session.get("worker_id")
    author = session.get("worker_name", "System")

    # Snapshot prev_state BEFORE applying reversible actions so the client can
    # offer a one-click "Rückgängig" toast.
    prev_state: dict[str, Any] | None = None
    if action in ("status_change", "reassign", "set_priority"):
        worker_role = session.get("role")
        tickets_snapshot = [
            db.session.get(Ticket, tid)
            for tid in ticket_ids
        ]
        prev_state = {
            str(t.id): {
                "status": t.status,
                "assigned_to_id": t.assigned_to_id,
                "assigned_team_id": t.assigned_team_id,
                "priority": t.priority,
                "wait_reason": t.wait_reason,
            }
            for t in tickets_snapshot
            if t and not t.is_deleted and t.is_accessible_by(worker_id, worker_role)
        }

    updated = _execute_bulk_action(ticket_ids, action, data, worker_id, author)
    payload: dict[str, Any] = {"updated": updated}
    if prev_state:
        payload["prev_state"] = prev_state
    return api_ok(**payload)


def _execute_bulk_action(
    ticket_ids: list[int],
    action: str,
    data: dict[str, Any],
    worker_id: int | None,
    author: str,
) -> int:
    """Apply *action* to each ticket in *ticket_ids*.  Returns count."""
    updated = 0
    worker_role = session.get("role")
    for tid in ticket_ids:
        ticket = db.session.get(Ticket, tid)
        if not ticket or ticket.is_deleted:
            continue
        if not ticket.is_accessible_by(worker_id, worker_role):
            continue

        if action == "status_change":
            updated += _bulk_status_change(ticket, data, author, worker_id)
        elif action == "reassign":
            updated += _bulk_reassign(ticket, data, author, worker_id)
        elif action == "soft_delete":
            if is_approval_locked(ticket):
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
            TicketCoreService.delete_ticket(
                ticket.id, author_name=author, author_id=worker_id,
            )
            updated += 1
        elif action == "set_due_date":
            updated += _bulk_set_due_date(ticket, data)
        elif action == "set_priority":
            updated += _bulk_set_priority(ticket, data)
    db.session.commit()
    return updated


def _bulk_status_change(
    ticket: Ticket, data: dict[str, Any], author: str, worker_id: int | None,
) -> int:
    """Apply a status change to *ticket*.  Returns 1 on success, 0 otherwise."""
    new_status = data.get("new_status")
    valid = {s.value for s in TicketStatus}
    if new_status and new_status in valid:
        TicketCoreService.update_status(ticket.id, new_status, author, worker_id)
        return 1
    return 0


def _bulk_reassign(
    ticket: Ticket, data: dict[str, Any], author: str, worker_id: int | None,
) -> int:
    """Reassign *ticket*.  Returns 1 on success."""
    target_worker_id = _safe_int(data.get("worker_id"))
    team_id = _safe_int(data.get("team_id"))
    TicketAssignmentService.assign_ticket(
        ticket.id, target_worker_id, author, worker_id, team_id=team_id,
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
# Bulk restore (undo for status_change / reassign / set_priority)
# ------------------------------------------------------------------

@worker_required
@write_required
@limiter.limit("20 per minute")
@api_endpoint
def _bulk_restore_state_api() -> tuple[Response, int] | Response:
    """Restore a bulk before-state produced by a previous /api/tickets/bulk call."""
    payload = request.get_json(silent=True) or {}
    prev_state = payload.get("prev_state") or {}
    if not isinstance(prev_state, dict):
        return api_error("prev_state muss ein Objekt sein.", 400)
    restored = 0
    worker_id = session.get("worker_id")
    role = session.get("role")
    for ticket_id_str, state in prev_state.items():
        try:
            tid = int(ticket_id_str)
        except (TypeError, ValueError):
            continue
        ticket = _check_ticket_access(tid, worker_id, role)
        if not ticket:
            continue
        ticket.status = state.get("status", ticket.status)
        ticket.assigned_to_id = state.get("assigned_to_id")
        ticket.assigned_team_id = state.get("assigned_team_id")
        ticket.priority = state.get("priority", ticket.priority)
        ticket.wait_reason = state.get("wait_reason")
        restored += 1
    db.session.commit()
    return api_ok(restored=restored)


# ------------------------------------------------------------------
# CSV exports
# ------------------------------------------------------------------

@worker_required
def _export_archive_csv() -> Response:
    """Export archive tickets as a streaming CSV download."""
    search = request.args.get("q", "").strip()
    author = request.args.get("author", "").strip()
    worker_id = session.get("worker_id")
    worker_role = session.get("role")
    is_elevated = worker_role in ELEVATED_ROLES

    query = Ticket.query.filter(
        Ticket.is_deleted.is_(False),
        Ticket.status == TicketStatus.ERLEDIGT.value,
    )

    if not is_elevated and worker_id is not None:
        from services._ticket_helpers import _confidential_filter
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
        from services._ticket_helpers import apply_search_filter
        query = apply_search_filter(query, search)

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
    projects = DashboardService.get_projects_summary()

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
        "/api/tickets/bulk/restore", "bulk_restore_state",
        view_func=_bulk_restore_state_api, methods=["POST"],
    )
    bp.add_url_rule(
        "/api/export/archive", "export_archive_csv",
        view_func=_export_archive_csv,
    )
    bp.add_url_rule(
        "/api/export/projects", "export_projects_csv",
        view_func=_export_projects_csv,
    )
