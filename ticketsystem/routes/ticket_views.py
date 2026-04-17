"""View endpoints for ticket dashboards, creation, detail, queue, and workload.

HTML-rendering routes that display pages to the user.
"""

from datetime import date, datetime, timedelta
from typing import Any

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    jsonify,
    render_template,
    request,
    session,
    url_for,
)
from markupsafe import Markup
from sqlalchemy.exc import SQLAlchemyError

from enums import ELEVATED_ROLES, TicketPriority, TicketStatus
from extensions import db, limiter
from models import ChecklistItem, ChecklistTemplate, Team, Ticket
from routes.auth import admin_or_management_required, redirect_to, worker_required
from services._ticket_helpers import ContactInfo, TicketFilterSpec, _urgency_score
from services.dashboard_service import DashboardService
from services.ticket_approval_service import TicketApprovalService
from services.ticket_core_service import TicketCoreService
from utils import get_utc_now

from ._helpers import (
    _check_ticket_access,
    _parse_assignment_ids,
    _parse_callback_due,
    _parse_date,
    _safe_int,
    get_active_workers,
    get_all_teams,
)


# ------------------------------------------------------------------
# Dashboard & Archive views
# ------------------------------------------------------------------

@worker_required
def _dashboard_view() -> str | Response:
    """Main dashboard view."""
    worker_id = session.get("worker_id")
    search = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)
    ua = request.headers.get("User-Agent", "")
    default_pp = 10 if any(k in ua.lower() for k in ("mobile", "android", "iphone")) else 25
    per_page = request.args.get("per_page", default_pp, type=int)
    per_page = min(max(per_page, 5), 100)
    assigned_to_me = request.args.get("assigned_to_me") == "1"
    unassigned_only = request.args.get("unassigned") == "1"
    callback_pending = request.args.get("callback_pending") == "1"
    assigned_worker_id = request.args.get("worker_id", type=int)
    sort_by = request.args.get("sort", "")
    sort_dir = request.args.get("dir", "asc")
    if sort_dir not in ("asc", "desc"):
        sort_dir = "asc"

    # Time horizon filter (due within N days, 0 = all)
    days_horizon = request.args.get("days", 0, type=int)

    # Active tab: "all" (default), "unassigned", "callback"
    # Deep-link alias retained for backward compat: "wartet" (not shown as a tab)
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
    tickets_data = DashboardService.get_dashboard_tickets(TicketFilterSpec(
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
        due_within_days=days_horizon,
    ))

    all_workers = get_active_workers()
    all_teams = get_all_teams()

    project_names: set[str] = {
        row[0]
        for row in (
            Ticket.query
            .filter(Ticket.order_reference.isnot(None))
            .with_entities(Ticket.order_reference)
            .distinct()
            .all()
        )
        if row[0]
    }

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
        today=date.today(),
        workers=all_workers,
        teams=all_teams,
        active_tab=tab,
        sort_by=sort_by,
        sort_dir=sort_dir,
        per_page=per_page,
        days_horizon=days_horizon,
        project_names=project_names,
    )


@worker_required
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
        end_date = end_date + timedelta(days=1)

    wid = session.get("worker_id")
    team_ids = Team.team_ids_for_worker(wid) if wid else []
    tickets_data = DashboardService.get_dashboard_tickets(TicketFilterSpec(
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
    ))

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
    pagination = TicketApprovalService.get_pending_approvals(page=page)
    return render_template(
        "approvals.html", pagination=pagination, tickets=pagination.items,
    )


@worker_required
def _projects_view() -> str:
    """Project / Baustellen overview."""
    projects = DashboardService.get_projects_summary()
    return render_template("projects.html", projects=projects)


# ------------------------------------------------------------------
# Ticket creation
# ------------------------------------------------------------------

