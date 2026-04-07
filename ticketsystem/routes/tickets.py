"""Ticket routes.

Handles ticket CRUD, public ticket view, queue, approvals, project
views, bulk actions, CSV exports, and notification endpoints.
"""

import csv
import io
import os
from datetime import datetime, timezone
from typing import Any

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    stream_with_context,
    url_for,
)
from markupsafe import Markup
from sqlalchemy.exc import SQLAlchemyError

from enums import ApprovalStatus, TicketPriority, TicketStatus, WorkerRole
from extensions import Config, db, limiter
from models import (
    Attachment,
    ChecklistItem,
    ChecklistTemplate,
    Comment,
    Notification,
    Team,
    Ticket,
    Worker,
)
from routes.auth import (
    admin_or_management_required,
    admin_required,
    redirect_to,
    worker_required,
)
from services import TicketService
from utils import get_utc_now

_ELEVATED_ROLES = frozenset({
    WorkerRole.ADMIN.value,
    WorkerRole.HR.value,
    WorkerRole.MANAGEMENT.value,
})

_PRIO_LABELS: dict[int, str] = {1: "Hoch", 2: "Mittel", 3: "Niedrig"}


# ------------------------------------------------------------------
# Shared helpers
# ------------------------------------------------------------------

def _session_author() -> str:
    """Return the current session's worker name or ``'System'``."""
    return session.get("worker_name", "System")


def _session_worker_id() -> int | None:
    """Return the current session's worker id."""
    return session.get("worker_id")


def _api_error(msg: str, status: int = 500) -> tuple[Response, int]:
    """Return a JSON error response."""
    return jsonify({"success": False, "error": msg}), status


def _api_ok(**extra: Any) -> Response:
    """Return a JSON success response with optional extra keys."""
    return jsonify({"success": True, **extra})


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

    if ticket and ticket.approval_status == ApprovalStatus.PENDING.value:
        return _api_error("Ticket ist für die Freigabe gesperrt.", 403)
    return None


# ------------------------------------------------------------------
# Form parsing helpers (extracted from _new_ticket_view)
# ------------------------------------------------------------------

def _parse_callback_due(raw: str) -> datetime | None:
    """Parse a callback-due datetime string to naive UTC."""
    if not raw:
        return None
    from zoneinfo import ZoneInfo

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


def _parse_date(raw: str | None, fmt: str = "%Y-%m-%d") -> datetime | None:
    """Parse a date string; return ``None`` on failure."""
    if not raw:
        return None
    try:
        clean = raw.split("T")[0]
        return datetime.strptime(clean, fmt)
    except (ValueError, TypeError, IndexError):
        return None


# ------------------------------------------------------------------
# Dashboard & Archive views
# ------------------------------------------------------------------

def _dashboard_view() -> str | Response:
    """Main dashboard view."""
    worker_id = _session_worker_id()
    search = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    per_page = min(max(per_page, 10), 100)  # clamp 10..100
    assigned_to_me = request.args.get("assigned_to_me") == "1"
    unassigned_only = request.args.get("unassigned") == "1"
    callback_pending = request.args.get("callback_pending") == "1"
    assigned_worker_id = request.args.get("worker_id", type=int)
    sort_by = request.args.get("sort", "")
    sort_dir = request.args.get("dir", "asc")
    if sort_dir not in ("asc", "desc"):
        sort_dir = "asc"

    # Active tab: "all" (default), "unassigned", "callback", "wartet"
    tab = request.args.get("tab", "all")

    if search.startswith("#") and search[1:].isdigit():
        return redirect_to("main.ticket_detail", ticket_id=int(search[1:]))

    # Derive filters from active tab
    if tab == "unassigned":
        unassigned_only = True
    elif tab == "callback":
        callback_pending = True
    elif tab == "wartet":
        status_filter = status_filter or "wartet"

    team_ids = Team.team_ids_for_worker(worker_id) if worker_id else []
    tickets_data = TicketService.get_dashboard_tickets(
        worker_id=worker_id,
        search=search,
        status_filter=status_filter,
        page=page,
        per_page=per_page,
        assigned_to_me=assigned_to_me,
        unassigned_only=unassigned_only,
        callback_pending=callback_pending,
        worker_role=session.get("role"),
        team_ids=team_ids,
        assigned_worker_id=assigned_worker_id,
        sort_by=sort_by or None,
        sort_dir=sort_dir,
    )

    all_workers = Worker.query.filter_by(is_active=True).order_by(Worker.name).all()
    all_teams = Team.query.order_by(Team.name).all()

    return render_template(
        "index.html",
        pagination=tickets_data["focus_pagination"],
        focus_tickets=tickets_data["focus_pagination"].items,
        summary_counts=tickets_data["summary_counts"],
        query=search,
        current_status=status_filter,
        assigned_to_me=assigned_to_me,
        unassigned_only=unassigned_only,
        callback_pending=callback_pending,
        today=get_utc_now(),
        workers=all_workers,
        teams=all_teams,
        active_tab=tab,
        sort_by=sort_by,
        sort_dir=sort_dir,
        per_page=per_page,
    )


