"""Admin routes module.

Handles worker management, team CRUD, checklist templates, SMTP
settings, and recovery-token display.
"""

import json
from datetime import datetime, timezone

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.wrappers import Response as WerkzeugResponse

from enums import WorkerRole
from extensions import db
from models import (
    ChecklistItem,
    ChecklistTemplate,
    ChecklistTemplateItem,
    Comment,
    CustomHoliday,
    SystemSettings,
    Team,
    Worker,
)
from routes.auth import admin_required, redirect_to
from services.worker_service import WorkerService
from utils import get_utc_now

admin_bp: Blueprint = Blueprint("admin", __name__)

_SMTP_KEYS = (
    "smtp_host",
    "smtp_port",
    "smtp_user",
    "smtp_password",
    "smtp_from",
    "smtp_tls",
    "smtp_base_url",
)

_TOKEN_EXPIRY_SECONDS = 300


# ------------------------------------------------------------------
# Workers
# ------------------------------------------------------------------

@admin_bp.route("/workers", methods=["GET", "POST"])
@admin_required
def workers() -> str | WerkzeugResponse:
    """List and manage workers."""
    if request.method == "POST":
        _dispatch_worker_action()

    workers_list = WorkerService.get_all_workers()
    return render_template("workers.html", workers=workers_list)


def _dispatch_worker_action() -> None:
    """Route the POST action to the appropriate worker handler."""
    action = request.form.get("action")
    try:
        if action == "create":
            _create_worker()
        elif action == "toggle_status":
            _toggle_worker_status()
        elif action == "update":
            _update_worker()
        elif action == "reset_pin":
            _reset_worker_pin()
        elif action == "generate_tokens":
            _generate_tokens()
    except ValueError as exc:
        flash(str(exc), "danger")
    except SQLAlchemyError:
        flash("Ein unerwarteter Fehler ist aufgetreten.", "danger")


def _create_worker() -> None:
    """Handle the ``create`` worker action."""
    name = request.form.get("name")
    pin = request.form.get("pin")
    role = request.form.get("role")
    email = request.form.get("email", "").strip() or None
    is_admin = role == WorkerRole.ADMIN.value
    WorkerService.create_worker(name, pin, is_admin, role, email=email)

    if pin:
        flash(
            f"Mitarbeiter '{name}' wurde angelegt. "
            f"Erster Login mit PIN: {pin}.",
            "success",
        )
    else:
        flash(
            f"Mitarbeiter '{name}' wurde ohne PIN angelegt. "
            "Standard-PIN ist '0000' (muss beim ersten Login geändert werden).",
            "success",
        )


def _toggle_worker_status() -> None:
    """Handle the ``toggle_status`` worker action."""
    worker_id = request.form.get("worker_id")
    worker = WorkerService.toggle_status(worker_id)
    status_str = "aktiviert" if worker.is_active else "deaktiviert"
    flash(f"Mitarbeiter '{worker.name}' wurde {status_str}.", "success")


def _update_worker() -> None:
    """Handle the ``update`` worker action."""
    worker_id = request.form.get("worker_id")
    name = request.form.get("name")
    role = request.form.get("role")
    email = request.form.get("email", "").strip() or None
    is_admin = role == WorkerRole.ADMIN.value
    WorkerService.update_worker(worker_id, name, is_admin, role, email=email)
    flash(f"Mitarbeiter '{name}' wurde aktualisiert.", "success")


def _reset_worker_pin() -> None:
    """Handle the ``reset_pin`` worker action."""
    worker_id = request.form.get("worker_id")
    worker = WorkerService.admin_reset_pin(worker_id)
    flash(
        f"PIN für '{worker.name}' wurde auf '0000' zurückgesetzt. "
        "Der Mitarbeiter muss diesen beim nächsten Login ändern.",
        "warning",
    )


