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
    """Decoupled database initialization."""
    if logger is None:
        logger = app.logger

    # Guard against running during tests if not explicitly allowed
    if 'pytest' in sys.modules and not app.config.get('TESTING'):
        return

    with app.app_context():
        logger.info("Database: Initialization started...")
        db.engine.dispose()

        tables = _inspect_current_state(logger)
        logger.info("Database: Current tables: %s",
                    ", ".join(tables) if tables else "None")

        _run_schema_management(tables, logger)

        _perform_seeding_and_backfill(app, logger)


def _inspect_current_state(logger):
    """Inspect current database tables."""
    try:
        inspector = sa.inspect(db.engine)
        return inspector.get_table_names()
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Database: Inspection failed: %s", e)
        return []


def _run_schema_management(tables, logger):
    """Handle create_all, stamping, and upgrading."""
    from flask_migrate import stamp as _db_stamp
    from flask_migrate import upgrade as _db_upgrade

    alembic_exists = 'alembic_version' in tables
    core_tables_exist = 'azubi' in tables

    try:
        if not core_tables_exist:
            logger.info(
                "Database: Core tables missing. Initializing via create_all...")
            db.create_all()
            _db_stamp()  # Set Alembic to HEAD
            logger.info("Database: Fresh install / Restore initialized.")
        elif not alembic_exists:
            logger.info(
                "Database: Legacy DB without history. Stamping to baseline.")
            _db_stamp()

        logger.info("Database: Running migrations (upgrade)...")
        _db_upgrade()
        logger.info("Database: Migration finished.")
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(
            "Database: Schema initialization/migration failed: %s", e)


def _perform_seeding_and_backfill(app, logger):
    """Execute seeding and data backfilling."""
    try:
        logger.info("Database: Starting seeding and backfill...")
        _seed_default_settings(app, logger)

        from services import CheckService
        count = CheckService.ensure_price_backfill()
        if count > 0:
            logger.info("Database: Backfilled %d checks.", count)
        logger.info("Database: Initialization finished successfully.")
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Database: Seeding/Backfill failed: %s", e)