def _archive_view() -> str:
    """Completed-tickets archive view."""
    search = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)
    author = request.args.get("author", "").strip()
    start_date_str = request.args.get("start_date", "")
    end_date_str = request.args.get("end_date", "")

    start_date = _parse_date(start_date_str)
    end_date = _parse_date(end_date_str)
    if end_date:
        end_date = end_date.replace(hour=23, minute=59, second=59)

    wid = _session_worker_id()
    team_ids = Team.team_ids_for_worker(wid) if wid else []
    tickets_data = TicketService.get_dashboard_tickets(
        worker_id=wid,
        search=search,
        status_filter=TicketStatus.ERLEDIGT.value,
        page=page,
        per_page=15,
        start_date=start_date,
        end_date=end_date,
        author_name=author,
        worker_role=session.get("role"),
        team_ids=team_ids,
    )

    return render_template(
        "archive.html",
        pagination=tickets_data["focus_pagination"],
        tickets=tickets_data["focus_pagination"].items,
        query=search,
        author=author,
        start_date=start_date_str,
        end_date=end_date_str,
        current_status=TicketStatus.ERLEDIGT.value,
    )


@admin_or_management_required
def _approvals_view() -> str:
    """Pending-approvals dashboard for management."""
    page = request.args.get("page", 1, type=int)
    pagination = TicketService.get_pending_approvals(page=page)
    return render_template(
        "approvals.html", pagination=pagination, tickets=pagination.items,
    )


def _projects_view() -> str:
    """Project / Baustellen overview."""
    projects = TicketService.get_projects_summary()
    return render_template("projects.html", projects=projects)


# ------------------------------------------------------------------
# Ticket creation
# ------------------------------------------------------------------

def _new_ticket_view() -> str | Response:
    """Handle new ticket creation."""
    if request.method == "POST":
        return _handle_ticket_creation()

    all_workers = Worker.query.filter_by(is_active=True).all()
    all_teams = Team.query.all()
    all_templates = ChecklistTemplate.query.all()
    return render_template(
        "ticket_new.html",
        workers=all_workers,
        teams=all_teams,
        templates=all_templates,
    )


def _handle_ticket_creation() -> str | Response:
    """Process the new-ticket form submission."""
    title = request.form.get("title")
    if not title:
        flash("Bitte einen Titel angeben.", "warning")
        return render_template("ticket_new.html")

    description = request.form.get("description")
    priority_val = request.form.get("priority", "2")
    author_name = request.form.get("author_name") or "Anonym"
    attachments = request.files.getlist("attachments")
    tags_raw = request.form.get("tags", "")
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

    is_confidential = (
        request.form.get("is_confidential") in ("True", "on")
        and bool(_session_worker_id())
    )

    assigned_to_id, assigned_team_id = _parse_assignment_ids(
        request.form.get("assigned_to_id"),
        request.form.get("assigned_team_id"),
    )

    template_id = _safe_int(request.form.get("template_id"))
    due_date = _parse_date(request.form.get("due_date"))
    callback_due = _parse_callback_due(request.form.get("callback_due", ""))

    try:
        priority = TicketPriority(int(priority_val))
        ticket = TicketService.create_ticket(
            title=title,
            description=description,
            priority=priority,
            author_name=author_name,
            author_id=_session_worker_id(),
            attachments=attachments,
            due_date=due_date,
            assigned_to_id=assigned_to_id,
            assigned_team_id=assigned_team_id,
            is_confidential=is_confidential,
            recurrence_rule=request.form.get("recurrence_rule"),
            order_reference=request.form.get("order_reference"),
            tags=tags,
            checklist_template_id=template_id,
            contact_name=request.form.get("contact_name") or None,
            contact_phone=request.form.get("contact_phone") or None,
            contact_email=request.form.get("contact_email") or None,
            contact_channel=request.form.get("contact_channel") or None,
            callback_requested=request.form.get("callback_requested") == "on",
            callback_due=callback_due,
        )
        return _after_ticket_created(ticket)
    except (ValueError, SQLAlchemyError):
        current_app.logger.exception(
            "Fehler beim Erstellen des Tickets (worker=%s)",
            _session_worker_id(),
        )
        flash("Fehler beim Erstellen des Tickets.", "error")
        return render_template("ticket_new.html")


def _after_ticket_created(ticket: Ticket) -> Response:
    """Flash success and redirect after ticket creation."""
    session["last_created_ticket_id"] = ticket.id
    ingress = request.headers.get("X-Ingress-Path", "")
    ticket_url = f"{ingress}{url_for('main.ticket_detail', ticket_id=ticket.id)}"
    link_html = (
        f' <a href="{ticket_url}" class="alert-link">'
        f"Ticket #{ticket.id} ansehen \u2192</a>"
    )

    if not _session_worker_id():
        return redirect_to("main.ticket_new", created=ticket.id)

    flash(Markup(f"Ticket {link_html} erfolgreich erstellt!"), "success")
    return redirect_to("main.index")


# ------------------------------------------------------------------
# Ticket detail & public views
# ------------------------------------------------------------------

@worker_required
def _ticket_detail_view(ticket_id: int) -> str | Response:
    """Ticket detail view."""
    db.session.expire_all()
    ticket = _check_ticket_access(ticket_id)
    if not ticket:
        flash("Ticket nicht gefunden.", "error")
        return redirect_to("main.index")

    all_workers = Worker.query.filter_by(is_active=True).all()
    all_teams = Team.query.all()
    all_templates = ChecklistTemplate.query.all()
    return render_template(
        "ticket_detail.html",
        ticket=ticket,
        workers=all_workers,
        teams=all_teams,
        templates=all_templates,
        has_full_access=True,
        now=get_utc_now(),
    )


@limiter.limit("30 per minute")
def _public_ticket_view(ticket_id: int) -> tuple[str, int] | str:
    """Public read-only status page."""
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.is_deleted or ticket.is_confidential:
        return render_template("404.html"), 404
    return render_template("ticket_public.html", ticket=ticket)


