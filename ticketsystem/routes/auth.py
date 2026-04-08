"""Authentication routes.

Handles worker authentication, session management, PIN recovery, and
profile / out-of-office settings.
"""

import hashlib
import secrets
from datetime import timedelta
from functools import wraps
from typing import Any, Callable, TypeVar
from urllib.parse import urljoin, urlparse

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.wrappers import Response as WerkzeugResponse

from enums import WorkerRole
from extensions import db, limiter
from models import Notification, SystemSettings, Worker
from utils import get_utc_now

_F = TypeVar("_F", bound=Callable[..., Any])

# Timing-normalisation dummy so user-enumeration via response-time is
# infeasible (comparison cost identical to a real hash check).
_TIMING_DUMMY_HASH: str = generate_password_hash("__timing_guard__")

_ELEVATED_ROLES = frozenset({
    WorkerRole.ADMIN.value,
    WorkerRole.HR.value,
    WorkerRole.MANAGEMENT.value,
})

_MAX_FAILED_LOGINS = 5
_LOCKOUT_MINUTES = 15


# ------------------------------------------------------------------
# URL / redirect helpers
# ------------------------------------------------------------------

def is_safe_url(target: str) -> bool:
    """Return ``True`` if *target* is on the same host or ingress path."""
    if not target:
        return False

    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))

    if test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc:
        return True

    ingress: str = request.headers.get("X-Ingress-Path", "")
    return bool(ingress and target.startswith(ingress))


def redirect_to(endpoint: str, **kwargs: Any) -> WerkzeugResponse:
    """Ingress-aware redirect helper."""
    ingress: str = request.headers.get("X-Ingress-Path", "")
    target: str = url_for(endpoint, **kwargs)

    if ingress.endswith("/") and target.startswith("/"):
        target = target[1:]
    elif not ingress.endswith("/") and not target.startswith("/"):
        target = "/" + target

    return redirect(f"{ingress}{target}")


# ------------------------------------------------------------------
# Decorators
# ------------------------------------------------------------------

def admin_required(func: _F) -> _F:
    """Require admin permissions."""
    @wraps(func)
    def _wrapper(*args: Any, **kwargs: Any) -> Any:
        if not session.get("is_admin"):
            return _deny("Admin-Rechte erforderlich.", "main.login")
        return func(*args, **kwargs)
    return _wrapper  # type: ignore[return-value]


def admin_or_management_required(func: _F) -> _F:
    """Require admin, management, or HR role."""
    @wraps(func)
    def _wrapper(*args: Any, **kwargs: Any) -> Any:
        if session.get("role") not in _ELEVATED_ROLES:
            return _deny(
                "Diese Seite erfordert Administrator-, HR- oder "
                "Management-Rechte.",
                "main.login",
            )
        return func(*args, **kwargs)
    return _wrapper  # type: ignore[return-value]


def worker_required(func: _F) -> _F:
    """Require a worker login session."""
    @wraps(func)
    def _wrapper(*args: Any, **kwargs: Any) -> Any:
        if not session.get("worker_id"):
            return _deny("Bitte zuerst einloggen.", "main.login", 401)
        return func(*args, **kwargs)
    return _wrapper  # type: ignore[return-value]


def _deny(
    message: str,
    login_endpoint: str,
    api_status: int = 403,
) -> Any:
    """Return a JSON error for API routes, otherwise flash and redirect."""
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": message}), api_status
    flash(message, "warning")
    return redirect_to(login_endpoint, next=request.url)


# ------------------------------------------------------------------
# View helpers (extracted from _login_view to reduce complexity)
# ------------------------------------------------------------------

def _ingress_redirect(endpoint: str) -> WerkzeugResponse:
    """Build a redirect using the raw ingress prefix."""
    ingress: str = request.headers.get("X-Ingress-Path", "")
    return redirect(f"{ingress}{url_for(endpoint)}")


