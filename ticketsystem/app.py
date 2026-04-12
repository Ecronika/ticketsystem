"""Main application entry point.

Configures and initialises the Flask application, extensions, logging,
security headers, scheduler jobs, template filters, and error handlers.
"""

import atexit
import json
import logging
import os
import queue
import secrets
import sqlite3
import stat
import sys
import time
from datetime import datetime, timedelta, timezone
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from typing import Any, Dict
from zoneinfo import ZoneInfo

from flask import (
    Flask,
    Response,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFError
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.wrappers import Response as WerkzeugResponse

from enums import ELEVATED_ROLES, ApprovalStatus, TicketPriority, TicketStatus, WorkerRole
from exceptions import DomainError
from extensions import Config, csrf, db, limiter, scheduler
from metrics import (
    ACTIVE_SESSIONS,
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
)
from routes import main_bp
from routes.metrics import metrics_bp
from services import BackupService
from services.backup_service import is_maintenance_mode
from utils import get_utc_now


# ---------------------------------------------------------------------------
# Application version (read from config.yaml)
# ---------------------------------------------------------------------------

def _read_app_version() -> str:
    """Read the application version from ``config.yaml``."""
    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "config.yaml",
    )
    try:
        with open(config_path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip().startswith("version:"):
                    return line.split(":", 1)[1].strip().strip("\"'")
    except FileNotFoundError:
        pass
    return "0.0.0-unknown"


APP_VERSION: str = _read_app_version()

# ---------------------------------------------------------------------------
# Flask app creation & WSGI wrapper
# ---------------------------------------------------------------------------

app: Flask = Flask(__name__)
app.wsgi_app = ProxyFix(  # type: ignore[assignment]
    app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1,
)

IS_STANDALONE: bool = os.environ.get("STANDALONE_MODE") == "true"
IS_HOMEASSISTANT: bool = (not IS_STANDALONE) and (
    os.environ.get("SUPERVISOR_TOKEN") is not None
    or os.environ.get("HAS_INGRESS") == "1"
)
SSL_ACTIVE: bool = os.environ.get("REQUIRE_HTTPS", "0") == "1"

# ---------------------------------------------------------------------------
# Core configuration
# ---------------------------------------------------------------------------

app.config.update(
    VERSION=APP_VERSION,
    SESSION_COOKIE_NAME=(
        "ticket_session_tls" if SSL_ACTIVE else "ticket_session_plain"
    ),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_PATH="/",
    SESSION_COOKIE_SAMESITE="None" if SSL_ACTIVE else "Lax",
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,
    WTF_CSRF_TIME_LIMIT=28800,
    WTF_CSRF_SSL_STRICT=False,
    WTF_CSRF_SAMESITE="None" if SSL_ACTIVE else "Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    SESSION_COOKIE_SECURE=SSL_ACTIVE,
    WTF_CSRF_ENABLED=True,
    DATA_DIR=Config.get_data_dir(),
)

if not os.environ.get("DATA_DIR"):
    logging.info("DATA_DIR not set. Using default: %s", Config.get_data_dir())

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

data_dir: str = Config.get_data_dir()
os.makedirs(data_dir, exist_ok=True)
db_path: str = Config.get_db_path()
log_file: str = os.path.join(data_dir, "app.log")


def _make_formatter() -> logging.Formatter:
    """Create the standard log formatter."""
    return logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


file_handler = RotatingFileHandler(log_file, maxBytes=10_000_000, backupCount=3)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(_make_formatter())

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(_make_formatter())


def _configure_logging_ha() -> None:
    """Set up async queue-based logging for Home Assistant mode."""
    log_queue: queue.Queue[Any] = queue.Queue(10_000)
    listener = QueueListener(
        log_queue, file_handler, console_handler, respect_handler_level=True,
    )
    listener.start()
    app.logger.addHandler(QueueHandler(log_queue))
    atexit.register(listener.stop)
    app.logger.info("Logging: Async (QueueListener) enabled for HA.")


def _configure_logging_standalone() -> None:
    """Set up synchronous logging for standalone / Gunicorn mode."""
    gunicorn_logger = logging.getLogger("gunicorn.error")
    if gunicorn_logger.handlers:
        app.logger.handlers = gunicorn_logger.handlers
        app.logger.setLevel(gunicorn_logger.level)
        app.logger.addHandler(file_handler)
        app.logger.info(
            "Logging: Gunicorn integration enabled. [v%s]", APP_VERSION,
        )
    else:
        app.logger.addHandler(console_handler)
        app.logger.addHandler(file_handler)
        app.logger.info(
            "Logging: Direct console output enabled. [v%s]", APP_VERSION,
        )

    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(console_handler)
        root.setLevel(logging.INFO)


if IS_STANDALONE:
    _configure_logging_standalone()
else:
    _configure_logging_ha()

app.logger.setLevel(logging.INFO)
app.logger.info(
    "Config: SSL_ACTIVE=%s, CSRF_ENABLED=%s, SAMESITE=%s [v%s]",
    SSL_ACTIVE,
    app.config.get("WTF_CSRF_ENABLED", True),
    app.config.get("SESSION_COOKIE_SAMESITE"),
    APP_VERSION,
)

# ---------------------------------------------------------------------------
# Database configuration
# ---------------------------------------------------------------------------

app.config["DATA_DIR"] = data_dir
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# ---------------------------------------------------------------------------
# Secret key (persistent)
# ---------------------------------------------------------------------------


def _load_or_create_secret(secret_path: str) -> str:
    """Load the secret key from disk, creating it if absent."""
    if os.path.exists(secret_path):
        try:
            with open(secret_path, encoding="utf-8") as fh:
                return fh.read().strip()
        except OSError:
            return secrets.token_hex(32)

    key = secrets.token_hex(32)
    try:
        with open(secret_path, "w", encoding="utf-8") as fh:
            fh.write(key)
        os.chmod(secret_path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError as exc:
        app.logger.critical(
            "Could not persist secret key to %s: %s", secret_path, exc,
        )
    return key


app.secret_key = _load_or_create_secret(os.path.join(data_dir, "secret.key"))

# ---------------------------------------------------------------------------
# Extension initialisation
# ---------------------------------------------------------------------------

db.init_app(app)
csrf.init_app(app)
limiter.init_app(app)

migrations_dir = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "migrations",
)
migrate = Migrate(app, db, directory=migrations_dir, render_as_batch=True)

# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

if os.environ.get("RUN_SCHEDULER", "1") == "1" and not scheduler.running:
    try:
        scheduler.init_app(app)
        scheduler.start()

        with app.app_context():
            BackupService.schedule_backup_job(app)
            from services.scheduler_service import (
                schedule_recurring_job,
                schedule_reminder_job,
                schedule_sla_job,
            )
            schedule_recurring_job(app)
            schedule_sla_job(app)
            schedule_reminder_job(app)

        atexit.register(scheduler.shutdown)
    except RuntimeError as exc:
        app.logger.warning(
            "Scheduler initialization skipped or failed: %s", exc,
        )

# ---------------------------------------------------------------------------
# SQLite connection optimisation
# ---------------------------------------------------------------------------


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(
    dbapi_conn: Any, _connection_record: Any,
) -> None:
    """Set SQLite pragmas for performance and concurrency."""
    if isinstance(dbapi_conn, sqlite3.Connection):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA busy_timeout = 30000")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA cache_size = -10000")
        cursor.execute("PRAGMA synchronous = NORMAL")
        cursor.execute("PRAGMA temp_store = MEMORY")
        cursor.execute("PRAGMA mmap_size = 268435456")
        cursor.execute("PRAGMA wal_autocheckpoint = 1000")
        cursor.close()


