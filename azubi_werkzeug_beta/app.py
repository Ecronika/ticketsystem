
"""
Main Application Entry Point.

Configures and initializes the Flask application.
"""
from logging.handlers import RotatingFileHandler, QueueHandler, QueueListener
import os
import sys
import logging
import secrets
import queue
import atexit
import sqlite3

from flask import Flask, render_template, request, flash, redirect, url_for
from werkzeug.exceptions import NotFound
from sqlalchemy import event
from sqlalchemy.engine import Engine

from extensions import db, limiter, csrf, scheduler, Config
from services import BackupService, CheckService

app = Flask(__name__)

# Security: Session Configuration
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    MAX_CONTENT_LENGTH=16 * 1024 * 1024  # 16MB Upload Limit
    # SESSION_COOKIE_SECURE=True # Disabled for Ingress (SSL terminated by HA Proxy)
)

# --- Environment Validation ---
# Ensure critical variables are set (or fallback is known)
# Note: SECRET_KEY and DATA_DIR are handled below, but we log warnings for clarity.
if not os.environ.get('SECRET_KEY') and not os.path.exists(os.path.join(Config.get_base_dir(), 'secret.key')):
    logging.warning("No SECRET_KEY set and no secret.key file found. A new key will be generated (sessions invalid on restart).")

if not os.environ.get('DATA_DIR'):
    logging.info(f"DATA_DIR not set. Using default: {Config.get_data_dir()}")

# Logging Configuration - ASYNC (Non-blocking)
# Issue: Synchronous file I/O was blocking request threads during heavy logging
# Solution: QueueHandler writes to memory queue (instant), background thread handles disk I/O

# Determine log file location based on DATA_DIR
# Note: We need to get DATA_DIR early for logging setup
data_dir = Config.get_data_dir()
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
queue_listener = QueueListener(log_queue, file_handler, console_handler, respect_handler_level=True)
queue_listener.start()

# Queue handler - writes to queue (NON-BLOCKING, instant!)
queue_handler = QueueHandler(log_queue)

# App logger uses queue (no I/O blocking!)
app.logger.addHandler(queue_handler)
app.logger.setLevel(logging.INFO)

# Ensure listener stops cleanly on shutdown
atexit.register(queue_listener.stop)

app.logger.info(f"Async logging initialized: File={log_file}, Console=stdout, Queue=ENABLED")

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
    except Exception:
        app.secret_key = secrets.token_hex(32)
else:
    app.secret_key = secrets.token_hex(32)
    try:
        with open(secret_file, 'w', encoding='utf-8') as f:
            f.write(app.secret_key)
    except OSError:
        pass

# Init Extensions
db.init_app(app)
csrf.init_app(app)
limiter.init_app(app)

if not scheduler.running:
    scheduler.init_app(app)
    scheduler.start()
    
    # Restore Backup Schedule from DB
    try:
        BackupService.schedule_backup_job(app)
    except Exception as e:
        app.logger.error(f"Failed to restore backup schedule: {e}")