def _new_ticket_view() -> str | Response:
    """Handle new ticket creation."""
    if request.method == "POST":
        return _handle_ticket_creation()

    all_workers = get_active_workers()
    all_teams = get_all_teams()
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

    worker_id = session.get("worker_id")
    is_confidential = (
        request.form.get("is_confidential") in ("True", "on")
        and bool(worker_id)
    )

    assigned_to_id, assigned_team_id = _parse_assignment_ids(
        request.form.get("assigned_to_id"),
        request.form.get("assigned_team_id"),
        fallback_worker_id=worker_id,
    )

    template_id = _safe_int(request.form.get("template_id"))
    raw_due_date = request.form.get("due_date")
    due_date = _parse_date(raw_due_date)
    if raw_due_date and not due_date:
        flash("Ungültiges Datumsformat für Fälligkeit. Bitte verwenden Sie das Format JJJJ-MM-TT.", "warning")
    callback_due = _parse_callback_due(request.form.get("callback_due", ""))

    try:
        priority = TicketPriority(int(priority_val))
        ticket = TicketCoreService.create_ticket(
            title=title,
            description=description,
            priority=priority,
            author_name=author_name,
            author_id=worker_id,
            attachments=attachments,
            due_date=due_date,
            assigned_to_id=assigned_to_id,
            assigned_team_id=assigned_team_id,
            is_confidential=is_confidential,
            recurrence_rule=request.form.get("recurrence_rule"),
            order_reference=request.form.get("order_reference"),
            tags=tags,
            checklist_template_id=template_id,
            contact=ContactInfo(
                name=request.form.get("contact_name") or None,
                phone=request.form.get("contact_phone") or None,
                email=request.form.get("contact_email") or None,
                channel=request.form.get("contact_channel") or None,
                callback_requested=request.form.get("callback_requested") == "on",
                callback_due=callback_due,
            ),
        )
        return _after_ticket_created(ticket)
    except (ValueError, SQLAlchemyError):
        current_app.logger.exception(
            "Fehler beim Erstellen des Tickets (worker=%s)",
            worker_id,
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

    if not session.get("worker_id"):
        return redirect_to("main.ticket_public", ticket_id=ticket.id, new=1)

    flash(Markup(f"Ticket {link_html} erfolgreich erstellt!"), "success")
    return redirect_to("main.index")


# ------------------------------------------------------------------
# Ticket detail & public views
# ------------------------------------------------------------------

@worker_required
def _ticket_detail_view(ticket_id: int) -> str | Response:
    """Ticket detail view."""
    worker_id = session.get("worker_id")
    role = session.get("role")

    db.session.expire_all()
    ticket = _check_ticket_access(ticket_id, worker_id, role)
    if not ticket:
        flash("Ticket nicht gefunden.", "error")
        return redirect_to("main.index")

    all_workers = get_active_workers()
    all_teams = get_all_teams()
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
# My Queue view
# ------------------------------------------------------------------

@worker_required
def _my_queue_view() -> str:
    """Personal task queue grouped by urgency."""
    worker_id = session.get("worker_id")
    days_horizon = request.args.get("days", 7, type=int)
    now = get_utc_now()

    worker_role = session.get("role")
    team_ids = Team.team_ids_for_worker(worker_id)
    tickets_list = _build_queue_query(worker_id, team_ids, worker_role).all()
    tickets_list.sort(key=lambda t: _urgency_score(t, now))

    groups = _group_by_urgency(tickets_list, now, days_horizon)
    urgent_count = len(groups["overdue"]) + len(groups["today"])

    return render_template(
        "my_queue.html",
        groups=groups,
        tickets=tickets_list,
        urgent_count=urgent_count,
        days_horizon=days_horizon,
        today=now.date(),
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
                    ChecklistItem.is_completed.is_(False),
                ),
            ),
        ]

    query = Ticket.query.filter(
        Ticket.is_deleted.is_(False),
        Ticket.status != TicketStatus.ERLEDIGT.value,
    ).filter(
        db.or_(
            Ticket.assigned_to_id == worker_id,
            Ticket.checklists.any(
                db.and_(
                    ChecklistItem.assigned_to_id == worker_id,
                    ChecklistItem.is_completed.is_(False),
                ),
            ),
            *team_clauses,
        ),
    )

    if worker_role not in ELEVATED_ROLES:
        from services._ticket_helpers import _confidential_filter
        query = query.filter(db.or_(*_confidential_filter(worker_id, team_ids)))

    return query


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
    """Partition *tickets* into urgency buckets."""
    effective = days_horizon if days_horizon > 0 else 999
    today = now.date()

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
            and t.due_date and t.due_date < today
        ],
        "today": [
            t for t in tickets
            if t.id not in reminder_ids
            and t.due_date and t.due_date == today
        ] + reminder_tickets,
        "this_week": [
            t for t in tickets
            if t.id not in reminder_ids
            and t.due_date and 0 < (t.due_date - today).days <= 7
        ],
        "upcoming": [
            t for t in tickets
            if t.id not in reminder_ids
            and t.due_date
            and 7 < (t.due_date - today).days <= effective
        ],
        "no_due_date": [
            t for t in tickets
            if t.id not in reminder_ids and not t.due_date
        ],
        "later": [
            t for t in tickets
            if t.id not in reminder_ids
            and t.due_date and (t.due_date - today).days > effective
        ],
    }