# ---------------------------------------------------------------------------
# Content-Security-Policy
# ---------------------------------------------------------------------------

if not IS_HOMEASSISTANT:
    from flask_talisman import Talisman

    Talisman(
        app,
        force_https=SSL_ACTIVE,
        session_cookie_secure=SSL_ACTIVE,
        strict_transport_security=SSL_ACTIVE,
        content_security_policy={
            "default-src": "'self'",
            "script-src": ["'self'", "cdn.jsdelivr.net", "unpkg.com"],
            "style-src": ["'self'", "cdn.jsdelivr.net", "'unsafe-inline'"],
            "img-src": ["'self'", "data:", "blob:"],
            "font-src": ["'self'", "cdn.jsdelivr.net"],
            "connect-src": ["'self'", "cdn.jsdelivr.net", "unpkg.com"],
        },
        content_security_policy_nonce_in=["script-src"],
    )
    app.logger.info(
        "Security: Flask-Talisman enabled (CSP + Security Headers, "
        "SSL_ACTIVE=%s)",
        SSL_ACTIVE,
    )
else:
    app.logger.info(
        "Security: Manual CSP headers enabled (Home Assistant Ingress mode)",
    )

# ---------------------------------------------------------------------------
# Blueprint registration
# ---------------------------------------------------------------------------