# SQLite Connection Optimization (Fix for Worker Timeouts)
# SQLite Connection Optimization (Fix for Worker Timeouts)

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """Set SQLite pragmas for better performance and concurrency.

    This fixes worker timeout issues caused by database locks.
    CRITICAL for multi-user concurrent access.
    """
    if isinstance(dbapi_conn, sqlite3.Connection):
        cursor = dbapi_conn.cursor()

        # CRITICAL: Set busy timeout to 30 seconds
        # SQLite waits up to 30s for lock release instead of failing immediately
        cursor.execute("PRAGMA busy_timeout = 30000")

        # WAL mode for better concurrent read/write
        # Allows simultaneous reads during writes - GAME CHANGER for concurrency!
        cursor.execute("PRAGMA journal_mode = WAL")

        # Increase cache size for better performance
        cursor.execute("PRAGMA cache_size = -10000")  # 10MB cache

        # Synchronous = NORMAL for better performance (safe with WAL mode)
        cursor.execute("PRAGMA synchronous = NORMAL")

        # NEW: Optimize for SD card (User Request)
        cursor.execute("PRAGMA temp_store = MEMORY")  # Temp data in RAM
        cursor.execute("PRAGMA mmap_size = 268435456")  # 256MB memory-mapped I/O
        cursor.execute("PRAGMA wal_autocheckpoint = 1000")  # Less frequent WAL checkpoints

        cursor.close()
        app.logger.info("SQLite pragmas set: busy_timeout=30s, WAL mode, cache=10MB, SD-optimized (mmap/mem-temp)")

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
            'script-src': ["'self'", 'cdn.jsdelivr.net', "'unsafe-inline'"],  # Inline scripts in templates
            'style-src': ["'self'", 'cdn.jsdelivr.net', "'unsafe-inline'"],  # Bootstrap inline styles
            'img-src': ["'self'", 'data:'],  # data: for inline images/QR codes
            'font-src': ["'self'", 'cdn.jsdelivr.net'],
            'connect-src': ["'self'", 'cdn.jsdelivr.net']  # For source maps
        }
    )
    app.logger.info("Security: Flask-Talisman enabled (CSP + Security Headers)")
else:
    # Home Assistant Ingress: Talisman breaks X-Ingress-Path, use manual headers
    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        # CSP headers (same policy as Talisman)
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' cdn.jsdelivr.net 'unsafe-inline'; "
            "style-src 'self' cdn.jsdelivr.net 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self' cdn.jsdelivr.net; "
            "connect-src 'self' cdn.jsdelivr.net"
        )
        return response
    app.logger.info("Security: Manual CSP headers enabled (Home Assistant Ingress mode)")

# Register Blueprints
app.register_blueprint(main_bp)

# Database Session Cleanup (Prevent Connection Leaks)
@app.teardown_appcontext
def remove_session(exception=None):
    """Ensure database session is properly cleaned up after each request.

    This prevents connection leaking, especially important when:
    - Multiple commits happen in single request
    - Exceptions occur during transactions
    - PDF generation fails after first commit

    Critical for SQLite connection pool management.
    """
    db.session.remove()

