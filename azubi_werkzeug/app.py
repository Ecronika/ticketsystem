# pylint: disable=line-too-long,wrong-import-order,too-many-lines,unnecessary-pass,too-many-locals,broad-exception-caught,import-outside-toplevel,mixed-line-endings,unused-import

"""
Main Application Entry Point.

Configures and initializes the Flask application.
"""
from flask import g
import atexit
import logging
import os
import queue
import secrets
import sqlite3
import sys
import time
from datetime import timedelta
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler

from flask import (
    Flask, flash, redirect, render_template, request, url_for
)
from sqlalchemy import event
from sqlalchemy.engine import Engine
from werkzeug.exceptions import NotFound
from werkzeug.security import generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_migrate import Migrate

from extensions import Config, csrf, db, limiter, scheduler
from services import BackupService
from routes import main_bp
from routes.metrics import metrics_bp
from metrics import HTTP_REQUESTS_TOTAL, HTTP_REQUEST_DURATION_SECONDS, ACTIVE_SESSIONS

import os
# Read version dynamically from config.yaml
_config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.yaml')
APP_VERSION = '0.0.0-unknown'
try:
    with open(_config_file, 'r', encoding='utf-8') as _f:
        for line in _f:
            if line.strip().startswith('version:'):
                APP_VERSION = line.split(':', 1)[1].strip().strip('"').strip("'")
                break
except FileNotFoundError:
    pass
app = Flask(__name__)
# Home Assistant Check (Ingress usually sets headers, but we also check env)
IS_HOMEASSISTANT = os.environ.get('SUPERVISOR_TOKEN') is not None or os.environ.get('HAS_INGRESS') == '1'

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Init Migrate
migrate = Migrate(app, db)

# Security: Session Configuration
# SSL is active only if explicitly requested — this is the single source of truth
# for cookie security. SameSite=None requires HTTPS+Secure; plain HTTP must use Lax.
SSL_ACTIVE = os.environ.get('REQUIRE_HTTPS', '0') == '1'

app.config.update(
    VERSION=APP_VERSION,
    SESSION_COOKIE_NAME='azubi_session_tls' if SSL_ACTIVE else 'azubi_session_plain',
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_PATH='/',  # Force root path to avoid Ingress/ProxyFix prefix issues
    # SameSite=None allows cookies inside iframes (HA Ingress), BUT browsers
    # strictly require Secure=True when SameSite=None — so this only applies over HTTPS.
    # Over plain HTTP we fall back to Lax (works everywhere except cross-site iframes).
    SESSION_COOKIE_SAMESITE='None' if SSL_ACTIVE else 'Lax',
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB Upload Limit
    # 7 Days Validity (Prevent expiry in long sessions)
    WTF_CSRF_TIME_LIMIT=604800,
    # Disable strict HTTPS referer check — required for both plain HTTP and proxied setups
    WTF_CSRF_SSL_STRICT=False,
    # CSRF cookie SameSite must match session cookie policy
    WTF_CSRF_SAMESITE='None' if SSL_ACTIVE else 'Lax',
    # Auto-logout after 8 hours
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    # Secure flag ONLY when SSL is actually active — critical for plain HTTP operation
    SESSION_COOKIE_SECURE=SSL_ACTIVE,
    # CSRF protection re-enabled now that session cookies bypass browser isolation
    WTF_CSRF_ENABLED=True,
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
# Note: We need to get DATA_DIR early for logging setup
data_dir = Config.get_data_dir()
if not os.path.exists(data_dir):
    os.makedirs(data_dir)
db_path = Config.get_db_path()
log_file = os.path.join(data_dir, 'app.log')

# Create log queue for async processing
log_queue = queue.Queue(-1)  # Unlimited size

# File handler - runs in BACKGROUND THREAD (non-blocking)
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

# Console handler - also in background thread
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
console_handler.setFormatter(console_formatter)

# Queue listener - processes log queue in background thread
queue_listener = QueueListener(
    log_queue, file_handler, console_handler, respect_handler_level=True
)
queue_listener.start()

# Queue handler - writes to queue (NON-BLOCKING, instant!)
queue_handler = QueueHandler(log_queue)

# App logger uses queue (no I/O blocking!)
app.logger.addHandler(queue_handler)
app.logger.setLevel(logging.INFO)

# Ensure listener stops cleanly on shutdown
atexit.register(queue_listener.stop)

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

# Ensure data directories exist
os.makedirs(os.path.join(data_dir, 'signatures'), exist_ok=True)
os.makedirs(os.path.join(data_dir, 'reports'), exist_ok=True)

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
    except OSError as e:
        # CRITICAL: If this fails, sessions are invalid after every restart
        app.logger.critical(
            "Could not persist secret key to %s: %s", secret_file, e)

# Init Extensions
db.init_app(app)
csrf.init_app(app)
limiter.init_app(app)

# C-5: Multi-Worker Guard — in-memory cache is process-local, unsafe for > 1 worker
_configured_workers = int(os.environ.get('GUNICORN_WORKERS', 1))
if _configured_workers > 1:
    app.logger.critical(
        "FATAL: GUNICORN_WORKERS=%d detected. The in-memory tool-assignment cache "
        "(_assigned_tools_cache) is process-local and will cause inventory "
        "inconsistencies with multiple workers. Set GUNICORN_WORKERS=1 or "
        "migrate to a shared cache (e.g. Redis).", _configured_workers
    )

if not scheduler.running:
    scheduler.init_app(app)
    scheduler.start()

    # Restore Backup Schedule from DB
    try:
        with app.app_context():
            BackupService.schedule_backup_job(app)
    except Exception as e:  # pylint: disable=broad-exception-caught
        app.logger.error("Failed to restore backup schedule: %s", e)

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
        # Less frequent WAL checkpoints
        cursor.execute("PRAGMA wal_autocheckpoint = 1000")
        cursor.close()
        app.logger.info(
            "SQLite pragmas set: busy_timeout=30s, WAL mode, cache=10MB, SD-optimized"
        )


# Security: Content-Security-Policy (Issue #3)
# CONDITIONAL: Use Talisman for standalone, manual headers for Home Assistant
# IS_HOMEASSISTANT is defined at the top of the file

if not IS_HOMEASSISTANT:
    # Standalone deployment: Use Flask-Talisman
    from flask_talisman import Talisman
    Talisman(app,
             force_https=(os.environ.get('REQUIRE_HTTPS', '0') == '1'),  # Redirect to HTTPS if enforced
             content_security_policy={
                 'default-src': "'self'",
                 'script-src': ["'self'", 'cdn.jsdelivr.net', 'unpkg.com', "'unsafe-inline'"],
                 'style-src': ["'self'", 'cdn.jsdelivr.net', "'unsafe-inline'"],
                 'img-src': ["'self'", 'data:'],
                 'font-src': ["'self'", 'cdn.jsdelivr.net'],
                 'connect-src': ["'self'", 'cdn.jsdelivr.net', 'unpkg.com']
             }
             )
    app.logger.info(
        "Security: Flask-Talisman enabled (CSP + Security Headers)")
else:
    # Home Assistant Ingress: Talisman breaks X-Ingress-Path, use manual
    # headers
    @app.after_request
    def add_security_headers(response):
        """Add manual Context Security Policy headers."""
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        # CSP headers (same policy as Talisman)
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' cdn.jsdelivr.net unpkg.com 'unsafe-inline'; "
            "style-src 'self' cdn.jsdelivr.net 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self' cdn.jsdelivr.net; "
            "connect-src 'self' cdn.jsdelivr.net unpkg.com"
        )
        return response