def _generate_tokens() -> WerkzeugResponse | None:
    """Handle the ``generate_tokens`` worker action."""
    from services.system_service import SystemService

    SystemService.generate_recovery_tokens()
    flash(
        "Neue Notfall-Codes wurden generiert. "
        "Bitte sofort sicher verwahren!",
        "warning",
    )
    # Note: caller must handle the redirect return value
    return redirect_to("admin.show_tokens")


# ------------------------------------------------------------------
# Checklist templates
# ------------------------------------------------------------------

@admin_bp.route("/templates", methods=["GET", "POST"])
@admin_required
def templates() -> str:
    """List and manage checklist templates."""
    if request.method == "POST":
        _dispatch_template_action()

    templates_list = ChecklistTemplate.query.all()
    return render_template("admin_templates.html", templates=templates_list)


def _dispatch_template_action() -> None:
    """Route the POST action to the appropriate template handler."""
    action = request.form.get("action")
    try:
        if action == "create":
            _create_template()
        elif action == "update":
            _update_template()
        elif action == "delete":
            _delete_template()
    except SQLAlchemyError as exc:
        db.session.rollback()
        flash(f"Fehler: {exc}", "danger")


def _create_template() -> None:
    """Create a new checklist template with items."""
    title = request.form.get("title")
    desc = request.form.get("description")
    tmpl = ChecklistTemplate(title=title, description=desc)
    db.session.add(tmpl)
    db.session.flush()
    _add_template_items(tmpl.id)
    db.session.commit()
    flash("Vorlage erfolgreich erstellt.", "success")


def _update_template() -> None:
    """Update an existing checklist template and replace its items."""
    tmpl = db.session.get(ChecklistTemplate, request.form.get("template_id"))
    if not tmpl:
        return
    new_title = request.form.get("title", "").strip()
    if new_title:
        tmpl.title = new_title
    tmpl.description = request.form.get("description", "").strip()

    ChecklistTemplateItem.query.filter_by(template_id=tmpl.id).delete()
    _add_template_items(tmpl.id)
    db.session.commit()
    flash(f"Vorlage '{tmpl.title}' aktualisiert.", "success")


def _delete_template() -> None:
    """Delete a checklist template."""
    tmpl = db.session.get(ChecklistTemplate, request.form.get("template_id"))
    if tmpl:
        # Detach template from tickets that reference it before deletion
        from models import Ticket
        Ticket.query.filter_by(checklist_template_id=tmpl.id).update(
            {"checklist_template_id": None}
        )
        db.session.delete(tmpl)
        db.session.commit()
        flash("Vorlage gelöscht.", "success")


def _add_template_items(template_id: int) -> None:
    """Persist the ``items[]`` form list as template items."""
    for item_title in request.form.getlist("items[]"):
        title = item_title.strip()
        if title:
            db.session.add(
                ChecklistTemplateItem(template_id=template_id, title=title),
            )


# ------------------------------------------------------------------
# Teams
# ------------------------------------------------------------------

@admin_bp.route("/teams", methods=["GET", "POST"])
@admin_required
def teams() -> str | WerkzeugResponse:
    """List and manage teams."""
    if request.method == "POST":
        _dispatch_team_action()

    teams_list = Team.query.order_by(Team.name).all()
    active_workers = (
        Worker.query.filter_by(is_active=True).order_by(Worker.name).all()
    )
    return render_template(
        "admin_teams.html", teams=teams_list, active_workers=active_workers,
    )


def _dispatch_team_action() -> WerkzeugResponse | None:
    """Route the POST action to the appropriate team handler."""
    action = request.form.get("action")
    try:
        if action == "create":
            _create_team()
        elif action == "update":
            return _update_team()
        elif action == "delete":
            _delete_team()
    except SQLAlchemyError as exc:
        db.session.rollback()
        flash(f"Fehler: {exc}", "danger")
    return None


