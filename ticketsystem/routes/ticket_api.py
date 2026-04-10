"""JSON API endpoints for ticket operations.

Covers status changes, assignment, meta updates, contact updates,
attachments, approval actions, and ticket duplication.
"""

import os
from typing import Any

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    request,
    send_from_directory,
    session,
)

from enums import TicketPriority, TicketStatus
from extensions import Config, db, limiter
from models import Attachment
from routes.auth import (
    admin_or_management_required,
    admin_required,
    redirect_to,
    worker_required,
    write_required,
)
from services._helpers import api_endpoint, api_error, api_ok
from services.ticket_approval_service import TicketApprovalService
from services.ticket_assignment_service import TicketAssignmentService
from services.ticket_core_service import TicketCoreService

from ._helpers import (
    _check_ticket_access,
    _parse_callback_due,
    _parse_date,
    _safe_int,
    check_approval_lock,
    is_approval_locked,
)


# ------------------------------------------------------------------
# Comment & status APIs
# ------------------------------------------------------------------

@worker_required
@write_required
@limiter.limit("20 per minute")
def _add_comment_view(ticket_id: int) -> Response:
    """Add a comment to a ticket."""
    worker_id = session.get("worker_id")
    role = session.get("role")
    ticket = _check_ticket_access(ticket_id, worker_id, role)
    if not ticket:
        flash("Ticket nicht gefunden.", "error")
        return redirect_to("main.index")

    if is_approval_locked(ticket):
        flash(
            "Ticket ist für die Freigabe gesperrt. "
            "Kommentare sind während der Prüfung nicht erlaubt.",
            "warning",
        )
        return redirect_to(
            "main.ticket_detail", ticket_id=ticket_id, _anchor="comment-form",
        )

    text = request.form.get("text")
    if text:
        author = session.get("worker_name", "System")
        TicketCoreService.add_comment(ticket_id, author, worker_id, text)
        flash("Kommentar hinzugefügt.", "success")
    return redirect_to(
        "main.ticket_detail", ticket_id=ticket_id, _anchor="comment-form",
    )


@worker_required
@write_required
@limiter.limit("20 per minute")
@api_endpoint
def _update_status_api(ticket_id: int) -> tuple[Response, int] | Response:
    """AJAX status update."""
    worker_id = session.get("worker_id")
    role = session.get("role")
    ticket = _check_ticket_access(ticket_id, worker_id, role)
    if not ticket:
        return api_error("Keine Berechtigung", 403)

    lock_err = check_approval_lock(ticket_id=ticket_id)
    if lock_err:
        return lock_err

    data: dict[str, Any] = request.get_json(silent=True) or {}
    new_status = data.get("status")
    if not new_status:
        return api_error("Kein Status angegeben", 400)

    valid_statuses = {s.value for s in TicketStatus}
    if new_status not in valid_statuses:
        return api_error(f"Ungültiger Status: {new_status}", 400)

    if new_status == TicketStatus.ERLEDIGT.value and ticket.checklists:
        open_items = [c for c in ticket.checklists if not c.is_completed]
        if open_items:
            return api_error(
                f"Ticket kann nicht geschlossen werden: "
                f"{len(open_items)} offene Checklisten-Aufgabe(n).",
                400,
            )

    author = session.get("worker_name", "System")
    TicketCoreService.update_status(ticket_id, new_status, author, worker_id)
    return api_ok()


# ------------------------------------------------------------------
# Assignment APIs
# ------------------------------------------------------------------

@worker_required
@write_required
@limiter.limit("20 per minute")
@api_endpoint
def _assign_ticket_api(ticket_id: int) -> tuple[Response, int] | Response:
    """AJAX ticket assignment."""
    current_worker_id = session.get("worker_id")
    role = session.get("role")
    ticket = _check_ticket_access(ticket_id, current_worker_id, role)
    if not ticket:
        return api_error("Keine Berechtigung", 403)

    lock_err = check_approval_lock(ticket_id=ticket_id)
    if lock_err:
        return lock_err

    data: dict[str, Any] = request.get_json(silent=True) or {}
    target_worker_id = _safe_int(data.get("worker_id"))
    team_id = _safe_int(data.get("team_id"))

    author = session.get("worker_name", "System")
    TicketAssignmentService.assign_ticket(
        ticket_id, target_worker_id, author,
        current_worker_id, team_id=team_id,
    )
    return api_ok()


@worker_required
@write_required
def _assign_to_me_view(ticket_id: int) -> str | Response:
    """Assign the ticket to the current logged-in worker."""
    worker_id = session.get("worker_id")
    role = session.get("role")
    ticket = _check_ticket_access(ticket_id, worker_id, role)
    if not ticket:
        return "", 404

    if is_approval_locked(ticket):
        flash("Ticket ist für die Freigabe gesperrt.", "error")
        return redirect_to("main.ticket_detail", ticket_id=ticket_id)

    if worker_id:
        author = session.get("worker_name", "System")
        TicketAssignmentService.assign_ticket(ticket_id, worker_id, author, worker_id)
        flash("Ticket wurde Ihnen zugewiesen.", "success")

    return redirect_to("main.ticket_detail", ticket_id=ticket_id)


