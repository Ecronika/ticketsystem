"""Checklist API endpoints for ticket sub-tasks."""

from typing import Any

from flask import Blueprint, Response, request, session

from extensions import db, limiter
from models import ChecklistItem
from routes.auth import worker_required, write_required
from services.checklist_service import ChecklistService
from services._helpers import api_endpoint, api_error, api_ok

from ._helpers import (
    _check_ticket_access,
    _parse_date,
    _safe_int,
    check_approval_lock,
)


@worker_required
@write_required
@limiter.limit("20 per minute")
@api_endpoint
def _add_checklist_api(ticket_id: int) -> tuple[Response, int] | Response:
    """Add a checklist item to a ticket."""
    worker_id = session.get("worker_id")
    role = session.get("role")
    ticket = _check_ticket_access(ticket_id, worker_id, role)
    if ticket is None:
        return api_error("Kein Zugriff auf dieses Ticket.", 403)

    lock_err = check_approval_lock(ticket_id=ticket_id)
    if lock_err:
        return lock_err

    data: dict[str, Any] = request.get_json(silent=True) or {}
    title = data.get("title")
    if not title:
        return api_error("Titel fehlt", 400)

    item = ChecklistService.add_checklist_item(
        ticket_id,
        title,
        _safe_int(data.get("assigned_to_id")),
        assigned_team_id=_safe_int(data.get("assigned_team_id")),
        due_date=_parse_date(data.get("due_date")),
        depends_on_item_id=_safe_int(data.get("depends_on_item_id")),
    )
    return api_ok(item_id=item.id)


@worker_required
@write_required
@limiter.limit("40 per minute")
@api_endpoint
def _toggle_checklist_api(item_id: int) -> tuple[Response, int] | Response:
    """Toggle a checklist item's completion state."""
    worker_id = session.get("worker_id")
    role = session.get("role")

    item = db.session.get(ChecklistItem, item_id)
    if item:
        ticket = _check_ticket_access(item.ticket_id, worker_id, role)
        if ticket is None:
            return api_error("Kein Zugriff auf dieses Ticket.", 403)

    lock_err = check_approval_lock(item_id=item_id)
    if lock_err:
        return lock_err

    author = session.get("worker_name", "System")
    item = ChecklistService.toggle_checklist_item(
        item_id, worker_name=author, worker_id=worker_id,
    )
    return api_ok(is_completed=item.is_completed if item else False)


@worker_required
@write_required
@limiter.limit("20 per minute")
@api_endpoint
def _delete_checklist_api(item_id: int) -> tuple[Response, int] | Response:
    """Delete a checklist item."""
    worker_id = session.get("worker_id")
    role = session.get("role")
    item = db.session.get(ChecklistItem, item_id)
    if item:
        ticket = _check_ticket_access(item.ticket_id, worker_id, role)
        if ticket is None:
            return api_error("Kein Zugriff auf dieses Ticket.", 403)

    lock_err = check_approval_lock(item_id=item_id)
    if lock_err:
        return lock_err

    ChecklistService.delete_checklist_item(item_id)
    return api_ok()


@worker_required
@write_required
@limiter.limit("30 per minute")
@api_endpoint
def _reorder_checklist_api(ticket_id: int) -> tuple[Response, int] | Response:
    """Reorder checklist items for a ticket."""
    worker_id = session.get("worker_id")
    role = session.get("role")
    ticket = _check_ticket_access(ticket_id, worker_id, role)
    if ticket is None:
        return api_error("Kein Zugriff auf dieses Ticket.", 403)

    data: dict[str, Any] = request.get_json(silent=True) or {}
    order = data.get("order", [])
    if not isinstance(order, list):
        return api_error("Ungültige Reihenfolge.", 400)

    ChecklistService.reorder_items(ticket_id, order)
    return api_ok()


@worker_required
@write_required
@api_endpoint
def _apply_template_api(ticket_id: int) -> tuple[Response, int] | Response:
    """Apply a checklist template to an existing ticket."""
    worker_id = session.get("worker_id")
    role = session.get("role")
    ticket = _check_ticket_access(ticket_id, worker_id, role)
    if ticket is None:
        return api_error("Kein Zugriff auf dieses Ticket.", 403)

    lock_err = check_approval_lock(ticket_id=ticket_id)
    if lock_err:
        return lock_err

    data: dict[str, Any] = request.get_json(silent=True) or {}
    template_id = data.get("template_id")
    if not template_id:
        return api_error("Keine Vorlage ausgewählt.", 400)

    ChecklistService.apply_checklist_template(ticket_id, template_id)
    return api_ok()


def register_routes(bp: Blueprint) -> None:
    """Register checklist API routes."""
    bp.add_url_rule(
        "/api/ticket/<int:ticket_id>/checklist", "add_checklist",
        view_func=_add_checklist_api, methods=["POST"],
    )
    bp.add_url_rule(
        "/api/checklist/<int:item_id>/toggle", "toggle_checklist",
        view_func=_toggle_checklist_api, methods=["POST"],
    )
    bp.add_url_rule(
        "/api/checklist/<int:item_id>", "delete_checklist",
        view_func=_delete_checklist_api, methods=["DELETE"],
    )
    bp.add_url_rule(
        "/api/ticket/<int:ticket_id>/checklist/reorder", "reorder_checklist",
        view_func=_reorder_checklist_api, methods=["POST"],
    )
    bp.add_url_rule(
        "/api/ticket/<int:ticket_id>/apply_template", "apply_template",
        view_func=_apply_template_api, methods=["POST"],
    )
