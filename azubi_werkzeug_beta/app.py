
"""
Main Application Entry Point.

Configures and initializes the Flask application.
"""
import atexit
import logging
import os
import queue
import secrets
import sqlite3
import sys
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler

from flask import (
    Flask, flash, redirect, render_template, request, url_for
)
from sqlalchemy import event
from sqlalchemy.engine import Engine
from werkzeug.exceptions import NotFound
from werkzeug.security import generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

from extensions import Config, csrf, db, limiter, scheduler
from services import BackupService
from routes import main_bp

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Security: Session Configuration
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB Upload Limit
    # 7 Days Validity (Prevent expiry in long sessions)
    WTF_CSRF_TIME_LIMIT=604800
    # SESSION_COOKIE_SECURE=True # Disabled for Ingress (SSL terminated by HA
    # Proxy)
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
    "Async logging initialized: File=%s, Console=stdout, Queue=ENABLED",
    log_file)

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
IS_HOMEASSISTANT = os.environ.get('SUPERVISOR_TOKEN') is not None

if not IS_HOMEASSISTANT:
    # Standalone deployment: Use Flask-Talisman
    from flask_talisman import Talisman
    Talisman(app,
             force_https=False,  # External proxy (nginx/traefik) handles SSL
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


def _add_column_if_missing(cursor, table, column, definition):
    """Add a column to a table if it does not exist."""
    cursor.execute(f'PRAGMA table_info("{table}")')
    columns = [info[1] for info in cursor.fetchall()]
    if column not in columns:
        app.logger.info(
            "Migrating DB: Adding '%s' column to %s table.", column, table)
        cursor.execute(f'ALTER TABLE "{table}" ADD COLUMN {column} {definition}')


def _apply_migrations(cursor):
    """Apply schema migrations to the database."""
    # --- Check 'tech_param_value' in 'check' table ---
    _add_column_if_missing(cursor, "check", "tech_param_value", "VARCHAR(50)")

    # --- Check 'incident_reason' in 'check' table (Phase 2) ---
    _add_column_if_missing(cursor, "check", "incident_reason", "VARCHAR(50)")

    # --- Check 'tech_param_label' in 'werkzeug' table ---
    _add_column_if_missing(cursor, "werkzeug", "tech_param_label", "VARCHAR(50)")

    # --- Phase 3: Audit Trail Columns in 'Check' ---
    cursor.execute('PRAGMA table_info("check")')
    check_columns_audit = [info[1] for info in cursor.fetchall()]

    if 'check_type' not in check_columns_audit:
        app.logger.info("Migrating DB: Phase 3 Columns...")
        cursor.execute(
            "ALTER TABLE \"check\" ADD COLUMN check_type VARCHAR(20) DEFAULT 'check'")
        cursor.execute(
            "ALTER TABLE \"check\" ADD COLUMN examiner VARCHAR(100)")
        cursor.execute(
            "ALTER TABLE \"check\" ADD COLUMN signature_azubi VARCHAR(200)")
        cursor.execute(
            "ALTER TABLE \"check\" ADD COLUMN signature_examiner VARCHAR(200)")
        cursor.execute(
            "ALTER TABLE \"check\" ADD COLUMN report_path VARCHAR(200)")

    # --- Phase 6: is_archived in 'Azubi' ---
    _add_column_if_missing(cursor, "azubi", "is_archived", "BOOLEAN DEFAULT 0")

    # --- v2.8.0: price on werkzeug, manufacturer on check ---
    cursor.execute("PRAGMA table_info(werkzeug)")
    werkzeug_cols_v28 = [info[1] for info in cursor.fetchall()]
    if 'price' not in werkzeug_cols_v28:
        app.logger.info(
            "Migrating DB: Adding 'price' column to werkzeug table.")
        cursor.execute(
            "ALTER TABLE werkzeug ADD COLUMN price FLOAT DEFAULT 0.0")

    cursor.execute('PRAGMA table_info("check")')
    check_cols_v28 = [info[1] for info in cursor.fetchall()]
    if 'manufacturer' not in check_cols_v28:
        app.logger.info(
            "Migrating DB: Adding 'manufacturer' column to check table.")
        cursor.execute(
            'ALTER TABLE "check" ADD COLUMN manufacturer VARCHAR(100)')

    _apply_indexes(cursor)


def _apply_indexes(cursor):
    """Apply database indexes."""
    # --- Phase 8: Performance Indexes ---
    cursor.execute("PRAGMA index_list('check')")
    indexes = [row[1] for row in cursor.fetchall()]

    if 'idx_check_session_id' not in indexes:
        app.logger.info("Migrating DB: Creating Index idx_check_session_id")
        cursor.execute(
            "CREATE INDEX idx_check_session_id ON \"check\" (session_id)")

    if 'idx_check_datum' not in indexes:
        app.logger.info("Migrating DB: Creating Index idx_check_datum")
        cursor.execute("CREATE INDEX idx_check_datum ON \"check\" (datum)")

    # --- Phase 9: UI Sorting Indexes (Performance Fix) ---
    cursor.execute("PRAGMA index_list('azubi')")
    azubi_indexes = [row[1] for row in cursor.fetchall()]
    if 'idx_azubi_name' not in azubi_indexes:
        app.logger.info("Migrating DB: Creating Index idx_azubi_name")
        cursor.execute("CREATE INDEX idx_azubi_name ON azubi (name)")

    cursor.execute("PRAGMA index_list('werkzeug')")
    werkzeug_indexes = [row[1] for row in cursor.fetchall()]
    if 'idx_werkzeug_name' not in werkzeug_indexes:
        app.logger.info("Migrating DB: Creating Index idx_werkzeug_name")
        cursor.execute("CREATE INDEX idx_werkzeug_name ON werkzeug (name)")


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
    """Create database tables and perform migrations (schema updates)."""
    with app.app_context():
        db.create_all()

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Explicit transaction for safety
            cursor.execute("BEGIN TRANSACTION")

            _apply_migrations(cursor)

            conn.commit()
            app.logger.info(
                "Database setup and migrations completed successfully.")

            # Seed default settings (idempotent — only if key missing)
            _seed_default_settings()
        except Exception as e:  # pylint: disable=broad-exception-caught
            conn.rollback()
            app.logger.critical(
                "Migration Failed! Rolled back changes. Error: %s", e)
            # We might want to exit here, but for now we just log critical
        finally:
            if conn:
                conn.close()


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
    # setup_database() # Already called above (unless pytest, but main implies
    # not pytest)
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.logger.info("Starte Server mit temporärem SSL-Zertifikat (adhoc)...")
    app.run(host='0.0.0.0', port=5000, debug=debug_mode, ssl_context='adhoc')
