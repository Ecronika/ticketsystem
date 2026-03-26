"""
Main Application Entry Point.

Configures and initializes the Flask application.
"""
from utils import get_utc_now

import atexit
import logging
import os
import queue
import secrets
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from zoneinfo import ZoneInfo

from flask import Flask, flash, g, jsonify, redirect, render_template, request, session, url_for
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFError
from sqlalchemy import event
from sqlalchemy.engine import Engine
from werkzeug.exceptions import HTTPException, NotFound
from werkzeug.middleware.proxy_fix import ProxyFix

from database_init import init_database
from extensions import Config, csrf, db, limiter, scheduler
from metrics import ACTIVE_SESSIONS, HTTP_REQUEST_DURATION_SECONDS, HTTP_REQUESTS_TOTAL
from routes import main_bp
from routes.metrics import metrics_bp
from services import BackupService
from enums import TicketStatus, TicketPriority, WorkerRole, ApprovalStatus

# Read version dynamically from config.yaml
_config_file = os.path.join(os.path.dirname(
    os.path.abspath(__file__)), 'config.yaml')
APP_VERSION = '0.0.0-unknown'
try:
    with open(_config_file, 'r', encoding='utf-8') as _f:
        for line in _f:
            if line.strip().startswith('version:'):
                APP_VERSION = line.split(
                    ':', 1)[1].strip().strip('"').strip("'")
                break
except FileNotFoundError:
    pass
app = Flask(__name__)
# Security: Application behind Reverse Proxy (Nginx/Ingress)
# Fixes URL generation for redirects and absolute links
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

IS_STANDALONE = os.environ.get('STANDALONE_MODE') == 'true'
# Home Assistant Check (Ingress usually sets headers, but we also check env)
IS_HOMEASSISTANT = (not IS_STANDALONE) and (
    os.environ.get('SUPERVISOR_TOKEN') is not None or os.environ.get(
        'HAS_INGRESS') == '1'
)

# Security: Session Configuration
# SSL is active only if explicitly requested ÃƒÂ¢€Ã¢â‚¬Â this is the single source of truth
# for cookie security. SameSite=None requires HTTPS+Secure; plain HTTP must use Lax.
SSL_ACTIVE = os.environ.get('REQUIRE_HTTPS', '0') == '1'

app.config.update(
    VERSION=APP_VERSION,
    SESSION_COOKIE_NAME='ticket_session_tls' if SSL_ACTIVE else 'ticket_session_plain',
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_PATH='/',  # Force root path to avoid Ingress/ProxyFix prefix issues
    # SameSite=None allows cookies inside iframes (HA Ingress), BUT browsers
    # strictly require Secure=True when SameSite=None ÃƒÂ¢€Ã¢â‚¬Â so this only applies over HTTPS.
    # Over plain HTTP we fall back to Lax (works everywhere except cross-site iframes).
    SESSION_COOKIE_SAMESITE='None' if SSL_ACTIVE else 'Lax',
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB Upload Limit
    # 8 Hours Validity (Aligned with session lifetime)
    WTF_CSRF_TIME_LIMIT=28800,
    # Disable strict HTTPS referer check ÃƒÂ¢€Ã¢â‚¬Â required for both plain HTTP and proxied setups
    WTF_CSRF_SSL_STRICT=False,
    # CSRF cookie SameSite must match session cookie policy
    WTF_CSRF_SAMESITE='None' if SSL_ACTIVE else 'Lax',
    # Auto-logout after 8 hours
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    # Secure flag ONLY when SSL is actually active ÃƒÂ¢€Ã¢â‚¬Â critical for plain HTTP operation
    SESSION_COOKIE_SECURE=SSL_ACTIVE,
    # CSRF protection re-enabled now that session cookies bypass browser isolation
    WTF_CSRF_ENABLED=True,
    DATA_DIR=Config.get_data_dir(),
)