# ------------------------------------------------------------------
# Comment & status APIs
# ------------------------------------------------------------------

@worker_required
@limiter.limit("20 per minute")
def _add_comment_view(ticket_id: int) -> Response:
    """Add a comment to a ticket."""
    ticket = _check_ticket_access(ticket_id)
    if not ticket:
        flash("Ticket nicht gefunden.", "error")
        return redirect_to("main.index")

    if ticket.approval_status == ApprovalStatus.PENDING.value:
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
        TicketService.add_comment(
            ticket_id, _session_author(), _session_worker_id(), text,
        )
        flash("Kommentar hinzugefügt.", "success")
    return redirect_to(
        "main.ticket_detail", ticket_id=ticket_id, _anchor="comment-form",
    )


@worker_required
@limiter.limit("20 per minute")
def _update_status_api(ticket_id: int) -> tuple[Response, int] | Response:
    """AJAX status update."""
    ticket = _check_ticket_access(ticket_id)
    if not ticket:
        return _api_error("Keine Berechtigung", 403)

    lock_err = check_approval_lock(ticket_id=ticket_id)
    if lock_err:
        return lock_err

    data: dict[str, Any] = request.get_json(silent=True) or {}
    new_status = data.get("status")
    if not new_status:
        return _api_error("Kein Status angegeben", 400)

    valid_statuses = {s.value for s in TicketStatus}
    if new_status not in valid_statuses:
        return _api_error(f"Ungültiger Status: {new_status}", 400)

    try:
        TicketService.update_status(
            ticket_id, new_status, _session_author(), _session_worker_id(),
        )
        return _api_ok()
    except SQLAlchemyError:
        current_app.logger.exception("API Error in _update_status_api")
        return _api_error("Ein interner Fehler ist aufgetreten.")


# ------------------------------------------------------------------
# Assignment APIs
# ------------------------------------------------------------------

@worker_required
@limiter.limit("20 per minute")
def _assign_ticket_api(ticket_id: int) -> tuple[Response, int] | Response:
    """AJAX ticket assignment."""
    ticket = _check_ticket_access(ticket_id)
    if not ticket:
        return _api_error("Keine Berechtigung", 403)

    lock_err = check_approval_lock(ticket_id=ticket_id)
    if lock_err:
        return lock_err

    data: dict[str, Any] = request.get_json(silent=True) or {}
    worker_id = _safe_int(str(data.get("worker_id", "")))
    team_id = _safe_int(str(data.get("team_id", "")))

    try:
        TicketService.assign_ticket(
            ticket_id, worker_id, _session_author(),
            _session_worker_id(), team_id=team_id,
        )
        return _api_ok()
    except SQLAlchemyError:
        current_app.logger.exception("API Error in _assign_ticket_api")
        return _api_error("Ein interner Fehler ist aufgetreten.")


@worker_required
def _assign_to_me_view(ticket_id: int) -> str | Response:
    """Assign the ticket to the current logged-in worker."""
    ticket = _check_ticket_access(ticket_id)
    if not ticket:
        return render_template("404.html"), 404

    if ticket.approval_status == ApprovalStatus.PENDING.value:
        flash("Ticket ist für die Freigabe gesperrt.", "error")
        return redirect_to("main.ticket_detail", ticket_id=ticket_id)

    wid = _session_worker_id()
    if wid:
        TicketService.assign_ticket(ticket_id, wid, _session_author(), wid)
        flash("Ticket wurde Ihnen zugewiesen.", "success")

    return redirect_to("main.ticket_detail", ticket_id=ticket_id)


@admin_or_management_required
@limiter.limit("30 per minute")
def _reassign_ticket_api(ticket_id: int) -> tuple[Response, int] | Response:
    """Reassign a single ticket to another worker."""
    data: dict[str, Any] = request.get_json(silent=True) or {}
    to_worker_id = _safe_int(str(data.get("to_worker_id", "")))

    if not to_worker_id:
        return _api_error("Ziel-Mitarbeiter fehlt.", 400)

    try:
        TicketService.reassign_ticket(
            ticket_id, to_worker_id, _session_author(), _session_worker_id(),
        )
        return _api_ok()
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except SQLAlchemyError:
        current_app.logger.exception("API Error in _reassign_ticket_api")
        return _api_error("Interner Fehler.")


# ------------------------------------------------------------------
# Ticket meta update & attachment serving
# ------------------------------------------------------------------

@worker_required
@limiter.limit("20 per minute")
def _update_ticket_api(ticket_id: int) -> tuple[Response, int] | Response:
    """Handle ticket meta updates (title, priority, due_date, tags)."""
    ticket = _check_ticket_access(ticket_id)
    if not ticket:
        return _api_error("Keine Berechtigung", 403)

    lock_err = check_approval_lock(ticket_id=ticket_id)
    if lock_err:
        return lock_err

    data: dict[str, Any] = request.get_json(silent=True) or {}

    new_title = data.get("title")
    if not new_title:
        return _api_error("Titel fehlt", 400)

    new_prio = data.get("priority")
    if new_prio is None:
        return _api_error("Priorität fehlt", 400)

    try:
        TicketPriority(int(new_prio))
    except (ValueError, TypeError):
        return _api_error(f"Ungültige Priorität: {new_prio}", 400)

    due_date = _parse_date(data.get("due_date"))
    reminder_date = _parse_date(data.get("reminder_date"))

    try:
        TicketService.update_ticket_meta(
            ticket_id,
            new_title,
            new_prio,
            _session_author(),
            _session_worker_id(),
            due_date=due_date,
            order_reference=data.get("order_reference"),
            reminder_date=reminder_date,
            tags=data.get("tags"),
            recurrence_rule=data.get("recurrence_rule"),
        )
        return _api_ok()
    except SQLAlchemyError:
        current_app.logger.exception("API Error in _update_ticket_api")
        return _api_error("Ein interner Fehler ist aufgetreten.")


