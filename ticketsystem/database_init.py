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

def init_database(app, *, logger=None):
    """Run migrations and seed defaults. Must be called within app context."""
    if logger is None:
        logger = app.logger

    # Guard: skip during test collection unless explicitly allowed
    if 'pytest' in sys.modules and not app.config.get('TESTING'):
        return

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