def _handle_locked_account(
    worker: Worker,
    now: Any,
    workers: list[Worker],
) -> str | None:
    """Return a rendered login page if the account is locked, else ``None``."""
    if not (worker.locked_until and worker.locked_until > now):
        return None
    remaining = worker.locked_until - now
    minutes_left = int(remaining.total_seconds() // 60) + 1
    flash(
        f"Konto vorübergehend gesperrt. Bitte in {minutes_left} Min. "
        "erneut versuchen.",
        "danger",
    )
    return render_template("login.html", workers=workers)


def _handle_successful_login(worker: Worker) -> WerkzeugResponse:
    """Reset lockout counters and initialise the session."""
    worker.failed_login_count = 0
    worker.locked_until = None
    worker.last_active = get_utc_now()
    db.session.commit()

    session.clear()
    session.modified = True
    session.permanent = True
    session["worker_id"] = worker.id
    session["worker_name"] = worker.name
    session["is_admin"] = worker.role == WorkerRole.ADMIN.value
    session["role"] = worker.role or "worker"

    if worker.needs_pin_change:
        flash(
            "Bitte ändern Sie zu Ihrer Sicherheit zuerst Ihren PIN.",
            "info",
        )
        return redirect_to("main.change_pin")

    flash(f"Willkommen zurück, {worker.name}!", "success")

    next_url = request.args.get("next") or request.form.get("next")
    if next_url and is_safe_url(next_url):
        return redirect(next_url)
    return redirect_to("main.my_queue")


def _handle_failed_login(
    worker: Worker, workers: list[Worker],
) -> str:
    """Increment failure counters and render the login page."""
    current_app.logger.debug(
        "Login FAILED for '%s' - PIN mismatch.", worker.name,
    )
    worker.failed_login_count += 1
    if worker.failed_login_count >= _MAX_FAILED_LOGINS:
        worker.locked_until = get_utc_now() + timedelta(minutes=_LOCKOUT_MINUTES)
        flash(
            "Zu viele Fehlversuche. Konto für 15 Minuten gesperrt.",
            "danger",
        )
    else:
        flash(
            "Ungültige Zugangsdaten. Bitte versuchen Sie es erneut.",
            "danger",
        )
    db.session.commit()
    return render_template("login.html", workers=workers)


# ------------------------------------------------------------------
# Route views
# ------------------------------------------------------------------

@limiter.limit("5 per minute")
def _setup_view() -> str | WerkzeugResponse:
    """Handle initial onboarding / first-start setup."""
    if SystemSettings.get_setting("onboarding_complete") == "true":
        return _ingress_redirect("main.login")

    if request.method != "POST":
        return render_template("setup.html")

    name = request.form.get("name")
    pin = request.form.get("pin")
    pin_confirm = request.form.get("pin_confirm")

    if not name or not pin:
        flash("Bitte Name und PIN angeben.", "warning")
        return render_template("setup.html")

    if pin != pin_confirm:
        flash("Die PINs stimmen nicht überein.", "warning")
        return render_template("setup.html")

    admin = Worker.query.filter_by(is_admin=True).first()
    if not admin:
        flash("Kein Admin-Konto gefunden.", "danger")
        return render_template("setup.html")

    admin.name = name
    admin.pin_hash = generate_password_hash(
        pin, method="pbkdf2:sha256", salt_length=16,
    )

    setting = SystemSettings.query.filter_by(key="onboarding_complete").first()
    if setting:
        setting.value = "true"

    db.session.commit()

    session.permanent = True
    session["worker_id"] = admin.id
    session["worker_name"] = admin.name
    session["is_admin"] = True

    flash("Setup abgeschlossen! Willkommen im System.", "success")
    return redirect_to("main.index")


@limiter.limit("20 per minute")
def _login_view() -> str | WerkzeugResponse:
    """Handle the login page and credential verification."""
    if SystemSettings.get_setting("onboarding_complete") != "true":
        return _ingress_redirect("main.setup")

    workers: list[Worker] = Worker.query.filter_by(is_active=True).all()
    if not workers:
        flash(
            "Keine Mitarbeiter gefunden. System-Bootstrap erforderlich.",
            "danger",
        )
        return render_template("login.html", workers=[])

    if request.method != "POST":
        return render_template("login.html", workers=workers)

    worker_name = (request.form.get("worker_name") or "").strip()
    pin = (request.form.get("pin") or "").strip()

    if not worker_name or not pin:
        flash("Bitte Name und PIN angeben.", "warning")
        return render_template("login.html", workers=workers)

    now = get_utc_now()
    worker = Worker.query.filter(
        Worker.name.ilike(worker_name),
        Worker.is_active == True,  # noqa: E712
    ).first()

    if not worker:
        check_password_hash(_TIMING_DUMMY_HASH, pin)
        flash("Ungültige Zugangsdaten oder Konto inaktiv.", "danger")
        return render_template("login.html", workers=workers)

    locked_response = _handle_locked_account(worker, now, workers)
    if locked_response is not None:
        return locked_response

    if check_password_hash(worker.pin_hash, pin):
        return _handle_successful_login(worker)

    return _handle_failed_login(worker, workers)


def _logout_view() -> WerkzeugResponse:
    """Handle worker logout with thorough session clearing."""
    # BUG-002: GET /logout redirects to login instead of 405
    if request.method == "GET":
        return redirect_to("main.login")

    session.clear()
    session.modified = True
    flash("Erfolgreich ausgeloggt.", "info")

    response: WerkzeugResponse = make_response(redirect_to("main.login"))
    response.set_cookie(
        current_app.config["SESSION_COOKIE_NAME"], "", expires=0,
    )
    response.headers["Clear-Site-Data"] = '"cache"'
    return response


def _recover_pin_view() -> str | WerkzeugResponse:
    """Handle PIN recovery using a single-use token."""
    if request.method != "POST":
        return render_template("recover_pin.html")

    token: str = request.form.get("token", "").strip().upper()

    saved_hashes_str: str = SystemSettings.get_setting(
        "recovery_tokens_hash", "",
    )
    if not saved_hashes_str:
        flash("Keine Recovery-Tokens im System hinterlegt.", "error")
        return render_template("recover_pin.html")

    hashed_tokens: list[str] = saved_hashes_str.split(",")
    valid_index = _find_valid_token(hashed_tokens, token)

    if valid_index < 0:
        flash("Ungültiger oder bereits verwendeter Token.", "error")
        return render_template("recover_pin.html")

    hashed_tokens.pop(valid_index)
    SystemSettings.set_setting(
        "recovery_tokens_hash", ",".join(hashed_tokens),
    )

    admin = Worker.query.filter_by(is_admin=True, is_active=True).first()
    if not admin:
        flash(
            "Kein aktiver Administrator gefunden, "
            "Wiederherstellung fehlgeschlagen.",
            "danger",
        )
        return render_template("recover_pin.html")

    session.clear()
    session["worker_id"] = admin.id
    session["worker_name"] = admin.name
    session["is_admin"] = True
    session.permanent = True

    admin.needs_pin_change = True
    db.session.commit()

    flash("Recovery erfolgreich. Bitte ändern Sie jetzt Ihren PIN!", "success")
    return redirect_to("main.index")


def _change_pin_view() -> str | WerkzeugResponse:
    """Handle PIN change by the worker themselves."""
    if not session.get("worker_id"):
        return _ingress_redirect("main.login")

    if request.method != "POST":
        return render_template("change_pin.html")

    new_pin: str = request.form.get("new_pin", "")
    new_pin_confirm: str = request.form.get("new_pin_confirm", "")

    if not new_pin or len(new_pin) < 4:
        flash("Der PIN muss mindestens 4 Ziffern lang sein.", "warning")
        return render_template("change_pin.html")

    if new_pin != new_pin_confirm:
        flash("Die PINs stimmen nicht überein.", "warning")
        return render_template("change_pin.html")

    from services.worker_service import _validate_pin
    try:
        _validate_pin(new_pin)
    except ValueError as exc:
        flash(str(exc), "warning")
        return render_template("change_pin.html")

    worker = db.session.get(Worker, session["worker_id"])
    if worker:
        worker.pin_hash = generate_password_hash(
            new_pin, method="pbkdf2:sha256", salt_length=16,
        )
        worker.needs_pin_change = False
        db.session.commit()
        flash("PIN erfolgreich geändert.", "success")
        return redirect_to("main.index")

    return render_template("change_pin.html")


_PIN_RESET_EXPIRY_MINUTES = 15


@limiter.limit("5 per minute")
def _forgot_pin_view() -> str | WerkzeugResponse:
    """Request a PIN reset link via email."""
    if request.method != "POST":
        workers = Worker.query.filter(
            Worker.is_active == True,  # noqa: E712
            Worker.email.isnot(None),
            Worker.email != "",
        ).order_by(Worker.name).all()
        return render_template("forgot_pin.html", workers=workers)

    worker_id = request.form.get("worker_id")
    if not worker_id:
        flash("Bitte wählen Sie einen Mitarbeiter aus.", "warning")
        return redirect_to("main.forgot_pin")

    worker = db.session.get(Worker, int(worker_id))
    if not worker or not worker.email:
        flash("Kein gültiger Mitarbeiter oder keine E-Mail hinterlegt.", "warning")
        return redirect_to("main.forgot_pin")

    # Generate secure token
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expiry = get_utc_now() + timedelta(minutes=_PIN_RESET_EXPIRY_MINUTES)

    # Store token hash and expiry in SystemSettings
    SystemSettings.set_setting(
        f"pin_reset_{worker.id}_hash", token_hash,
    )
    SystemSettings.set_setting(
        f"pin_reset_{worker.id}_expiry", expiry.isoformat(),
    )
    db.session.commit()

    # Build reset URL
    ingress = current_app.config.get("INGRESS_PATH", "")
    base_url = request.host_url.rstrip("/") + ingress
    reset_url = f"{base_url}{url_for('main.reset_pin_email', token=raw_token, wid=worker.id)}"

    from services.email_service import EmailService
    sent = EmailService.send_pin_reset(worker.name, reset_url, worker.email)

    if sent:
        flash("Ein Link zum Zurücksetzen wurde an Ihre E-Mail gesendet.", "success")
    else:
        flash("E-Mail konnte nicht gesendet werden. Bitte kontaktieren Sie den Administrator.", "warning")

    return redirect_to("main.login")


@limiter.limit("10 per minute")
def _reset_pin_email_view() -> str | WerkzeugResponse:
    """Handle the PIN reset link from email."""
    token = request.args.get("token", "")
    wid = request.args.get("wid", type=int)

    if not token or not wid:
        flash("Ungültiger Reset-Link.", "error")
        return redirect_to("main.login")

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    stored_hash = SystemSettings.get_setting(f"pin_reset_{wid}_hash") or ""
    expiry_str = SystemSettings.get_setting(f"pin_reset_{wid}_expiry") or ""

    if not stored_hash or token_hash != stored_hash:
        flash("Ungültiger oder bereits verwendeter Reset-Link.", "error")
        return redirect_to("main.login")

    from datetime import datetime
    try:
        expiry = datetime.fromisoformat(expiry_str)
    except (ValueError, TypeError):
        flash("Ungültiger Reset-Link.", "error")
        return redirect_to("main.login")

    if get_utc_now() > expiry:
        flash("Der Reset-Link ist abgelaufen.", "error")
        return redirect_to("main.login")

    worker = db.session.get(Worker, wid)
    if not worker or not worker.is_active:
        flash("Mitarbeiter nicht gefunden.", "error")
        return redirect_to("main.login")

    # Invalidate token (single use)
    SystemSettings.set_setting(f"pin_reset_{wid}_hash", "")
    SystemSettings.set_setting(f"pin_reset_{wid}_expiry", "")

    # Log worker in and force PIN change
    session.clear()
    session["worker_id"] = worker.id
    session["worker_name"] = worker.name
    session["is_admin"] = worker.role == WorkerRole.ADMIN.value
    session["role"] = worker.role or "worker"
    session.permanent = True

    worker.needs_pin_change = True
    db.session.commit()

    flash("Bitte setzen Sie jetzt einen neuen PIN.", "success")
    return redirect_to("main.change_pin")


def _profile_view() -> str | WerkzeugResponse:
    """Display and update the worker profile / OOO settings."""
    if not session.get("worker_id"):
        return _ingress_redirect("main.login")

    worker = db.session.get(Worker, session["worker_id"])
    if not worker:
        return redirect_to("main.logout")

    if request.method == "POST" and request.form.get("action") == "update_ooo":
        _update_ooo(worker)
        flash("Abwesenheitseinstellungen aktualisiert.", "success")
        return redirect_to("main.profile")

    if request.method == "POST" and request.form.get("action") == "update_notifications":
        _update_notifications(worker)
        flash("Benachrichtigungseinstellungen aktualisiert.", "success")
        return redirect_to("main.profile")

    if request.method == "POST" and request.form.get("action") == "update_email":
        _update_email(worker)
        flash("E-Mail-Adresse aktualisiert.", "success")
        return redirect_to("main.profile")

    if request.method == "POST" and request.form.get("action") == "update_push_notifications":
        _update_push_notifications(worker)
        flash("Push-Benachrichtigungseinstellungen aktualisiert.", "success")
        return redirect_to("main.profile")

    other_workers: list[Worker] = (
        Worker.query
        .filter(Worker.is_active == True, Worker.id != worker.id)  # noqa: E712
        .order_by(Worker.name)
        .all()
    )
    notifications: list[Notification] = (
        Notification.query
        .filter_by(user_id=worker.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
    return render_template(
        "profile.html",
        worker=worker,
        workers=other_workers,
        notifications=notifications,
    )


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------

def _find_valid_token(hashed_tokens: list[str], token: str) -> int:
    """Return the index of the matching hash, or ``-1``."""
    for idx, hashed in enumerate(hashed_tokens):
        if check_password_hash(hashed, token):
            return idx
    return -1


def _update_email(worker: Worker) -> None:
    """Apply email form data to *worker*."""
    raw_email = (request.form.get("email") or "").strip()
    if raw_email:
        parts = raw_email.split("@")
        valid = (
            len(parts) == 2
            and len(parts[0]) > 0
            and "." in parts[1]
            and len(parts[1]) >= 3
            and " " not in raw_email
        )
        if not valid:
            from flask import flash as _flash
            _flash("Ungültige E-Mail-Adresse.", "warning")
            return
    worker.email = raw_email or None
    db.session.commit()


def _update_push_notifications(worker: Worker) -> None:
    """Apply push notification preference and remove subscriptions if disabled."""
    enabled = request.form.get("push_notifications_enabled") == "on"
    worker.push_notifications_enabled = enabled
    if not enabled:
        from models import PushSubscription
        PushSubscription.query.filter_by(worker_id=worker.id).delete()
    db.session.commit()


def _update_notifications(worker: Worker) -> None:
    """Apply notification preference form data to *worker*."""
    worker.email_notifications_enabled = (
        request.form.get("email_notifications_enabled") == "on"
    )
    db.session.commit()


def _update_ooo(worker: Worker) -> None:
    """Apply out-of-office form data to *worker*."""
    worker.is_out_of_office = request.form.get("is_out_of_office") == "on"
    delegate_id_str = request.form.get("delegate_to_id", "")
    if delegate_id_str.isdigit():
        delegate_id = int(delegate_id_str)
        if delegate_id != worker.id:
            worker.delegate_to_id = delegate_id
            db.session.commit()
            return
    worker.delegate_to_id = None
    db.session.commit()


# ------------------------------------------------------------------
# Route registration
# ------------------------------------------------------------------

def register_routes(bp: Blueprint) -> None:
    """Register authentication routes on *bp*."""
    bp.add_url_rule(
        "/login", "login", view_func=_login_view, methods=["GET", "POST"],
    )
    bp.add_url_rule(
        "/logout", "logout", view_func=_logout_view, methods=["GET", "POST"],
    )
    bp.add_url_rule(
        "/setup", "setup", view_func=_setup_view, methods=["GET", "POST"],
    )
    bp.add_url_rule(
        "/recover_pin", "recover_pin",
        view_func=_recover_pin_view, methods=["GET", "POST"],
    )
    bp.add_url_rule(
        "/change-pin", "change_pin",
        view_func=_change_pin_view, methods=["GET", "POST"],
    )
    bp.add_url_rule(
        "/forgot-pin", "forgot_pin",
        view_func=_forgot_pin_view, methods=["GET", "POST"],
    )
    bp.add_url_rule(
        "/reset-pin", "reset_pin_email",
        view_func=_reset_pin_email_view, methods=["GET"],
    )
    bp.add_url_rule(
        "/profile", "profile",
        view_func=_profile_view, methods=["GET", "POST"],
    )