@worker_required
@limiter.limit("20 per minute")
def _update_contact_api(ticket_id: int) -> tuple[Response, int] | Response:
    """Update customer contact fields on a ticket."""
    ticket = _check_ticket_access(ticket_id)
    if not ticket:
        return _api_error("Keine Berechtigung", 403)

    data: dict[str, Any] = request.get_json(silent=True) or {}

    ticket.contact_name = data.get("contact_name") or None
    ticket.contact_phone = data.get("contact_phone") or None
    ticket.contact_email = data.get("contact_email") or None
    ticket.contact_channel = data.get("contact_channel") or None
    ticket.callback_requested = bool(data.get("callback_requested", False))
    callback_due_str = data.get("callback_due")
    ticket.callback_due = _parse_callback_due(callback_due_str) if callback_due_str else None
    ticket.updated_at = get_utc_now()

    try:
        db.session.commit()
        return _api_ok()
    except SQLAlchemyError:
        current_app.logger.exception("API Error in _update_contact_api")
        return _api_error("Ein interner Fehler ist aufgetreten.")


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
            _session_worker_id(), session.get("role"),
        ):
            return "Forbidden", 403

    data_dir = current_app.config.get("DATA_DIR", Config.get_data_dir())
    attachments_dir = os.path.join(data_dir, "attachments")

    safe_filename = os.path.basename(attachment.path)
    if not safe_filename or safe_filename in (".", ".."):
        return "Invalid Path", 400

    return send_from_directory(attachments_dir, safe_filename)


# ------------------------------------------------------------------
# Approval APIs
# ------------------------------------------------------------------

@worker_required
@limiter.limit("20 per minute")
def _request_approval_api(ticket_id: int) -> tuple[Response, int] | Response:
    """Request management approval for a ticket."""
    try:
        TicketService.request_approval(
            ticket_id, _session_worker_id(), _session_author(),
        )
        return _api_ok()
    except SQLAlchemyError:
        current_app.logger.exception("API Error in _request_approval_api")
        return _api_error("Ein interner Fehler ist aufgetreten.")


@admin_required
@limiter.limit("20 per minute")
def _approve_ticket_api(ticket_id: int) -> tuple[Response, int] | Response:
    """Approve a pending ticket."""
    try:
        TicketService.approve_ticket(
            ticket_id, _session_worker_id(), _session_author(),
        )
        return _api_ok()
    except SQLAlchemyError:
        current_app.logger.exception("API Error in _approve_ticket_api")
        return _api_error("Ein interner Fehler ist aufgetreten.")


@admin_required
@limiter.limit("20 per minute")
def _reject_ticket_api(ticket_id: int) -> tuple[Response, int] | Response:
    """Reject a pending ticket (reason required)."""
    data: dict[str, Any] = request.get_json(silent=True) or {}
    reason = data.get("reason")
    if not reason:
        return _api_error("Ablehnungsgrund fehlt.", 400)

    try:
        TicketService.reject_ticket(
            ticket_id, _session_worker_id(), _session_author(), reason,
        )
        return _api_ok()
    except SQLAlchemyError:
        current_app.logger.exception("API Error in _reject_ticket_api")
        return _api_error("Ein interner Fehler ist aufgetreten.")


# ------------------------------------------------------------------
# Checklist APIs
# ------------------------------------------------------------------

@worker_required
@limiter.limit("20 per minute")
def _add_checklist_api(ticket_id: int) -> tuple[Response, int] | Response:
    """Add a checklist item to a ticket."""
    ticket = _check_ticket_access(ticket_id)
    if ticket is None:
        return _api_error("Kein Zugriff auf dieses Ticket.", 403)

    lock_err = check_approval_lock(ticket_id=ticket_id)
    if lock_err:
        return lock_err

    data: dict[str, Any] = request.get_json(silent=True) or {}
    title = data.get("title")
    if not title:
        return _api_error("Titel fehlt", 400)

    try:
        item = TicketService.add_checklist_item(
            ticket_id,
            title,
            _safe_int(str(data.get("assigned_to_id", ""))),
            assigned_team_id=_safe_int(str(data.get("assigned_team_id", ""))),
            due_date=_parse_date(data.get("due_date")),
            depends_on_item_id=_safe_int(
                str(data.get("depends_on_item_id", "")),
            ),
        )
        return _api_ok(item_id=item.id)
    except SQLAlchemyError:
        current_app.logger.exception("API Error in _add_checklist_api")
        return _api_error("Ein interner Fehler ist aufgetreten.")


@worker_required
@limiter.limit("40 per minute")
def _toggle_checklist_api(item_id: int) -> tuple[Response, int] | Response:
    """Toggle a checklist item's completion state."""
    item = db.session.get(ChecklistItem, item_id)
    if item:
        ticket = _check_ticket_access(item.ticket_id)
        if ticket is None:
            return _api_error("Kein Zugriff auf dieses Ticket.", 403)

    lock_err = check_approval_lock(item_id=item_id)
    if lock_err:
        return lock_err

    try:
        item = TicketService.toggle_checklist_item(
            item_id,
            worker_name=_session_author(),
            worker_id=_session_worker_id(),
        )
        return _api_ok(is_completed=item.is_completed if item else False)
    except SQLAlchemyError:
        current_app.logger.exception("API Error in _toggle_checklist_api")
        return _api_error("Ein interner Fehler ist aufgetreten.")