def _create_team() -> None:
    """Create a new team with optional members."""
    name = request.form.get("name", "").strip()
    if not name:
        flash("Teamname ist erforderlich.", "warning")
        return
    if Team.query.filter_by(name=name).first():
        flash(f"Team '{name}' existiert bereits.", "danger")
        return

    team = Team(name=name)
    _set_team_members(team)
    db.session.add(team)
    db.session.commit()
    flash(f"Team '{name}' wurde erstellt.", "success")


def _update_team() -> WerkzeugResponse | None:
    """Update an existing team's name and members."""
    team = db.session.get(Team, request.form.get("team_id"))
    if not team:
        return None

    new_name = request.form.get("name", "").strip()
    if new_name and new_name != team.name:
        if Team.query.filter_by(name=new_name).first():
            flash(f"Team '{new_name}' existiert bereits.", "danger")
            return redirect_to("admin.teams")
        team.name = new_name

    _set_team_members(team)
    db.session.commit()
    flash(f"Team '{team.name}' wurde aktualisiert.", "success")
    return None


def _delete_team() -> None:
    """Delete a team and nullify its FK references.

    Iterates affected tickets individually so that a system comment is
    written to each ticket's audit trail instead of doing a silent bulk
    UPDATE that leaves no trace of who was unassigned or why.
    """
    team = db.session.get(Team, request.form.get("team_id"))
    if not team:
        return
    from models import Ticket

    affected_tickets = Ticket.query.filter_by(assigned_team_id=team.id).all()
    team_name = team.name
    for ticket in affected_tickets:
        ticket.assigned_team_id = None
        ticket.updated_at = get_utc_now()
        db.session.add(Comment(
            ticket_id=ticket.id,
            author="System",
            text=(
                f"Team \"{team_name}\" wurde gelöscht. "
                "Ticket-Zuweisung wurde systemseitig aufgehoben."
            ),
            is_system_event=True,
        ))

    ChecklistItem.query.filter_by(assigned_team_id=team.id).update(
        {"assigned_team_id": None},
    )
    db.session.delete(team)
    db.session.commit()
    flash(
        f"Team '{team_name}' wurde gelöscht. "
        "Betroffene Zuweisungen wurden aufgehoben.",
        "success",
    )


def _set_team_members(team: Team) -> None:
    """Replace *team.members* with the workers from ``member_ids``."""
    team.members = []
    for mid in request.form.getlist("member_ids"):
        worker = db.session.get(Worker, int(mid))
        if worker:
            team.members.append(worker)


# ------------------------------------------------------------------
# Settings (SMTP)
# ------------------------------------------------------------------

@admin_bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings() -> str | WerkzeugResponse:
    """SMTP and system settings page."""
    if request.method == "POST":
        result = _dispatch_settings_action()
        if result is not None:
            return result
        return redirect(url_for("admin.settings"))

    current: dict[str, str] = {
        key: SystemSettings.get_setting(key, "") for key in _SMTP_KEYS
    }
    report_cfg = {
        "send_time": SystemSettings.get_setting("report_send_time", "07:00"),
        "weekdays": SystemSettings.get_setting("report_weekdays", "1,2,3,4,5"),
        "federal_state": SystemSettings.get_setting("report_federal_state", ""),
    }
    custom_holidays = (
        CustomHoliday.query.order_by(CustomHoliday.date).all()
    )

    from services.scheduler_service import FEDERAL_STATES
    return render_template(
        "settings.html",
        smtp=current,
        report_cfg=report_cfg,
        custom_holidays=custom_holidays,
        federal_states=FEDERAL_STATES,
    )


def _dispatch_settings_action() -> WerkzeugResponse | None:
    """Route the POST action to the appropriate settings handler."""
    action = request.form.get("action")
    if action == "save_smtp":
        _save_smtp()
    elif action == "test_smtp":
        _test_smtp()
    elif action == "clear_smtp_password":
        SystemSettings.set_setting("smtp_password", "")
        flash("SMTP-Passwort wurde entfernt.", "success")
    elif action == "generate_tokens":
        return _generate_tokens()
    elif action == "save_report_schedule":
        _save_report_schedule()
    elif action == "add_custom_holiday":
        _add_custom_holiday()
    elif action == "delete_custom_holiday":
        _delete_custom_holiday()
    return None