# --- Helper to create DB and Seed Data ---
def setup_database():
    """Create database tables and perform migrations (schema updates)."""
    with app.app_context():
        db.create_all()

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # --- Check 'tech_param_value' in 'check' table ---
            cursor.execute('PRAGMA table_info("check")')
            check_columns = [info[1] for info in cursor.fetchall()]
            if 'tech_param_value' not in check_columns:
                app.logger.info("Migrating DB: Adding 'tech_param_value' column to check table.")
                cursor.execute('ALTER TABLE "check" ADD COLUMN tech_param_value VARCHAR(50)')
                conn.commit()

            # --- Check 'incident_reason' in 'check' table (Phase 2) ---
            if 'incident_reason' not in check_columns:
                app.logger.info("Migrating DB: Adding 'incident_reason' column to check table.")
                cursor.execute('ALTER TABLE "check" ADD COLUMN incident_reason VARCHAR(50)')
                conn.commit()

            # --- Check 'tech_param_label' in 'werkzeug' table ---
            cursor.execute("PRAGMA table_info(werkzeug)")
            werkzeug_columns = [info[1] for info in cursor.fetchall()]
            if 'tech_param_label' not in werkzeug_columns:
                app.logger.info("Migrating DB: Adding 'tech_param_label' column to werkzeug table.")
                cursor.execute("ALTER TABLE werkzeug ADD COLUMN tech_param_label VARCHAR(50)")
                conn.commit()

            # --- Phase 3: Audit Trail Columns in 'Check' ---
            cursor.execute('PRAGMA table_info("check")')
            check_columns_audit = [info[1] for info in cursor.fetchall()]

            if 'check_type' not in check_columns_audit:
                app.logger.info("Migrating DB: Phase 3 Columns...")
                cursor.execute("ALTER TABLE \"check\" ADD COLUMN check_type VARCHAR(20) DEFAULT 'check'")
                cursor.execute("ALTER TABLE \"check\" ADD COLUMN examiner VARCHAR(100)")
                cursor.execute("ALTER TABLE \"check\" ADD COLUMN signature_azubi VARCHAR(200)")
                cursor.execute("ALTER TABLE \"check\" ADD COLUMN signature_examiner VARCHAR(200)")
                cursor.execute("ALTER TABLE \"check\" ADD COLUMN report_path VARCHAR(200)")
                conn.commit()

            # --- Phase 3.5: Examiner Table ---
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='examiner'")
            if not cursor.fetchone():
                pass

            # --- Phase 6: is_archived in 'Azubi' ---
            cursor.execute("PRAGMA table_info(azubi)")
            azubi_columns = [info[1] for info in cursor.fetchall()]
            if 'is_archived' not in azubi_columns:
                app.logger.info("Migrating DB: Adding 'is_archived' column to azubi table.")
                cursor.execute("ALTER TABLE azubi ADD COLUMN is_archived BOOLEAN DEFAULT 0")
                conn.commit()

            # --- Phase 8: Performance Indexes ---
            cursor.execute("PRAGMA index_list('check')")
            # index_list returns (seq, name, unique)
            indexes = [row[1] for row in cursor.fetchall()]

            if 'idx_check_session_id' not in indexes:
                app.logger.info("Migrating DB: Creating Index idx_check_session_id")
                cursor.execute("CREATE INDEX idx_check_session_id ON \"check\" (session_id)")
                conn.commit()

            if 'idx_check_datum' not in indexes:
                app.logger.info("Migrating DB: Creating Index idx_check_datum")
                cursor.execute("CREATE INDEX idx_check_datum ON \"check\" (datum)")
                conn.commit()

            # --- Phase 9: UI Sorting Indexes (Performance Fix) ---
            cursor.execute("PRAGMA index_list('azubi')")
            azubi_indexes = [row[1] for row in cursor.fetchall()]
            if 'idx_azubi_name' not in azubi_indexes:
                app.logger.info("Migrating DB: Creating Index idx_azubi_name")
                cursor.execute("CREATE INDEX idx_azubi_name ON azubi (name)")
                conn.commit()

            cursor.execute("PRAGMA index_list('werkzeug')")
            werkzeug_indexes = [row[1] for row in cursor.fetchall()]
            if 'idx_werkzeug_name' not in werkzeug_indexes:
                app.logger.info("Migrating DB: Creating Index idx_werkzeug_name")
                cursor.execute("CREATE INDEX idx_werkzeug_name ON werkzeug (name)")
                conn.commit()

            conn.close()
        except Exception as e:
            app.logger.error(f"Migration Info: {e}")



# --- Global Error Handlers ---
@app.errorhandler(413) # Payload Too Large
def request_entity_too_large(e):
    """Handle 413 Payload Too Large error."""
    app.logger.warning("File upload too large: %s", request.content_length)
    flash('Datei zu groß (max. 2MB).', 'error')
    # fallback to index if manage is not available or context is unclear
    return redirect(url_for('main.index'))

@app.errorhandler(Exception)
def handle_exception(e):
    """Handle standard exceptions."""
    # Pass through HTTP errors
    if isinstance(e, int):
        return e

    # Handle 404 separately to avoid issues with request.endpoint being None
    if isinstance(e, NotFound):
        return """
        <!DOCTYPE html>
        <html><head><title>404 - Nicht gefunden</title></head>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1>404 - Seite nicht gefunden</h1>
            <p><a href="/">Zurück zur Startseite</a></p>
        </body></html>
        """, 404

    app.logger.error("Unhandled Exception: %s", e, exc_info=True)
    return render_template('base.html', content=f"<h1>Ein unerwarteter Fehler ist aufgetreten</h1><p>{e}</p>"), 500

if __name__ == '__main__':
    setup_database()
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)