@worker_required
@limiter.limit("20 per minute")
def _delete_checklist_api(item_id: int) -> tuple[Response, int] | Response:
    """Delete a checklist item."""
    item = db.session.get(ChecklistItem, item_id)
    if item:
        ticket = _check_ticket_access(item.ticket_id)
        if ticket is None:
            return _api_error("Kein Zugriff auf dieses Ticket.", 403)

    lock_err = check_approval_lock(item_id=item_id)
    if lock_err:
        return lock_err

    try:
        TicketService.delete_checklist_item(item_id)
        return _api_ok()
    except SQLAlchemyError:
        current_app.logger.exception("API Error in _delete_checklist_api")
        return _api_error("Ein interner Fehler ist aufgetreten.")


def _apply_template_api(ticket_id: int) -> tuple[Response, int] | Response:
    """Apply a checklist template to an existing ticket."""
    ticket = _check_ticket_access(ticket_id)
    if ticket is None:
        return _api_error("Kein Zugriff auf dieses Ticket.", 403)

    lock_err = check_approval_lock(ticket_id=ticket_id)
    if lock_err:
        return lock_err

    data: dict[str, Any] = request.get_json(silent=True) or {}
    template_id = data.get("template_id")
    if not template_id:
        return _api_error("Keine Vorlage ausgewählt.", 400)

    try:
        TicketService.apply_checklist_template(ticket_id, template_id)
        return _api_ok()
    except SQLAlchemyError as exc:
        return _api_error(str(exc))


# ------------------------------------------------------------------
# My Queue view
# ------------------------------------------------------------------

def _my_queue_view() -> str:
    """Personal task queue grouped by urgency."""
    worker_id = _session_worker_id()
    days_horizon = request.args.get("days", 7, type=int)
    now = get_utc_now()

    worker_role = session.get("role")
    team_ids = Team.team_ids_for_worker(worker_id)
    tickets_list = _build_queue_query(worker_id, team_ids, worker_role).all()
    tickets_list.sort(key=lambda t: TicketService._urgency_score(t, now))

    groups = _group_by_urgency(tickets_list, now, days_horizon)
    urgent_count = len(groups["overdue"]) + len(groups["today"])

    return render_template(
        "my_queue.html",
        groups=groups,
        tickets=tickets_list,
        urgent_count=urgent_count,
        days_horizon=days_horizon,
        today=now,
    )


def _build_queue_query(
    worker_id: int | None,
    team_ids: list[int],
    worker_role: str | None,
) -> Any:
    """Build the SQLAlchemy query for the personal queue."""
    team_clauses: list[Any] = []
    if team_ids:
        team_clauses = [
            Ticket.assigned_team_id.in_(team_ids),
            Ticket.checklists.any(
                db.and_(
                    ChecklistItem.assigned_team_id.in_(team_ids),
                    ChecklistItem.is_completed == False,  # noqa: E712
                ),
            ),
        ]

    query = Ticket.query.filter(
        Ticket.is_deleted == False,  # noqa: E712
        Ticket.status != TicketStatus.ERLEDIGT.value,
    ).filter(
        db.or_(
            Ticket.assigned_to_id == worker_id,
            Ticket.checklists.any(
                db.and_(
                    ChecklistItem.assigned_to_id == worker_id,
                    ChecklistItem.is_completed == False,  # noqa: E712
                ),
            ),
            *team_clauses,
        ),
    )

    if worker_role not in _ELEVATED_ROLES:
        query = _apply_confidential_filter(query, worker_id, team_ids)

    return query


def _apply_confidential_filter(
    query: Any,
    worker_id: int | None,
    team_ids: list[int],
) -> Any:
    """Filter out confidential tickets the worker cannot see."""
    conf_team: list[Any] = []
    if team_ids:
        conf_team = [
            Ticket.assigned_team_id.in_(team_ids),
            Ticket.checklists.any(
                ChecklistItem.assigned_team_id.in_(team_ids),
            ),
        ]
    author_sub = (
        db.session.query(Comment.ticket_id)
        .filter(
            Comment.event_type == "TICKET_CREATED",
            Comment.author_id == worker_id,
        )
        .subquery()
    )
    return query.filter(
        db.or_(
            Ticket.is_confidential == False,  # noqa: E712
            Ticket.id.in_(author_sub),
            Ticket.assigned_to_id == worker_id,
            Ticket.checklists.any(
                ChecklistItem.assigned_to_id == worker_id,
            ),
            *conf_team,
        ),
    )


def _has_due_reminder(t: Ticket, today) -> bool:
    """Return True if ticket is waiting with a reminder due today or earlier."""
    return (
        t.status == TicketStatus.WARTET.value
        and t.reminder_date is not None
        and t.reminder_date.date() <= today
    )