from routes.admin import admin_bp  # noqa: E402

app.register_blueprint(main_bp)
app.register_blueprint(metrics_bp)
app.register_blueprint(admin_bp, url_prefix="/admin")

# Public REST API (isolated blueprint)
from routes.api import register_api, api_bp as _api_bp  # noqa: E402
register_api(app)
csrf.exempt(_api_bp)

# CSRF exemptions (protected by rate-limiting + single-use token)
csrf.exempt("main.recover_pin")
csrf.exempt("main.reset_pin_email")


# ---------------------------------------------------------------------------
# PWA manifest – served dynamically so start_url reflects the HA ingress path
# ---------------------------------------------------------------------------

@app.route("/manifest.json")
def pwa_manifest() -> Response:
    """Serve the PWA manifest with a dynamic start_url for HA Ingress support."""
    ingress_path = request.headers.get("X-Ingress-Path", "").rstrip("/")
    manifest = {
        "name": "Ticketsystem Shopfloor",
        "short_name": "Tickets",
        "description": "Enterprise Ticket System for Workshop & Production",
        "start_url": f"{ingress_path}/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#0d6efd",
        "icons": [
            {
                "src": f"{ingress_path}/static/img/icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
            },
            {
                "src": f"{ingress_path}/static/img/icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
            },
        ],
    }
    return Response(
        json.dumps(manifest),
        mimetype="application/manifest+json",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


# ---------------------------------------------------------------------------
# Request lifecycle hooks
# ---------------------------------------------------------------------------

@app.before_request
def check_maintenance_mode() -> Response | None:
    """Return 503 while a DB restore is in progress."""
    if is_maintenance_mode() and request.endpoint not in ("static",):
        return Response(
            "Wiederherstellung läuft – bitte in Kürze erneut versuchen.",
            status=503,
            headers={"Retry-After": "10", "Content-Type": "text/plain; charset=utf-8"},
        )
    return None


@app.before_request
def before_request_metrics() -> None:
    """Start timer for request duration."""
    g.start_time = time.time()
    if request.endpoint != "static":
        ACTIVE_SESSIONS.inc()


@app.after_request
def after_request_metrics(response: Response) -> Response:
    """Record request duration and count."""
    endpoint = request.endpoint or ""
    if endpoint and endpoint not in ("static", "metrics.metrics"):
        latency = time.time() - getattr(g, "start_time", time.time())
        HTTP_REQUESTS_TOTAL.labels(
            method=request.method,
            endpoint=endpoint,
            http_status=response.status_code,
        ).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(
            method=request.method,
            endpoint=endpoint,
        ).observe(latency)
    return response


@app.before_request
def set_nonce() -> None:
    """Generate a random nonce for CSP on every request."""
    g.csp_nonce = secrets.token_urlsafe(16)


@app.after_request
def add_security_headers(response: Response) -> Response:
    """Add standard security headers to every response."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"

    if IS_HOMEASSISTANT:
        _set_manual_csp(response)

    if os.environ.get("REQUIRE_HTTPS", "0") == "1":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


def _set_manual_csp(response: Response) -> None:
    """Apply CSP header manually (Home Assistant Ingress mode)."""
    nonce = getattr(g, "csp_nonce", None)
    nonce_directive = f"'nonce-{nonce}'" if nonce else ""
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        f"script-src 'self' cdn.jsdelivr.net unpkg.com {nonce_directive}; "
        "style-src 'self' cdn.jsdelivr.net 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self' cdn.jsdelivr.net; "
        "connect-src 'self' cdn.jsdelivr.net unpkg.com"
    )


@app.teardown_request
def teardown_request_gauge(_exception: BaseException | None = None) -> None:
    """Decrease active sessions gauge on request teardown."""
    if request.endpoint != "static":
        ACTIVE_SESSIONS.dec()


@app.teardown_appcontext
def remove_session(_exception: BaseException | None = None) -> None:
    """Clean up the database session after each request."""
    db.session.remove()


# ---------------------------------------------------------------------------
# Session validation (zombie session kill)
# ---------------------------------------------------------------------------

_SESSION_EXEMPT_ENDPOINTS = frozenset({
    "main.login", "main.logout", "main.change_pin", "static", "metrics",
})


@app.before_request
def validate_session() -> WerkzeugResponse | None:
    """Re-validate authenticated sessions on every request."""
    worker_id = session.get("worker_id")
    if not worker_id:
        return None

    endpoint = request.endpoint or ""
    if endpoint in _SESSION_EXEMPT_ENDPOINTS or endpoint.startswith("metrics"):
        return None

    from models import Worker

    try:
        worker = db.session.get(Worker, worker_id)
    except SQLAlchemyError:
        worker = None

    if not worker or not worker.is_active:
        session.clear()
        flash(
            "Ihre Sitzung ist nicht mehr gültig. "
            "Bitte melden Sie sich erneut an.",
            "danger",
        )
        return redirect(url_for("main.login"))

    session["role"] = worker.role
    session["is_admin"] = worker.role == WorkerRole.ADMIN.value
    session["worker_name"] = worker.name

    # BUG-001: Block access to all pages while PIN change is pending
    if worker.needs_pin_change and endpoint not in (
        "main.change_pin", "main.logout", "static",
    ):
        flash(
            "Bitte ändern Sie zuerst Ihren PIN.",
            "warning",
        )
        return redirect(url_for("main.change_pin"))

    return None


# ---------------------------------------------------------------------------
# Context processors (inject_globals helpers extracted)
# ---------------------------------------------------------------------------

def _count_urgent_tickets(worker_id: int, now: datetime) -> int:
    """Count tickets due today or overdue assigned to *worker_id*."""
    from models import ChecklistItem, Team, Ticket

    today = now.date()
    team_ids = Team.team_ids_for_worker(worker_id)

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

    return Ticket.query.filter(
        Ticket.is_deleted.is_(False),
        Ticket.status != TicketStatus.ERLEDIGT.value,
        Ticket.due_date.isnot(None),
        Ticket.due_date <= today,
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
    ).count()


def _count_pending_approvals() -> int:
    """Count tickets awaiting management approval."""
    from models import Ticket

    from models import TicketApproval
    return Ticket.query.filter(
        Ticket.is_deleted.is_(False),
        Ticket.approval.has(TicketApproval.status == ApprovalStatus.PENDING.value),
    ).count()


def _count_unread_notifications(worker_id: int) -> int:
    """Count unread notifications for *worker_id*."""
    from models import Notification

    return Notification.query.filter_by(
        user_id=worker_id, is_read=False,
    ).count()


def _count_absent_critical(now: datetime) -> int:
    """Count critical tickets assigned to absent workers."""
    from models import Ticket, Worker

    now_date = now.date()
    days_to_friday = (4 - now_date.weekday()) % 7
    if days_to_friday == 0 and now_date.weekday() != 4:
        days_to_friday = 7
    week_end = now_date + timedelta(days=days_to_friday)

    absent_ids = [
        w.id
        for w in Worker.query.filter_by(
            is_active=True, is_out_of_office=True,
        ).all()
    ]
    if not absent_ids:
        return 0

    return Ticket.query.filter(
        Ticket.is_deleted.is_(False),
        Ticket.status.in_([
            TicketStatus.OFFEN.value,
            TicketStatus.IN_BEARBEITUNG.value,
        ]),
        Ticket.assigned_to_id.in_(absent_ids),
        db.or_(
            Ticket.priority == TicketPriority.HOCH.value,
            Ticket.due_date <= week_end,
        ),
    ).count()


def _is_worker_ooo(worker_id: int) -> bool:
    """Return whether the worker is currently out-of-office."""
    from models import Worker

    worker = db.session.get(Worker, worker_id)
    return bool(worker and worker.is_out_of_office)


def _safe_query(label: str, func: Any, *args: Any) -> Any:
    """Execute *func* and return its result, or 0 on failure."""
    try:
        return func(*args)
    except SQLAlchemyError as exc:
        app.logger.warning("inject_globals: %s query failed: %s", label, exc)
        return 0


@app.context_processor
def inject_globals() -> Dict[str, Any]:
    """Inject global variables into templates.

    Skips DB queries for static files and unauthenticated requests.
    """
    from models import SystemSettings

    from services._ticket_helpers import (
        MAX_UPLOAD_FILE_SIZE,
        MAX_UPLOAD_FILES,
        MAX_UPLOAD_TOTAL_SIZE,
    )

    base: Dict[str, Any] = {
        "ingress_path": request.headers.get("X-Ingress-Path", ""),
        "system_settings": SystemSettings,
        "TicketStatus": TicketStatus,
        "ApprovalStatus": ApprovalStatus,
        "WorkerRole": WorkerRole,
        "TicketPriority": TicketPriority,
        "urgent_count": 0,
        "pending_approval_count": 0,
        "unread_notifications_count": 0,
        "absent_entries_with_critical": 0,
        "MAX_UPLOAD_FILE_SIZE": MAX_UPLOAD_FILE_SIZE,
        "MAX_UPLOAD_TOTAL_SIZE": MAX_UPLOAD_TOTAL_SIZE,
        "MAX_UPLOAD_FILES": MAX_UPLOAD_FILES,
    }

    endpoint = request.endpoint or ""
    worker_id = session.get("worker_id")
    if not worker_id or endpoint in ("static", "metrics") or endpoint.startswith("metrics"):
        return base

    now_dt = get_utc_now()
    role = session.get("role")

    base["urgent_count"] = _safe_query(
        "urgent_count", _count_urgent_tickets, worker_id, now_dt,
    )

    if session.get("is_admin") or role in ELEVATED_ROLES:
        base["pending_approval_count"] = _safe_query(
            "pending_approval", _count_pending_approvals,
        )

    base["unread_notifications_count"] = _safe_query(
        "notification", _count_unread_notifications, worker_id,
    )

    if role in ELEVATED_ROLES:
        base["absent_entries_with_critical"] = _safe_query(
            "absent_critical", _count_absent_critical, now_dt,
        )

    try:
        base["worker_is_ooo"] = _is_worker_ooo(worker_id)
    except SQLAlchemyError:
        base["worker_is_ooo"] = False

    try:
        from models import Worker as _Worker
        _w = db.session.get(_Worker, worker_id)
        base["worker_ui_theme"] = (_w.ui_theme or "auto") if _w else "auto"
    except SQLAlchemyError:
        base["worker_ui_theme"] = "auto"

    return base


@app.context_processor
def inject_help() -> Dict[str, Any]:
    """Inject context-sensitive help content for the current page."""
    from help_content import HELP

    endpoint = request.endpoint or ""
    page_key = endpoint.replace("main.", "").replace("admin.", "admin_")
    role = session.get("role", "worker")
    help_data = HELP.get(page_key)

    if help_data:
        filtered_sections = [
            s for s in help_data.get("sections", [])
            if s.get("roles") is None or role in s.get("roles", [])
        ]
        page_help: Dict[str, Any] | None = {
            **help_data, "sections": filtered_sections,
        }
    else:
        page_help = None

    return {"page_help": page_help, "HELP": HELP}


# ---------------------------------------------------------------------------
# Template filters
# ---------------------------------------------------------------------------

@app.template_filter("local_time")
def local_time_filter(dt: datetime | None) -> datetime | str:
    """Localise UTC datetime to Europe/Berlin."""
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo("Europe/Berlin"))


@app.template_filter("datetime")
def datetime_filter(dt: datetime | None, fmt: str = "%d.%m.%Y %H:%M") -> str:
    """Format a datetime object."""
    if not dt:
        return ""
    return dt.strftime(fmt)


@app.template_filter("time")
def time_filter(dt: datetime | None, fmt: str = "%H:%M") -> str:
    """Format the time portion of a datetime object."""
    if not dt:
        return ""
    return dt.strftime(fmt)


@app.template_filter("time_ago")
def time_ago_filter(dt: datetime | None) -> str:
    """Return a pretty relative time string (German)."""
    if not dt:
        return ""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)

    now = get_utc_now()
    if now.tzinfo is not None:
        now = now.astimezone(timezone.utc).replace(tzinfo=None)

    seconds = (now - dt).total_seconds()
    if seconds < 60:
        return "jetzt"
    if seconds < 3600:
        return f"vor {int(seconds // 60)} Min."
    if seconds < 86400:
        return f"vor {int(seconds // 3600)} Std."
    return f"vor {int(seconds // 86400)} Tg."


_STATUS_LABELS: Dict[str, str] = {
    TicketStatus.OFFEN.value: "Offen",
    TicketStatus.IN_BEARBEITUNG.value: "In Bearbeitung",
    TicketStatus.WARTET.value: "Wartet",
    TicketStatus.ERLEDIGT.value: "Erledigt",
}


@app.template_filter("status_label")
def status_label_filter(status: str) -> str:
    """Translate internal status enums to human-readable label."""
    return _STATUS_LABELS.get(status, status)


_PRIO_LABELS: Dict[int, str] = {
    TicketPriority.HOCH.value: "Hoch",
    TicketPriority.MITTEL.value: "Mittel",
    TicketPriority.NIEDRIG.value: "Niedrig",
}


@app.template_filter("priority_label")
def priority_label_filter(priority: int) -> str:
    """Translate priority integer to human-readable label."""
    return _PRIO_LABELS.get(priority, f"P{priority}")


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(DomainError)
def handle_domain_error(exc: DomainError) -> tuple[Response | str, int]:
    """Map domain exceptions to the appropriate HTTP response."""
    code = exc.status_code
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": str(exc)}), code
    if code == 404:
        return render_template("404.html"), 404
    return render_template("400.html", error=str(exc)), code


@app.errorhandler(400)
def bad_request(exc: HTTPException) -> tuple[Response | str, int]:
    """Handle 400 Bad Request."""
    if request.path.startswith("/api/"):
        return jsonify({
            "success": False, "error": exc.description or "Bad Request",
        }), 400
    return render_template("400.html", error=exc.description), 400


@app.errorhandler(404)
def page_not_found(_exc: HTTPException) -> tuple[str, int]:
    """Handle 404 Not Found."""
    return render_template("404.html"), 404


@app.errorhandler(413)
def request_entity_too_large(_exc: HTTPException) -> WerkzeugResponse:
    """Handle 413 Payload Too Large."""
    app.logger.warning("File upload too large: %s", request.content_length)
    flash("Datei zu groß (maximal 16MB erlaubt).", "error")
    return redirect(url_for("main.index"))


@app.errorhandler(429)
def rate_limit_exceeded(_exc: HTTPException) -> tuple[WerkzeugResponse, int]:
    """Handle 429 Too Many Requests from Flask-Limiter."""
    app.logger.warning("Rate limit exceeded: %s", request.path)
    flash("Zu viele Versuche. Bitte 1 Minute warten.", "warning")
    next_url = request.referrer or url_for("main.index")
    return redirect(next_url), 429


@app.errorhandler(CSRFError)
def handle_csrf_error(exc: CSRFError) -> tuple[Response | str, int]:
    """Handle CSRF token errors."""
    app.logger.warning("CSRF Fehler: %s", exc.description)
    if request.path.startswith("/api/"):
        return jsonify({
            "success": False,
            "error": f"CSRF Fehler: {exc.description}",
        }), 400
    return render_template(
        "400.html",
        error=f"Sitzung abgelaufen (CSRF): {exc.description}.",
    ), 400


@app.errorhandler(Exception)
def handle_exception(exc: Exception) -> tuple[str, int] | Response:
    """Handle unhandled exceptions (pass through HTTP errors)."""
    if isinstance(exc, HTTPException):
        return exc
    app.logger.error("Unhandled Exception: %s", exc, exc_info=True)
    return render_template("500.html"), 500


# ---------------------------------------------------------------------------
# Development server
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    ssl_context: str | None = "adhoc" if SSL_ACTIVE else None
    if SSL_ACTIVE:
        app.logger.info(
            "Starte Server mit Ad-hoc-SSL-Zertifikat (REQUIRE_HTTPS=1)...",
        )
    else:
        app.logger.info(
            "Starte Server ohne SSL (plain HTTP) "
            "- setze REQUIRE_HTTPS=1 für HTTPS.",
        )
    app.run(host="0.0.0.0", port=5000, debug=debug_mode, ssl_context=ssl_context)