# --- Environment Validation ---
# Ensure critical variables are set (or fallback is known)
# Note: SECRET_KEY is handled securely in the 'Security: Dynamic Secret Key' section below.
# We check DATA_DIR next to ensure the persistent storage location exists.

if not os.environ.get('DATA_DIR'):
    logging.info("DATA_DIR not set. Using default: %s", Config.get_data_dir())

# Logging Configuration - ASYNC (Non-blocking)
# Issue: Synchronous file I/O was blocking request threads during heavy logging
# Solution: QueueHandler writes to memory queue (instant), background
# thread handles disk I/O

# Determine log file location based on DATA_DIR
data_dir = Config.get_data_dir()
if not os.path.exists(data_dir):
    os.makedirs(data_dir)
db_path = Config.get_db_path()
log_file = os.path.join(data_dir, 'app.log')

# File handler
file_handler = RotatingFileHandler(
    log_file,
    maxBytes=10_000_000,  # 10MB
    backupCount=3
)
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
file_handler.setFormatter(file_formatter)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
console_handler.setFormatter(console_formatter)

# --- Logging Strategy ---
# HA Add-on: Use Async (QueueListener)
# Standalone: Use Sync (Direct) to avoid missed logs in docker logs
if not IS_STANDALONE:
    # LOG-1: Bounded queue (10 000 entries) prevents unbounded memory growth
    # if disk I/O stalls (e.g., full SD-card on Raspberry Pi).
    log_queue = queue.Queue(10_000)
    queue_listener = QueueListener(
        log_queue, file_handler, console_handler, respect_handler_level=True
    )
    queue_listener.start()
    app.logger.addHandler(QueueHandler(log_queue))
    atexit.register(queue_listener.stop)
    app.logger.info("Logging: Async (QueueListener) enabled for HA.")
else:
    # Standalone: Check if running under Gunicorn
    gunicorn_logger = logging.getLogger('gunicorn.error')
    if gunicorn_logger.handlers:
        # Inherit Gunicorn's handlers and level for seamless integration
        app.logger.handlers = gunicorn_logger.handlers
        app.logger.setLevel(gunicorn_logger.level)
        # Also add file handler for persistent logs
        app.logger.addHandler(file_handler)
        app.logger.info(
            "Logging: Gunicorn integration enabled. [v%s]", APP_VERSION)
    else:
        # Standard console logging (e.g. running app.py directly)
        app.logger.addHandler(console_handler)
        app.logger.addHandler(file_handler)
        app.logger.info(
            "Logging: Direct console output enabled. [v%s]", APP_VERSION)

    # Ensure root logger also reaches the console for libraries like Alembic
    # but clear existing ones first to avoid duplicates if Gunicorn already did it
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(console_handler)
        root.setLevel(logging.INFO)

app.logger.setLevel(logging.INFO)

app.logger.info(
    "Config: SSL_ACTIVE=%s, CSRF_ENABLED=%s, SAMESITE=%s [v%s]",
    SSL_ACTIVE,
    app.config.get('WTF_CSRF_ENABLED', True),
    app.config.get('SESSION_COOKIE_SAMESITE'),
    APP_VERSION
)

# Database configuration (using data_dir from logging setup above)
# data_dir, db_path already defined during logging init


# Export DATA_DIR for routes to use
app.config['DATA_DIR'] = data_dir


app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Security: Dynamic Secret Key (Persistent)
secret_file = os.path.join(data_dir, 'secret.key')
if os.path.exists(secret_file):
    try:
        with open(secret_file, 'r', encoding='utf-8') as f:
            app.secret_key = f.read().strip()
    except Exception:  # pylint: disable=broad-exception-caught
        app.secret_key = secrets.token_hex(32)
else:
    app.secret_key = secrets.token_hex(32)
    try:
        with open(secret_file, 'w', encoding='utf-8') as f:
            f.write(app.secret_key)
        # FIX-12: Restrict secret.key to owner-read/write only (chmod 600)
        import stat
        os.chmod(secret_file, stat.S_IRUSR | stat.S_IWUSR)
    except OSError as e:
        # CRITICAL: If this fails, sessions are invalid after every restart
        app.logger.critical(
            "Could not persist secret key to %s: %s", secret_file, e)