def _group_by_urgency(
    tickets: list[Ticket],
    now: datetime,
    days_horizon: int,
) -> dict[str, list[Ticket]]:
    """Partition *tickets* into urgency buckets.

    Tickets with status "Wartet" whose ``reminder_date`` is due today or
    earlier are surfaced in the "today" bucket so they appear in the
    Kanban board as actionable follow-ups.
    """
    effective = days_horizon if days_horizon > 0 else 999
    today = now.date()

    # Collect IDs of waiting tickets promoted via reminder_date so they
    # are not also placed into their due_date bucket.
    reminder_ids: set[int] = set()
    reminder_tickets: list[Ticket] = []
    for t in tickets:
        if _has_due_reminder(t, today):
            reminder_ids.add(t.id)
            reminder_tickets.append(t)

    return {
        "overdue": [
            t for t in tickets
            if t.id not in reminder_ids
            and t.due_date and t.due_date.date() < today
        ],
        "today": [
            t for t in tickets
            if t.id not in reminder_ids
            and t.due_date and t.due_date.date() == today
        ] + reminder_tickets,
        "this_week": [
            t for t in tickets
            if t.id not in reminder_ids
            and t.due_date and 0 < (t.due_date.date() - today).days <= 7
        ],
        "upcoming": [
            t for t in tickets
            if t.id not in reminder_ids
            and t.due_date
            and 7 < (t.due_date.date() - today).days <= effective
        ],
        "no_due_date": [
            t for t in tickets
            if t.id not in reminder_ids and not t.due_date
        ],
        "later": [
            t for t in tickets
            if t.id not in reminder_ids
            and t.due_date and (t.due_date.date() - today).days > effective
        ],
    }


# ------------------------------------------------------------------
# Workload view
# ------------------------------------------------------------------

@admin_or_management_required
def _workload_view() -> str:
    """Admin/Management workload overview per worker."""
    absent_entries, present_entries = TicketService.get_workload_overview()
    active_workers = (
        Worker.query.filter_by(is_active=True).order_by(Worker.name).all()
    )
    return render_template(
        "workload.html",
        absent_entries=absent_entries,
        present_entries=present_entries,
        active_workers=active_workers,
        today=get_utc_now(),
    )


# ------------------------------------------------------------------
# Notification APIs
# ------------------------------------------------------------------

def _api_get_notifications() -> Response:
    """Fetch recent notifications for the dropdown."""
    worker_id = _session_worker_id()
    notifs = (
        Notification.query
        .filter_by(user_id=worker_id)
        .order_by(Notification.created_at.desc())
        .limit(15)
        .all()
    )
    return jsonify({
        "notifications": [
            {
                "id": n.id,
                "message": n.message,
                "link": n.link or "#",
                "is_read": n.is_read,
            }
            for n in notifs
        ],
        "unread_count": sum(1 for n in notifs if not n.is_read),
    })


def _api_read_notification(notif_id: int) -> tuple[Response, int] | Response:
    """Mark a single notification as read."""
    worker_id = _session_worker_id()
    notif = db.session.get(Notification, notif_id)
    if notif and notif.user_id == worker_id:
        notif.is_read = True
        db.session.commit()
        return _api_ok()
    return _api_error("Not found", 404)


def _api_read_all_notifications() -> Response:
    """Mark all notifications for the current worker as read."""
    worker_id = _session_worker_id()
    Notification.query.filter_by(
        user_id=worker_id, is_read=False,
    ).update({"is_read": True})
    db.session.commit()
    return _api_ok()


# ------------------------------------------------------------------
# Bulk actions
# ------------------------------------------------------------------

def _bulk_action_api() -> tuple[Response, int] | Response:
    """Handle bulk operations on multiple tickets."""
    data: dict[str, Any] = request.get_json(silent=True) or {}
    ticket_ids: list[int] = data.get("ticket_ids", [])
    action: str | None = data.get("action")

    if not ticket_ids or not action:
        return _api_error("Keine Tickets oder Aktion angegeben.", 400)

    try:
        updated = _execute_bulk_action(ticket_ids, action, data)
        db.session.commit()
        return _api_ok(updated=updated)
    except SQLAlchemyError as exc:
        db.session.rollback()
        return _api_error(str(exc))


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
            if ticket.approval_status == ApprovalStatus.PENDING.value:
                ticket.approval_status = ApprovalStatus.REJECTED.value
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
    worker_id = _safe_int(str(data.get("worker_id", "")))
    team_id = _safe_int(str(data.get("team_id", "")))
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


# ------------------------------------------------------------------
# CSV exports
# ------------------------------------------------------------------

def _export_archive_csv() -> Response:
    """Export archive tickets as a streaming CSV download.

    Uses ``yield_per`` to avoid loading all rows into RAM at once,
    which prevents OOM crashes on memory-constrained systems.
    """
    search = request.args.get("q", "").strip()
    author = request.args.get("author", "").strip()
    worker_id = _session_worker_id()
    worker_role = session.get("role")
    is_elevated = worker_role in _ELEVATED_ROLES

    query = Ticket.query.filter(
        Ticket.is_deleted == False,  # noqa: E712
        Ticket.status == TicketStatus.ERLEDIGT.value,
    )

    if not is_elevated and worker_id is not None:
        from services.ticket_service import _confidential_filter
        from models import Team
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
                | Ticket.contact_name.ilike(pattern)
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


# ------------------------------------------------------------------
# Duplicate ticket
# ------------------------------------------------------------------