app.logger.info(
    "Security: Manual CSP headers enabled (Home Assistant Ingress mode)")

# Register Blueprints
app.register_blueprint(main_bp)
app.register_blueprint(metrics_bp)

@app.errorhandler(429)
def rate_limit_exceeded(e):
    """Handle 429 Too Many Requests from Flask-Limiter."""
    app.logger.warning('Rate limit exceeded: %s', request.path)
    flash('Zu viele Versuche. Bitte 1 Minute warten.', 'warning')
    next_url = request.referrer or url_for('main.index')
    return redirect(next_url), 429

# Exempt auth routes from global CSRF (Flask-WTF 1.2.2 requires endpoint strings,
# not function references — the protect() method matches against request.endpoint).
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

@app.teardown_request
def teardown_request_gauge(_exception=None):
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

# --- Helper to create DB and Seed Data ---


def _seed_default_settings():
    """Seed default system settings if not already present."""
    from models import SystemSettings  # pylint: disable=import-outside-toplevel
    defaults = {
        'manufacturer_presets': 'Wera,Wiha,Knipex,Hazet,Stahlwille,Gedore,NWS',
        'admin_pin_hash': generate_password_hash("0000"),
    }
    for key, value in defaults.items():
        if SystemSettings.get_setting(key) is None:
            SystemSettings.set_setting(key, value)
            app.logger.info("Seeded default setting: %s", key)


def setup_database():
    """Create database tables and seed default data."""
    with app.app_context():
        # db.create_all() has been replaced by Alembic migrations (flask db upgrade).
        # We only run seeding here. The actual schema is managed by Alembic.

        try:
            # Seed default settings (idempotent — only if key missing)
            _seed_default_settings()
        except Exception as e:  # pylint: disable=broad-exception-caught
            app.logger.error("Failed to seed default settings: %s", e)


# --- Global Error Handlers ---
@app.errorhandler(413)  # Payload Too Large
def request_entity_too_large(e):
    """Handle 413 Payload Too Large error."""
    # pylint: disable=unused-argument
    app.logger.warning("File upload too large: %s", request.content_length)
    flash('Datei zu groß (max. 2MB).', 'error')
    # fallback to index if manage is not available or context is unclear
    return redirect(url_for('main.index'))


@app.errorhandler(NotFound)
def page_not_found(e):
    """Handle 404 Not Found error."""
    # pylint: disable=unused-argument
    return render_template('404.html'), 404


@app.errorhandler(Exception)
def handle_exception(e):
    """Handle standard exceptions."""
    # pylint: disable=unused-argument
    app.logger.error("Unhandled Exception: %s", e, exc_info=True)
    return render_template('500.html'), 500


# Perform Database Setup & Migrations on Import
# This ensures tables/migrations exist when running via Gunicorn
# (which imports 'app' but skips 'if __name__ == "__main__"')
# Use a guard to prevent running during tests (when pytest imports app)
if 'pytest' not in sys.modules:
    with app.app_context():
        # Only run if not in a special context (like alembic, though we use manual migrations)
        # Checks are idempotent (safe to run multiple times)
        setup_database()


if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    require_https = os.environ.get('REQUIRE_HTTPS', '0') == '1'
    if require_https:
        app.logger.info("Starte Server mit Ad-hoc-SSL-Zertifikat (REQUIRE_HTTPS=1)...")
        app.run(host='0.0.0.0', port=5000, debug=debug_mode, ssl_context='adhoc')
    else:
        app.logger.info("Starte Server ohne SSL (plain HTTP) - setze REQUIRE_HTTPS=1 für HTTPS.")
        app.run(host='0.0.0.0', port=5000, debug=debug_mode)