@admin_or_management_required
@limiter.limit("30 per minute")
@api_endpoint
def _reassign_ticket_api(ticket_id: int) -> tuple[Response, int] | Response:
    """Reassign a single ticket to another worker."""
    data: dict[str, Any] = request.get_json(silent=True) or {}
    to_worker_id = _safe_int(data.get("to_worker_id"))

    if not to_worker_id:
        return api_error("Ziel-Mitarbeiter fehlt.", 400)

    author = session.get("worker_name", "System")
    worker_id = session.get("worker_id")
    TicketAssignmentService.reassign_ticket(
        ticket_id, to_worker_id, author, worker_id,
    )
    return api_ok()


# ------------------------------------------------------------------
# Ticket meta update & contact
# ------------------------------------------------------------------

@worker_required
@write_required
@limiter.limit("20 per minute")
@api_endpoint
def _update_ticket_api(ticket_id: int) -> tuple[Response, int] | Response:
    """Handle ticket meta updates (title, priority, due_date, tags)."""
    worker_id = session.get("worker_id")
    role = session.get("role")
    ticket = _check_ticket_access(ticket_id, worker_id, role)
    if not ticket:
        return api_error("Keine Berechtigung", 403)

    lock_err = check_approval_lock(ticket_id=ticket_id)
    if lock_err:
        return lock_err

    data: dict[str, Any] = request.get_json(silent=True) or {}

    new_title = data.get("title")
    if not new_title:
        return api_error("Titel fehlt", 400)

    new_prio = data.get("priority")
    if new_prio is None:
        return api_error("Priorität fehlt", 400)

    try:
        TicketPriority(int(new_prio))
    except (ValueError, TypeError):
        return api_error(f"Ungültige Priorität: {new_prio}", 400)

    raw_due = data.get("due_date")
    due_date = _parse_date(raw_due)
    if raw_due and not due_date:
        return api_error("Ungültiges Datumsformat für Fälligkeit.", 400)
    raw_reminder = data.get("reminder_date")
    reminder_date = _parse_date(raw_reminder)
    if raw_reminder and not reminder_date:
        return api_error("Ungültiges Datumsformat für Erinnerung.", 400)

    author = session.get("worker_name", "System")
    TicketCoreService.update_ticket_meta(
        ticket_id,
        new_title,
        new_prio,
        author,
        worker_id,
        due_date=due_date,
        order_reference=data.get("order_reference"),
        reminder_date=reminder_date,
        tags=data.get("tags"),
        recurrence_rule=data.get("recurrence_rule"),
    )
    return api_ok()


@worker_required
@write_required
@limiter.limit("20 per minute")
@api_endpoint
def _update_contact_api(ticket_id: int) -> tuple[Response, int] | Response:
    """Update customer contact fields on a ticket."""
    worker_id = session.get("worker_id")
    role = session.get("role")
    ticket = _check_ticket_access(ticket_id, worker_id, role)
    if not ticket:
        return api_error("Keine Berechtigung", 403)

    data: dict[str, Any] = request.get_json(silent=True) or {}
    callback_due_str = data.get("callback_due")

    from services._ticket_helpers import ContactInfo
    TicketCoreService.update_contact(
        ticket_id,
        ContactInfo(
            name=data.get("contact_name") or None,
            phone=data.get("contact_phone") or None,
            email=data.get("contact_email") or None,
            channel=data.get("contact_channel") or None,
            callback_requested=bool(data.get("callback_requested", False)),
            callback_due=_parse_callback_due(callback_due_str) if callback_due_str else None,
        ),
    )
    return api_ok()


# ------------------------------------------------------------------
# Attachment serving & deletion
# ------------------------------------------------------------------

@worker_required
def _serve_attachment(attachment_id: int) -> Response | tuple[str, int]:
    """Securely serve uploaded attachments."""
    attachment = db.session.get(Attachment, attachment_id)
    if not attachment:
        return "Not Found", 404

    ticket = attachment.ticket
    if ticket:
        if ticket.is_deleted:
            return "Forbidden", 403
        if ticket.is_confidential and not ticket.is_accessible_by(
            session.get("worker_id"), session.get("role"),
        ):
            return "Forbidden", 403

    data_dir = current_app.config.get("DATA_DIR", Config.get_data_dir())
    attachments_dir = os.path.join(data_dir, "attachments")

    safe_filename = os.path.basename(attachment.path)
    if not safe_filename or safe_filename in (".", ".."):
        return "Invalid Path", 400

    return send_from_directory(attachments_dir, safe_filename)