def _duplicate_ticket_api(ticket_id: int) -> Response:
    """Create a copy of a ticket (metadata only, without comments/history)."""
    ticket = _check_ticket_access(ticket_id)
    if ticket is None:
        return _api_error("Ticket nicht gefunden oder keine Berechtigung.", 404)

    try:
        new_ticket = Ticket(
            title=f"Kopie von: {ticket.title}",
            description=ticket.description,
            priority=ticket.priority,
            status=TicketStatus.OFFEN.value,
            order_reference=ticket.order_reference,
            contact_name=ticket.contact_name,
            contact_phone=ticket.contact_phone,
            contact_email=ticket.contact_email,
            contact_channel=ticket.contact_channel,
            is_confidential=ticket.is_confidential,
            assigned_to_id=ticket.assigned_to_id,
            assigned_team_id=ticket.assigned_team_id,
        )
        # Copy tags
        for tag in ticket.tags:
            new_ticket.tags.append(tag)

        db.session.add(new_ticket)
        db.session.flush()

        # Copy checklist items (uncompleted)
        for item in ticket.checklists:
            db.session.add(ChecklistItem(
                ticket_id=new_ticket.id,
                title=item.title,
                is_completed=False,
                assigned_to_id=item.assigned_to_id,
                assigned_team_id=item.assigned_team_id,
            ))

        db.session.commit()
        return _api_ok(ticket_id=new_ticket.id)
    except SQLAlchemyError as exc:
        db.session.rollback()
        current_app.logger.error("Duplicate ticket error: %s", exc)
        return _api_error("Datenbankfehler beim Duplizieren.")


# ------------------------------------------------------------------
# Theme preference
# ------------------------------------------------------------------

def _save_theme_api() -> Response:
    """Save the authenticated user's UI theme preference."""
    worker_id = session.get("worker_id")
    if not worker_id:
        return _api_error("Nicht angemeldet.", 401)

    data = request.get_json(silent=True) or {}
    theme = data.get("theme", "").strip()
    if theme not in ("light", "dark", "hc", "auto"):
        return _api_error("Ungültiges Theme.", 400)

    try:
        worker = db.session.get(Worker, worker_id)
        if worker:
            worker.ui_theme = theme
            db.session.commit()
        return _api_ok()
    except SQLAlchemyError as exc:
        db.session.rollback()
        current_app.logger.error("Save theme error: %s", exc)
        return _api_error("Datenbankfehler.")


# ------------------------------------------------------------------
# Route registration
# ------------------------------------------------------------------

def _push_vapid_key_api() -> Response:
    """Return the VAPID public key for push subscription."""
    try:
        from services.push_service import get_vapid_public_key, get_or_create_vapid_keys
        pub = get_vapid_public_key()
        if not pub:
            _, pub = get_or_create_vapid_keys()
        return jsonify({"public_key": pub})
    except Exception as exc:
        current_app.logger.error("VAPID key retrieval error: %s", exc)
        return jsonify({"error": "Interner Serverfehler."}), 500


def _push_subscribe_api() -> Response:
    """Store a push subscription for the authenticated worker."""
    data = request.get_json(silent=True) or {}
    endpoint = data.get("endpoint")
    keys = data.get("keys", {})
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")

    if not endpoint or not p256dh or not auth:
        return jsonify({"success": False, "error": "Unvollständige Subscription-Daten."}), 400

    worker_id = _session_worker_id()
    if not worker_id:
        return jsonify({"success": False, "error": "Nicht authentifiziert."}), 401

    try:
        from services.push_service import save_subscription
        save_subscription(worker_id, endpoint, p256dh, auth)
        return jsonify({"success": True})
    except Exception as exc:
        current_app.logger.error("Push subscribe error: %s", exc)
        return jsonify({"success": False, "error": "Interner Serverfehler."}), 500


def _push_unsubscribe_api() -> Response:
    """Remove a push subscription."""
    data = request.get_json(silent=True) or {}
    endpoint = data.get("endpoint")
    if not endpoint:
        return jsonify({"success": False, "error": "Kein Endpoint angegeben."}), 400
    try:
        from services.push_service import delete_subscription
        delete_subscription(endpoint)
        return jsonify({"success": True})
    except Exception as exc:
        current_app.logger.error("Push unsubscribe error: %s", exc)
        return jsonify({"success": False, "error": "Interner Serverfehler."}), 500


def _worker_mention_names_api() -> Response:
    """Return active worker names for @mention autocomplete."""
    workers = Worker.query.filter_by(is_active=True).order_by(Worker.name).all()
    return jsonify({"names": [w.name for w in workers]})


def _dashboard_rows_api() -> Response:
    """Return rendered HTML of the dashboard table rows for silent polling refresh."""
    worker_id = _session_worker_id()
    search = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    per_page = min(max(per_page, 10), 100)
    unassigned_only = request.args.get("unassigned") == "1"
    callback_pending = request.args.get("callback_pending") == "1"
    assigned_worker_id = request.args.get("worker_id", type=int)
    sort_by = request.args.get("sort", "") or None
    sort_dir = request.args.get("dir", "asc")
    if sort_dir not in ("asc", "desc"):
        sort_dir = "asc"
    tab = request.args.get("tab", "all")

    if tab == "unassigned":
        unassigned_only = True
    elif tab == "callback":
        callback_pending = True
    elif tab == "wartet":
        status_filter = status_filter or "wartet"

    team_ids = Team.team_ids_for_worker(worker_id) if worker_id else []
    tickets_data = TicketService.get_dashboard_tickets(
        worker_id=worker_id,
        search=search,
        status_filter=status_filter,
        page=page,
        per_page=per_page,
        unassigned_only=unassigned_only,
        callback_pending=callback_pending,
        worker_role=session.get("role"),
        team_ids=team_ids,
        assigned_worker_id=assigned_worker_id,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )

    all_workers = Worker.query.filter_by(is_active=True).order_by(Worker.name).all()
    all_teams = Team.query.order_by(Team.name).all()

    html = render_template(
        "components/_dashboard_rows.html",
        focus_tickets=tickets_data["focus_pagination"].items,
        workers=all_workers,
        teams=all_teams,
        today=get_utc_now(),
    )
    return Response(html, mimetype="text/html")