def _save_smtp() -> None:
    """Persist SMTP settings from the form."""
    for key in _SMTP_KEYS:
        val = request.form.get(key, "").strip()
        if key == "smtp_password" and not val:
            continue
        SystemSettings.set_setting(key, val)
    flash("SMTP-Einstellungen gespeichert.", "success")


def _test_smtp() -> None:
    """Send a test email to the address supplied in the form."""
    from services.email_service import _send

    test_addr = request.form.get("test_email", "").strip()
    if not test_addr:
        flash(
            "Bitte eine Empfänger-Adresse für den Test angeben.", "warning",
        )
        return

    ok = _send(
        test_addr,
        "[TicketSystem] SMTP Test-E-Mail",
        "<p>Die SMTP-Konfiguration funktioniert korrekt.</p>"
        "<hr><p style='color:#888;font-size:0.85em;'>"
        "TicketSystem — Testmail</p>",
        "Die SMTP-Konfiguration funktioniert korrekt.",
    )
    if ok:
        flash(f"Test-E-Mail erfolgreich an {test_addr} gesendet.", "success")
    else:
        flash(
            "Versand fehlgeschlagen. Bitte SMTP-Einstellungen prüfen "
            "(Details im Log).",
            "danger",
        )


def _save_report_schedule() -> None:
    """Persist report schedule settings and reschedule the SLA job."""
    send_time = request.form.get("report_send_time", "07:00").strip()
    weekdays = ",".join(request.form.getlist("report_weekdays"))
    federal_state = request.form.get("report_federal_state", "").strip()

    SystemSettings.set_setting("report_send_time", send_time)
    SystemSettings.set_setting("report_weekdays", weekdays or "1,2,3,4,5")
    if federal_state:
        SystemSettings.set_setting("report_federal_state", federal_state)
    else:
        setting = SystemSettings.query.filter_by(
            key="report_federal_state",
        ).first()
        if setting:
            db.session.delete(setting)
            db.session.commit()

    try:
        from services.scheduler_service import reschedule_sla_job
        reschedule_sla_job()
    except Exception:
        pass  # Scheduler may not be running in dev/test

    flash("Berichtsversand-Einstellungen gespeichert.", "success")


def _add_custom_holiday() -> None:
    """Add one or more custom holidays (date range + label)."""
    from datetime import date, timedelta

    start_str = request.form.get("holiday_start", "").strip()
    end_str = request.form.get("holiday_end", "").strip()
    label = request.form.get("holiday_label", "").strip()

    if not start_str or not label:
        flash("Datum und Bezeichnung sind Pflichtfelder.", "warning")
        return

    try:
        start = date.fromisoformat(start_str)
        end = date.fromisoformat(end_str) if end_str else start
    except ValueError:
        flash("Ungültiges Datumsformat.", "danger")
        return

    if end < start:
        flash("Enddatum darf nicht vor dem Startdatum liegen.", "warning")
        return

    added = 0
    current = start
    while current <= end:
        existing = CustomHoliday.query.filter_by(date=current).first()
        if not existing:
            db.session.add(CustomHoliday(date=current, label=label))
            added += 1
        current += timedelta(days=1)

    if added > 0:
        db.session.commit()
        flash(f"{added} freie(r) Tag(e) hinzugefügt.", "success")
    else:
        flash("Alle Tage waren bereits eingetragen.", "info")


def _delete_custom_holiday() -> None:
    """Delete a single custom holiday by ID."""
    hid = request.form.get("holiday_id")
    if not hid:
        return
    holiday = db.session.get(CustomHoliday, int(hid))
    if holiday:
        db.session.delete(holiday)
        db.session.commit()
        flash(
            f"Freier Tag ({holiday.date.strftime('%d.%m.%Y')}) entfernt.",
            "success",
        )


