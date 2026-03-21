"""
Database Initialization module.

Handles creation of tables, migrations, and seeding of default data.
Uses Dependency Injection to decouple from the global Flask app object.
"""
import sys
from werkzeug.security import generate_password_hash
from flask_migrate import upgrade as flask_upgrade
from models import SystemSettings, Worker
from extensions import db

def _seed_default_settings(app, logger):
    """Seed initial system settings and bootstrap worker."""
    # Default admin_pin_hash (superseded by Worker pins)
    if not SystemSettings.query.filter_by(key="admin_pin_hash").first():
        db.session.add(SystemSettings(key="admin_pin_hash", value=generate_password_hash("0000")))

    # SME Shortcuts
    if not SystemSettings.query.filter_by(key="ticket_shortcuts").first():
        db.session.add(SystemSettings(key="ticket_shortcuts", value="Prüfen,Bestellt,Erledigt,Rückruf"))

    # Initial Onboarding Flag
    if not SystemSettings.query.filter_by(key="onboarding_complete").first():
        db.session.add(SystemSettings(key="onboarding_complete", value="false"))

    # Bootstrap Worker (if none exists)
    if not Worker.query.first():
        bootstrap_admin = Worker(
            name="Admin (Bootstrap)",
            pin_hash=generate_password_hash("0000"),
            is_admin=True,
            role='admin',
            is_active=True
        )
        db.session.add(bootstrap_admin)
        if logger:
            logger.info("Database: Seeded bootstrap worker 'Admin (Bootstrap)' with PIN '0000'")

    db.session.commit()

def _ensure_critical_columns(logger):
    """
    Manually ensure critical columns exist before migrations run.
    This fixes inconsistent states from previous failed or non-Alembic upgrades.
    """
    try:
        engine = db.engine
        inspector = db.inspect(engine)
        tables = inspector.get_table_names()
        
        if 'worker' in tables:
            columns = [c['name'] for c in inspector.get_columns('worker')]
            with engine.connect() as conn:
                # Critical columns that might be missing from v1.2.0 or failed v1.3.0 attempts
                # Note: SQLite doesn't support Multiple ADD COLUMN in one statement easily without batch
                # but these are single ADD COLUMNs which are safe.
                if 'failed_login_count' not in columns:
                    logger.info("Repair: Adding worker.failed_login_count")
                    conn.execute(db.text("ALTER TABLE worker ADD COLUMN failed_login_count INTEGER DEFAULT 0"))
                if 'locked_until' not in columns:
                    logger.info("Repair: Adding worker.locked_until")
                    conn.execute(db.text("ALTER TABLE worker ADD COLUMN locked_until DATETIME"))
                if 'needs_pin_change' not in columns:
                    logger.info("Repair: Adding worker.needs_pin_change")
                    conn.execute(db.text("ALTER TABLE worker ADD COLUMN needs_pin_change BOOLEAN DEFAULT 0"))
                if 'role' not in columns:
                    logger.info("Repair: Adding worker.role")
                    conn.execute(db.text("ALTER TABLE worker ADD COLUMN role VARCHAR(20)"))
                if 'is_active' not in columns:
                    logger.info("Repair: Adding worker.is_active")
                    conn.execute(db.text("ALTER TABLE worker ADD COLUMN is_active BOOLEAN DEFAULT 1"))
                if 'is_admin' not in columns:
                    logger.info("Repair: Adding worker.is_admin")
                    conn.execute(db.text("ALTER TABLE worker ADD COLUMN is_admin BOOLEAN DEFAULT 0"))
                conn.commit()

        if 'ticket' in tables:
            columns = [c['name'] for c in inspector.get_columns('ticket')]
            with engine.connect() as conn:
                if 'is_deleted' not in columns:
                    logger.info("Repair: Adding ticket.is_deleted")
                    conn.execute(db.text("ALTER TABLE ticket ADD COLUMN is_deleted BOOLEAN DEFAULT 0"))
                if 'due_date' not in columns:
                    logger.info("Repair: Adding ticket.due_date")
                    conn.execute(db.text("ALTER TABLE ticket ADD COLUMN due_date DATETIME"))
                conn.commit()
                
    except Exception as e:
        logger.warning("Repair: Auto-repair encountered an issue (non-fatal): %s", e)

def init_database(app, *, logger=None):
    """Run migrations and seed defaults. Must be called within app context."""
    if logger is None:
        logger = app.logger

    # Guard: skip during test collection unless explicitly allowed
    if 'pytest' in sys.modules and not app.config.get('TESTING'):
        return

    # Preliminary schema repair for mission-critical columns
    _ensure_critical_columns(logger)

    # Note: caller (app.py) ensures app_context()
    logger.info("Database: Running migrations...")
    try:
        flask_upgrade()
        logger.info("Database: Schema is up to date.")
    except Exception as e:
        import traceback
        logger.critical("Database: Migration FAILED. Manual intervention required: %s", e)
        logger.error(traceback.format_exc())
        db.session.rollback()
        # CRITICAL: No more fallback to create_all() to avoid untracked states
        raise

    logger.info("Database: Seeding defaults...")
    try:
        _seed_default_settings(app, logger)
        logger.info("Database: Initialization finished successfully.")
    except Exception as e:
        db.session.rollback()
        logger.error("Database: Seeding failed: %s", e)
        raise