# --- Database Initialization (Legacy Block Moved) ---
# Note: Connections are optimized via the event listener below.


# Init Extensions - Order: DB FIRST, then Migrate
db.init_app(app)
csrf.init_app(app)
limiter.init_app(app)

# Init Migrate after db.init_app to ensure engine is configured
# Explicitly set the migrations directory to be relative to the app.py file
migrations_dir = os.path.join(os.path.dirname(
    os.path.abspath(__file__)), 'migrations')
migrate = Migrate(app, db, directory=migrations_dir, render_as_batch=True)


if not scheduler.running:
    try:
        scheduler.init_app(app)
        scheduler.start()

        # Restore Backup Schedule from DB
        with app.app_context():
            BackupService.schedule_backup_job(app)
            from services.scheduler_service import schedule_recurring_job
            schedule_recurring_job(app)
        
        # P3-3: Ensure clean scheduler shutdown
        atexit.register(lambda: scheduler.shutdown())
    except Exception as e:  # pylint: disable=broad-exception-caught
        # In multi-worker environments, the scheduler might already be running
        app.logger.warning("Scheduler initialization skipped or failed: %s", e)

# SQLite Connection Optimization (Fix for Worker Timeouts)


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_conn, _connection_record):
    """Set SQLite pragmas for better performance and concurrency.

    This fixes worker timeout issues caused by database locks.
    CRITICAL for multi-user concurrent access.
    """
    if isinstance(dbapi_conn, sqlite3.Connection):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA busy_timeout = 30000")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA cache_size = -10000")  # 10MB cache
        cursor.execute("PRAGMA synchronous = NORMAL")
        cursor.execute("PRAGMA temp_store = MEMORY")  # Temp data in RAM
        # 256MB memory-mapped I/O
        cursor.execute("PRAGMA mmap_size = 268435456")
        
        # Use standard logging for pragma logging to avoid context errors (OFFEN-03)
        logging.getLogger(__name__).debug("SQLite pragmas set: WAL=on, busy_timeout=30s")
        # Less frequent WAL checkpoints
        cursor.execute("PRAGMA wal_autocheckpoint = 1000")
        cursor.close()


# Security: Content-Security-Policy (Issue #3)
# CONDITIONAL: Use Talisman for standalone, manual headers for Home Assistant
# IS_HOMEASSISTANT is defined at the top of the file

if not IS_HOMEASSISTANT:
    # Standalone deployment: Use Flask-Talisman
    from flask_talisman import Talisman
    Talisman(app,
             force_https=SSL_ACTIVE,
             session_cookie_secure=SSL_ACTIVE,
             strict_transport_security=SSL_ACTIVE,
             content_security_policy={
                 'default-src': "'self'",
                 'script-src': ["'self'", 'cdn.jsdelivr.net', 'unpkg.com'],
                 'style-src': ["'self'", 'cdn.jsdelivr.net', "'unsafe-inline'"],
                 'img-src': ["'self'", 'data:'],
                 'font-src': ["'self'", 'cdn.jsdelivr.net'],
                 'connect-src': ["'self'", 'cdn.jsdelivr.net', 'unpkg.com']
             },
             content_security_policy_nonce_in=['script-src']
             )
    app.logger.info(
        "Security: Flask-Talisman enabled (CSP + Security Headers, "
        "SSL_ACTIVE=%s)", SSL_ACTIVE)
else:
    # Home Assistant Ingress: Talisman breaks X-Ingress-Path, manual headers are handled globally
    app.logger.info(
        "Security: Manual CSP headers enabled (Home Assistant Ingress mode)")

# Register Blueprints
from routes.admin import admin_bp
app.register_blueprint(main_bp)
app.register_blueprint(metrics_bp)
app.register_blueprint(admin_bp, url_prefix='/admin')


