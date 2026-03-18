"""
Database Initialization module.

Handles creation of tables, migrations, and seeding of default data.
Uses Dependency Injection to decouple from the global Flask app object.
"""
import sys
import sqlalchemy as sa
from werkzeug.security import generate_password_hash

from extensions import db


def _seed_default_settings(_app, logger):
    """Seed default system settings into the database."""
    from models import SystemSettings

    defaults = {
        'backup_retention_days': '30',
        'backup_interval': 'date',  # daily, weekly, never, date
        'backup_time': '03:00',
        'manufacturer_presets': 'Wera,Wiha,Knipex,Hazet,Stahlwille,Gedore,NWS',
        'admin_pin_hash': generate_password_hash("0000"),
    }

    for key, value in defaults.items():
        if SystemSettings.get_setting(key) is None:
            SystemSettings.set_setting(key, value)
            logger.info("Seeded default setting: %s", key)


def init_database(app, *, logger=None):
    """Generic database initialization."""
    if logger is None:
        logger = app.logger

    # Guard against running during tests if not explicitly allowed
    if 'pytest' in sys.modules and not app.config.get('TESTING'):
        return

    with app.app_context():
        logger.info("Database: Initialization started...")
        db.engine.dispose()

        try:
            # Create all tables defined in models.py
            db.create_all()
            logger.info("Database: Tables created (if not existing).")
            
            # Seed default system settings
            _seed_default_settings(app, logger)
            logger.info("Database: Initialization finished successfully.")
        except Exception as e:
            logger.error("Database: Initialization failed: %s", e)