def register_routes(bp: Blueprint) -> None:
    """Register ticket routes with explicit endpoints."""
    # Dashboards
    bp.add_url_rule("/", "index", view_func=worker_required(_dashboard_view))
    bp.add_url_rule(
        "/api/dashboard/rows", "dashboard_rows_api",
        view_func=worker_required(_dashboard_rows_api),
    )
    bp.add_url_rule(
        "/archive", "archive", view_func=worker_required(_archive_view),
    )
    bp.add_url_rule(
        "/my-queue", "my_queue", view_func=worker_required(_my_queue_view),
    )
    bp.add_url_rule("/approvals", "approvals", view_func=_approvals_view)
    bp.add_url_rule(
        "/projects", "projects", view_func=worker_required(_projects_view),
    )
    bp.add_url_rule("/workload", "workload", view_func=_workload_view)

    # Ticket creation & view
    bp.add_url_rule(
        "/ticket/new", "ticket_new",
        view_func=limiter.limit("5 per minute")(_new_ticket_view),
        methods=["GET", "POST"],
    )
    bp.add_url_rule(
        "/ticket/<int:ticket_id>", "ticket_detail",
        view_func=worker_required(_ticket_detail_view),
    )
    bp.add_url_rule(
        "/ticket/<int:ticket_id>/public", "ticket_public",
        view_func=_public_ticket_view,
    )

    # Actions & API
    bp.add_url_rule(
        "/ticket/<int:ticket_id>/comment", "add_comment",
        view_func=worker_required(_add_comment_view), methods=["POST"],
    )
    bp.add_url_rule(
        "/ticket/<int:ticket_id>/assign_me", "assign_to_me",
        view_func=worker_required(_assign_to_me_view), methods=["POST"],
    )
    bp.add_url_rule(
        "/api/ticket/<int:ticket_id>/request_approval",
        "request_approval_api",
        view_func=worker_required(_request_approval_api), methods=["POST"],
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
        "/api/ticket/<int:ticket_id>/status", "update_status",
        view_func=worker_required(_update_status_api), methods=["POST"],
    )
    bp.add_url_rule(
        "/api/ticket/<int:ticket_id>/assign", "assign_ticket_api",
        view_func=worker_required(_assign_ticket_api), methods=["POST"],
    )
    bp.add_url_rule(
        "/api/ticket/<int:ticket_id>/update", "update_ticket",
        view_func=worker_required(_update_ticket_api), methods=["POST"],
    )
    bp.add_url_rule(
        "/api/ticket/<int:ticket_id>/update_contact", "update_contact",
        view_func=worker_required(_update_contact_api), methods=["POST"],
    )
    bp.add_url_rule(
        "/api/ticket/<int:ticket_id>/apply_template", "apply_template",
        view_func=worker_required(_apply_template_api), methods=["POST"],
    )
    bp.add_url_rule(
        "/api/ticket/<int:ticket_id>/reassign", "reassign_ticket_api",
        view_func=_reassign_ticket_api, methods=["POST"],
    )
    bp.add_url_rule(
        "/api/tickets/bulk", "bulk_action_api",
        view_func=worker_required(_bulk_action_api), methods=["POST"],
    )
    bp.add_url_rule(
        "/api/export/archive", "export_archive_csv",
        view_func=worker_required(_export_archive_csv),
    )
    bp.add_url_rule(
        "/api/export/projects", "export_projects_csv",
        view_func=worker_required(_export_projects_csv),
    )
    bp.add_url_rule(
        "/attachment/<int:attachment_id>", "serve_attachment",
        view_func=worker_required(_serve_attachment),
    )
    bp.add_url_rule(
        "/api/notifications", "get_notifications",
        view_func=worker_required(_api_get_notifications), methods=["GET"],
    )
    bp.add_url_rule(
        "/api/notifications/<int:notif_id>/read", "read_notification",
        view_func=worker_required(_api_read_notification), methods=["POST"],
    )
    bp.add_url_rule(
        "/api/notifications/read_all", "read_all_notifications",
        view_func=worker_required(_api_read_all_notifications),
        methods=["POST"],
    )
    bp.add_url_rule(
        "/api/ticket/<int:ticket_id>/duplicate", "duplicate_ticket_api",
        view_func=worker_required(_duplicate_ticket_api), methods=["POST"],
    )
    bp.add_url_rule(
        "/api/user/theme", "save_theme_api",
        view_func=_save_theme_api, methods=["POST"],
    )
    bp.add_url_rule(
        "/api/workers/mention-names", "worker_mention_names",
        view_func=worker_required(_worker_mention_names_api),
    )
    bp.add_url_rule(
        "/api/push/vapid-key", "push_vapid_key",
        view_func=worker_required(_push_vapid_key_api),
    )
    bp.add_url_rule(
        "/api/push/subscribe", "push_subscribe",
        view_func=worker_required(_push_subscribe_api), methods=["POST"],
    )
    bp.add_url_rule(
        "/api/push/unsubscribe", "push_unsubscribe",
        view_func=worker_required(_push_unsubscribe_api), methods=["POST"],
    )