@app.errorhandler(429)
def rate_limit_exceeded(_e):
    """Handle 429 Too Many Requests from Flask-Limiter."""
    app.logger.warning('Rate limit exceeded: %s', request.path)
    flash('Zu viele Versuche. Bitte 1 Minute warten.', 'warning')
    next_url = request.referrer or url_for('main.index')
    return redirect(next_url), 429


# Exempt auth routes from global CSRF (Flask-WTF 1.2.2 requires endpoint strings,
# not function references ÃƒÂ¢€Ã¢â‚¬Â the protect() method matches against request.endpoint).
# Login/recover_pin are protected by rate-limiting (5/min) + PIN hash check.
csrf.exempt('main.login')
csrf.exempt('main.recover_pin')

# --- Prometheus Metrics Middleware ---


@app.before_request
def before_request_metrics():
    """Start timer for request duration."""
    g.start_time = time.time()
    if request.endpoint != 'static':
        ACTIVE_SESSIONS.inc()



@app.after_request
def after_request_metrics(response):
    """Record request duration and count."""
    # Ignore static files and the metrics endpoint itself
    if request.endpoint and request.endpoint not in ['static', 'metrics.metrics']:
        request_latency = time.time() - getattr(g, 'start_time', time.time())
        HTTP_REQUESTS_TOTAL.labels(
            method=request.method,
            endpoint=request.endpoint,
            http_status=response.status_code
        ).inc()

        HTTP_REQUEST_DURATION_SECONDS.labels(
            method=request.method,
            endpoint=request.endpoint
        ).observe(request_latency)

    return response


@app.before_request
def set_nonce():
    """Generate a random nonce for CSP on every request."""
    g.csp_nonce = secrets.token_urlsafe(16)


@app.after_request
def add_security_headers(response):
    """Add standard security headers to every response."""
    # Global headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    # CSP Nonce support
    nonce = getattr(g, 'csp_nonce', None)
    
    # IS_HOMEASSISTANT manual CSP (Talisman is disabled in this mode)
    if IS_HOMEASSISTANT:
        # P0-1: Avoid backslashes in f-strings for Python 3.11 compatibility
        nonce_directive = f"'nonce-{nonce}'" if nonce else ""
        csp_policy = (
            "default-src 'self'; "
            f"script-src 'self' cdn.jsdelivr.net unpkg.com {nonce_directive}; "
            "style-src 'self' cdn.jsdelivr.net 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self' cdn.jsdelivr.net; "
            "connect-src 'self' cdn.jsdelivr.net unpkg.com"
        )
        response.headers['Content-Security-Policy'] = csp_policy

    # SEC-05: Strict-Transport-Security (HSTS)
    if os.environ.get('REQUIRE_HTTPS', '0') == '1':
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
    return response


@app.teardown_request
def teardown_request_gauge(_exception=None):
    """Decrease active sessions gauge on request teardown."""
    if request.endpoint != 'static':
        ACTIVE_SESSIONS.dec()

# Database Session Cleanup (Prevent Connection Leaks)


@app.teardown_appcontext
def remove_session(_exception=None):
    """Ensure database session is properly cleaned up after each request.

    This prevents connection leaking, especially important when:
    - Multiple commits happen in single request
    - Exceptions occur during transactions
    - PDF generation fails after first commit

    Critical for SQLite connection pool management.
    """
    db.session.remove()


# --- Session Validation (Zombie Session Kill) ---

_SESSION_EXEMPT_ENDPOINTS = frozenset({
    'main.login', 'main.logout', 'main.change_pin', 'static', 'metrics'
})