@worker_required
@write_required
@limiter.limit("20 per minute")
@api_endpoint
def _delete_attachment_api(attachment_id: int) -> tuple[Response, int] | Response:
    """Delete an attachment from a ticket."""
    attachment = db.session.get(Attachment, attachment_id)
    if not attachment:
        return api_error("Anhang nicht gefunden.", 404)

    ticket = attachment.ticket
    if not ticket:
        return api_error("Ticket nicht gefunden.", 404)

    # Only ticket author or admin can delete
    wid = session.get("worker_id")
    role = session.get("role")
    if not ticket._worker_is_author(wid) and role != "admin":
        return api_error("Keine Berechtigung.", 403)

    db.session.delete(attachment)
    db.session.commit()
    return api_ok()


# ------------------------------------------------------------------
# Approval APIs
# ------------------------------------------------------------------

@worker_required
@write_required
@limiter.limit("20 per minute")
@api_endpoint
def _request_approval_api(ticket_id: int) -> tuple[Response, int] | Response:
    """Request management approval for a ticket."""
    worker_id = session.get("worker_id")
    author = session.get("worker_name", "System")
    TicketApprovalService.request_approval(ticket_id, worker_id, author)
    return api_ok()


@worker_required
@admin_required
@limiter.limit("20 per minute")
@api_endpoint
def _approve_ticket_api(ticket_id: int) -> tuple[Response, int] | Response:
    """Approve a pending ticket."""
    worker_id = session.get("worker_id")
    author = session.get("worker_name", "System")
    TicketApprovalService.approve_ticket(ticket_id, worker_id, author)
    return api_ok()


@worker_required
@admin_required
@limiter.limit("20 per minute")
@api_endpoint
def _reject_ticket_api(ticket_id: int) -> tuple[Response, int] | Response:
    """Reject a pending ticket (reason required)."""
    data: dict[str, Any] = request.get_json(silent=True) or {}
    reason = data.get("reason")
    if not reason:
        return api_error("Ablehnungsgrund fehlt.", 400)

    worker_id = session.get("worker_id")
    author = session.get("worker_name", "System")
    TicketApprovalService.reject_ticket(ticket_id, worker_id, author, reason)
    return api_ok()


# ------------------------------------------------------------------
# Duplicate ticket
# ------------------------------------------------------------------

@worker_required
@write_required
@api_endpoint
def _duplicate_ticket_api(ticket_id: int) -> Response:
    """Create a copy of a ticket (metadata only, without comments/history)."""
    worker_id = session.get("worker_id")
    role = session.get("role")
    ticket = _check_ticket_access(ticket_id, worker_id, role)
    if ticket is None:
        return api_error("Ticket nicht gefunden oder keine Berechtigung.", 404)

    new_ticket = TicketCoreService.duplicate_ticket(ticket_id)
    return api_ok(ticket_id=new_ticket.id)


def register_routes(bp: Blueprint) -> None:
    """Register API routes for ticket operations."""
    bp.add_url_rule(
        "/ticket/<int:ticket_id>/comment", "add_comment",
        view_func=_add_comment_view, methods=["POST"],
    )
    bp.add_url_rule(
        "/ticket/<int:ticket_id>/assign_me", "assign_to_me",
        view_func=_assign_to_me_view, methods=["POST"],
    )
    bp.add_url_rule(
        "/api/ticket/<int:ticket_id>/status", "update_status",
        view_func=_update_status_api, methods=["POST"],
    )
    bp.add_url_rule(
        "/api/ticket/<int:ticket_id>/assign", "assign_ticket_api",
        view_func=_assign_ticket_api, methods=["POST"],
    )
    bp.add_url_rule(
        "/api/ticket/<int:ticket_id>/update", "update_ticket",
        view_func=_update_ticket_api, methods=["POST"],
    )
    bp.add_url_rule(
        "/api/ticket/<int:ticket_id>/update_contact", "update_contact",
        view_func=_update_contact_api, methods=["POST"],
    )
    bp.add_url_rule(
        "/api/ticket/<int:ticket_id>/reassign", "reassign_ticket_api",
        view_func=_reassign_ticket_api, methods=["POST"],
    )
    bp.add_url_rule(
        "/attachment/<int:attachment_id>", "serve_attachment",
        view_func=_serve_attachment,
    )
    bp.add_url_rule(
        "/api/attachment/<int:attachment_id>", "delete_attachment",
        view_func=_delete_attachment_api, methods=["DELETE"],
    )
    bp.add_url_rule(
        "/api/ticket/<int:ticket_id>/request_approval",
        "request_approval_api",
        view_func=_request_approval_api, methods=["POST"],
    )
    bp.add_url_rule(
        "/api/ticket/<int:ticket_id>/approve", "approve_ticket_api",
        view_func=_approve_ticket_api, methods=["POST"],
    )
    bp.add_url_rule(
        "/api/ticket/<int:ticket_id>/reject", "reject_ticket_api",
        view_func=_reject_ticket_api, methods=["POST"],
    )
    bp.add_url_rule(
        "/api/ticket/<int:ticket_id>/duplicate", "duplicate_ticket_api",
        view_func=_duplicate_ticket_api, methods=["POST"],
    )
