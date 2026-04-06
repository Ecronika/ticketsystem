"""Admin routes module.

Handles worker management, team CRUD, checklist templates, SMTP
settings, and recovery-token display.
"""

import json
from datetime import datetime, timezone
from typing import Any

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
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
    """Delete a team and nullify its FK references."""
    team = db.session.get(Team, request.form.get("team_id"))
    if not team:
        return
    from models import Ticket

    Ticket.query.filter_by(assigned_team_id=team.id).update(
        {"assigned_team_id": None},
    )
    ChecklistItem.query.filter_by(assigned_team_id=team.id).update(
        {"assigned_team_id": None},
    )
    team_name = team.name
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
    return render_template("settings.html", smtp=current)


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