@app.before_request
def validate_session():
    """SESSION-1: Re-validate authenticated sessions on every request.

    Ensures deactivated or role-changed workers cannot continue using
    the app via stale cookies (up to 8-hour lifetime).
    Loads the Worker via SQLAlchemy's identity map — effectively free
    after the first access per request context.
    """
    worker_id = session.get('worker_id')
    if not worker_id:
        return  # Unauthenticated — nothing to validate

    endpoint = request.endpoint or ''
    if endpoint in _SESSION_EXEMPT_ENDPOINTS or endpoint.startswith('metrics'):
        return  # Never redirect login/logout into a loop

    from models import Worker
    try:
        worker = db.session.get(Worker, worker_id)
    except Exception:  # pylint: disable=broad-exception-caught
        worker = None

    if not worker or not worker.is_active:
        session.clear()
        flash('Ihre Sitzung ist nicht mehr gültig. Bitte melden Sie sich erneut an.', 'danger')
        return redirect(url_for('main.login'))

    # Keep role in sync: if admin was demoted, clear elevated session flags
    if worker.role != session.get('role'):
        session['role'] = worker.role
        session['is_admin'] = (worker.role == WorkerRole.ADMIN.value)


# --- Jinja Filters ---


@app.context_processor
def inject_globals():
    """Inject global variables into templates. Skips DB queries for static/unauthenticated requests."""
    from models import SystemSettings, Ticket
    from enums import TicketStatus, ApprovalStatus, WorkerRole, TicketPriority
    from flask import request

    # FIX-06: Skip all DB queries for static assets and unrouted requests
    _endpoint = request.endpoint or ''
    _base = {
        'ingress_path': request.headers.get('X-Ingress-Path', ''),
        'system_settings': SystemSettings,
        'TicketStatus': TicketStatus,
        'ApprovalStatus': ApprovalStatus,
        'WorkerRole': WorkerRole,
        'TicketPriority': TicketPriority,
        'urgent_count': 0, 'pending_approval_count': 0,
        'unread_notifications_count': 0
    }
    if not session.get('worker_id') or _endpoint in ('static', 'metrics') or _endpoint.startswith('metrics'):
        return _base

    urgent_count = 0
    # FIX-03: Use .isnot(None) for correct SQL IS NOT NULL semantics
    now_dt = get_utc_now()
    limit_dt = now_dt.replace(hour=23, minute=59, second=59)
    try:
        urgent_count = Ticket.query.filter(
            Ticket.assigned_to_id == session['worker_id'],
            Ticket.is_deleted == False,
            Ticket.status != TicketStatus.ERLEDIGT.value,
            Ticket.due_date.isnot(None),
            Ticket.due_date <= limit_dt
        ).count()
    except Exception as e:  # pylint: disable=broad-exception-caught
        app.logger.warning("inject_globals: urgent_count query failed: %s", e)

    pending_approval_count = 0
    if session.get('is_admin'):
        try:
            pending_approval_count = Ticket.query.filter_by(
                is_deleted=False, 
                approval_status=ApprovalStatus.PENDING.value
            ).count()
        except Exception as e:  # pylint: disable=broad-exception-caught
            app.logger.warning("inject_globals: pending_approval query failed: %s", e)

    unread_notifications_count = 0
    from models import Notification
    try:
        unread_notifications_count = Notification.query.filter_by(
            user_id=session['worker_id'], 
            is_read=False
        ).count()
    except Exception as e:  # pylint: disable=broad-exception-caught
        app.logger.warning("inject_globals: notification query failed: %s", e)

    # NEU-02: DRY final return — merge into _base instead of repeating keys
    return {
        **_base,
        'urgent_count': urgent_count,
        'pending_approval_count': pending_approval_count,
        'unread_notifications_count': unread_notifications_count
    }


@app.template_filter('local_time')
def local_time_filter(dt):
    """Localize UTC datetime to Europe/Berlin."""
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo('Europe/Berlin'))


@app.template_filter('datetime')
def datetime_filter(dt, format='%d.%m.%Y %H:%M'):
    """Format a datetime object."""
    if not dt:
        return ""
    return dt.strftime(format)


@app.template_filter('time')
def time_filter(dt, format='%H:%M'):
    """Format a time from a datetime object."""
    if not dt:
        return ""
    return dt.strftime(format)