@admin_bp.route("/holiday-preview")
@admin_required
def holiday_preview() -> WerkzeugResponse:
    """Return the next 5 federal holidays as JSON for the preview widget."""
    import holidays as holidays_lib
    from datetime import date
    from flask import jsonify

    state = request.args.get("state", "")
    if not state:
        return jsonify(holidays=[])

    today = date.today()
    de = holidays_lib.Germany(subdiv=state, years=[today.year, today.year + 1])
    upcoming = sorted(
        [(d, name) for d, name in de.items() if d >= today],
        key=lambda x: x[0],
    )[:5]

    return jsonify(holidays=[
        {"date": d.strftime("%d.%m.%Y"), "name": name}
        for d, name in upcoming
    ])


# ------------------------------------------------------------------
# Recovery tokens
# ------------------------------------------------------------------

@admin_bp.route("/workers/tokens")
@admin_required
def show_tokens() -> str:
    """Display the generated recovery tokens (expires after 5 min)."""
    tokens_json = SystemSettings.get_setting("recovery_tokens_raw", "[]")
    tokens_ts = SystemSettings.get_setting("recovery_tokens_generated_at", "")

    tokens: list[str] = []
    expired = False

    if tokens_json and tokens_json != "[]":
        tokens, expired = _parse_tokens(tokens_json, tokens_ts)

    return render_template(
        "show_recovery_tokens.html", tokens=tokens, expired=expired,
    )


def _parse_tokens(
    tokens_json: str, tokens_ts: str,
) -> tuple[list[str], bool]:
    """Parse recovery tokens and check expiry.

    Returns:
        A tuple of ``(token_list, is_expired)``.
    """
    try:
        if tokens_ts:
            generated_at = datetime.fromisoformat(tokens_ts)
            now = get_utc_now()
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            if generated_at.tzinfo is None:
                generated_at = generated_at.replace(tzinfo=timezone.utc)
            elapsed = (now - generated_at).total_seconds()
            if elapsed > _TOKEN_EXPIRY_SECONDS:
                SystemSettings.set_setting("recovery_tokens_raw", "[]")
                SystemSettings.set_setting("recovery_tokens_generated_at", "")
                return [], True
        return json.loads(tokens_json), False
    except (ValueError, json.JSONDecodeError):
        return [], False


# ------------------------------------------------------------------
# Papierkorb (soft-deleted ticket recovery)
# ------------------------------------------------------------------

@admin_bp.route("/trash", methods=["GET", "POST"])
@admin_required
def trash() -> str | WerkzeugResponse:
    """Show soft-deleted tickets and allow restore or permanent deletion."""
    if request.method == "POST":
        action = request.form.get("action")
        ticket_id = request.form.get("ticket_id", type=int)
        if action and ticket_id:
            _handle_trash_action(action, ticket_id)
        return redirect(url_for("admin.trash"))

    from models import Ticket
    deleted_tickets = (
        Ticket.query.filter_by(is_deleted=True)
        .order_by(Ticket.updated_at.desc())
        .all()
    )
    return render_template("admin_trash.html", deleted_tickets=deleted_tickets)


def _handle_trash_action(action: str, ticket_id: int) -> None:
    """Restore or permanently delete a soft-deleted ticket."""
    from exceptions import TicketNotFoundError
    from models import Ticket
    from services.ticket_core_service import TicketCoreService

    if action == "restore":
        try:
            TicketCoreService.restore_ticket(
                ticket_id,
                author_name=session.get("worker_name", "Admin"),
                author_id=session.get("worker_id"),
            )
            flash(f"Ticket #{ticket_id} wurde wiederhergestellt.", "success")
        except TicketNotFoundError:
            flash("Ticket nicht gefunden.", "warning")
        return

    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or not ticket.is_deleted:
        flash("Ticket nicht gefunden.", "warning")
        return

    if action == "delete_permanent":
        db.session.delete(ticket)
        db.session.commit()
        flash(f"Ticket #{ticket.id} wurde dauerhaft gelöscht.", "warning")
