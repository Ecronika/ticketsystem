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
    """Generic database initialization with automatic migrations."""
    if logger is None:
        logger = app.logger

    # Guard against running during tests if not explicitly allowed
    if 'pytest' in sys.modules and not app.config.get('TESTING'):
        return

    with app.app_context():
        logger.info("Database: Initialization started...")
        
        try:
            # Automatic Migrations via Alembic/Flask-Migrate
            # This handles both fresh installs (create_all equivalent) and upgrades
            logger.info("Database: Running migrations...")
            flask_upgrade()
            logger.info("Database: Schema is up to date.")
            
            # Seed default system settings
            _seed_default_settings(app, logger)
            logger.info("Database: Initialization finished successfully.")
        except Exception as e:
            logger.error("Database: Initialization failed: %s", e)
            db.session.rollback()
            # If migration fails, we might fall back to create_all for completely fresh DBs
            # though flask_upgrade() should handle it if 'migrations' folder is present.
            try:
                db.create_all()
                logger.info("Database: Fallback to db.create_all() finished.")
            except Exception as e2:
                logger.error("Database: Fallback failed: %s", e2)