@app.template_filter('time_ago')
def time_ago_filter(dt):
    """Return a pretty relative time string."""
    if not dt:
        return ""
    # Standardize to naive UTC for calculation (SQLite compatibility)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    
    now = datetime.utcnow()
    diff = now - dt
    
    seconds = diff.total_seconds()
    if seconds < 60:
        return "jetzt"
    if seconds < 3600:
        return f"vor {int(seconds // 60)} Min."
    if seconds < 86400:
        return f"vor {int(seconds // 3600)} Std."
    return f"vor {int(seconds // 86400)} Tg."


@app.template_filter('status_label')
def status_label_filter(status):
    """Translate internal status enums to human label."""
    labels = {
        TicketStatus.OFFEN.value: 'Offen',
        TicketStatus.IN_BEARBEITUNG.value: 'In Bearbeitung',
        TicketStatus.WARTET.value: 'Wartet',
        TicketStatus.ERLEDIGT.value: 'Erledigt'
    }
    return labels.get(status, status)


@app.template_filter('priority_label')
def priority_label_filter(priority):
    """Translate priority integer to human label."""
    if priority == TicketPriority.HOCH.value:
        return 'Hoch'
    if priority == TicketPriority.MITTEL.value:
        return 'Mittel'
    if priority == TicketPriority.NIEDRIG.value:
        return 'Niedrig'
    return f'P{priority}'


# --- Global Error Handlers ---
@app.errorhandler(413)  # Payload Too Large
def request_entity_too_large(e):
    """Handle 413 Payload Too Large error."""
    # pylint: disable=unused-argument
    app.logger.warning("File upload too large: %s", request.content_length)
    flash('Datei zu groÃƒÆ’Ã…Â¸ (max. 2MB).', 'error')
    # fallback to index if manage is not available or context is unclear
    return redirect(url_for('main.index'))


@app.errorhandler(400)
def bad_request(e):
    """Handle 400 Bad Request error."""
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': e.description or 'Bad Request'}), 400
    return render_template('400.html', error=e.description), 400


@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    """Handle CSRF errors specifically."""
    app.logger.warning("CSRF Fehler: %s", e.description)
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': f'CSRF Fehler: {e.description}'}), 400
    return render_template('400.html', error=f"Sitzung abgelaufen (CSRF): {e.description}."), 400


@app.errorhandler(NotFound)
def page_not_found(e):
    """Handle 404 Not Found error."""
    # pylint: disable=unused-argument
    return render_template('404.html'), 404


@app.errorhandler(Exception)
def handle_exception(e):
    """Handle standard exceptions."""
    # pylint: disable=unused-argument

    # Pass through HTTP errors (like 400 Bad Request, 405 Method Not Allowed)
    # instead of turning them into 500 errors.
    if isinstance(e, HTTPException):
        return e

    app.logger.error("Unhandled Exception: %s", e, exc_info=True)
    return render_template('500.html'), 500


# --- Database Setup (Moved to init_db.py for production) ---
# Module-level initialization is disabled to avoid Gunicorn worker crashes.
# Production deployments should call 'python init_db.py' before starting the server.
# if 'pytest' not in sys.modules:
#     with app.app_context():
#         try:
#             init_database(app)
#         except Exception as e:
#             app.logger.critical("APPLICATION BOOT FAILED: Database initialization error: %s", e, exc_info=True)
#             raise


if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    require_https = os.environ.get('REQUIRE_HTTPS', '0') == '1'
    if require_https:
        app.logger.info(
            "Starte Server mit Ad-hoc-SSL-Zertifikat (REQUIRE_HTTPS=1)...")
        app.run(host='0.0.0.0', port=5000,
                debug=debug_mode, ssl_context='adhoc')
    else:
        app.logger.info(
            "Starte Server ohne SSL (plain HTTP) - setze REQUIRE_HTTPS=1 fÃƒÆ’Ã‚Â¼r HTTPS.")
        app.run(host='0.0.0.0', port=5000, debug=debug_mode)