# ------------------------------------------------------------------
# Workload view
# ------------------------------------------------------------------

@admin_or_management_required
def _workload_view() -> str:
    """Admin/Management workload overview per worker."""
    absent_entries, present_entries = DashboardService.get_workload_overview()
    active_workers = get_active_workers()
    return render_template(
        "workload.html",
        absent_entries=absent_entries,
        present_entries=present_entries,
        active_workers=active_workers,
        today=date.today(),
    )


# ------------------------------------------------------------------
# Dashboard rows API (AJAX polling)
# ------------------------------------------------------------------

@worker_required
def _dashboard_rows_api() -> Response:
    """Return rendered HTML fragments for silent polling refresh.

    Liefert JSON mit ``rows_html`` (Desktop-Tabelle, ``<tbody>``-Inhalt) und
    ``cards_html`` (Mobile-Card-Container, ``.ticket-cards``-Inhalt), damit
    beide Darstellungsvarianten beim Polling synchron bleiben.
    """
    worker_id = session.get("worker_id")
    search = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)
    ua = request.headers.get("User-Agent", "")
    default_pp = 10 if any(k in ua.lower() for k in ("mobile", "android", "iphone")) else 25
    per_page = request.args.get("per_page", default_pp, type=int)
    per_page = min(max(per_page, 5), 100)
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
    # Deep-link alias: "wartet" was formerly a UI tab, now lives as a backward-compat filter only.
    elif tab == "wartet":
        status_filter = status_filter or "wartet"

    team_ids = Team.team_ids_for_worker(worker_id) if worker_id else []
    tickets_data = DashboardService.get_dashboard_tickets(TicketFilterSpec(
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
    ))

    all_workers = get_active_workers()
    all_teams = get_all_teams()

    template_ctx = dict(
        focus_tickets=tickets_data["focus_pagination"].items,
        workers=all_workers,
        teams=all_teams,
        today=date.today(),
    )
    rows_html = render_template("components/_dashboard_rows.html", **template_ctx)
    cards_html = render_template("components/_dashboard_cards.html", **template_ctx)
    return jsonify({
        "success": True,
        "rows_html": rows_html,
        "cards_html": cards_html,
    })


def register_routes(bp: Blueprint) -> None:
    """Register view-related routes."""
    bp.add_url_rule("/", "index", view_func=_dashboard_view)
    bp.add_url_rule(
        "/api/dashboard/rows", "dashboard_rows_api",
        view_func=_dashboard_rows_api,
    )
    bp.add_url_rule("/archive", "archive", view_func=_archive_view)
    bp.add_url_rule("/my-queue", "my_queue", view_func=_my_queue_view)
    bp.add_url_rule("/approvals", "approvals", view_func=_approvals_view)
    bp.add_url_rule("/projects", "projects", view_func=_projects_view)
    bp.add_url_rule("/workload", "workload", view_func=_workload_view)
    bp.add_url_rule(
        "/ticket/new", "ticket_new",
        view_func=limiter.limit("5 per minute")(_new_ticket_view),
        methods=["GET", "POST"],
    )
    bp.add_url_rule(
        "/ticket/<int:ticket_id>", "ticket_detail",
        view_func=_ticket_detail_view,
    )
    bp.add_url_rule(
        "/ticket/<int:ticket_id>/public", "ticket_public",
        view_func=_public_ticket_view,
    )
