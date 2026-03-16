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
                "Database: Legacy DB without history. Stamping to baseline (449fb7b).")
            # Stamp to the first stable revision that matches core tables
            _db_stamp(revision='449fb7b61987')

        # Repair: Manually check for columns that might be missing due to previous bad stamps
        _repair_missing_columns(logger)

        logger.info("Database: Running migrations (upgrade)...")
        _db_upgrade()
        logger.info("Database: Migration finished.")
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(
            "Database: Schema initialization/migration failed: %s", e)


def _repair_missing_columns(logger):
    """
    Safety net for mis-stamped databases (v2.13.5 issue).
    Manually adds missing columns if they don't exist in the physical schema.
    """
    import sqlalchemy as sa
    try:
        inspector = sa.inspect(db.engine)
        
        # 1. Check table 'check'
        check_cols = [c['name'] for c in inspector.get_columns('check')]
        if 'price' not in check_cols:
            logger.info("Repair: Adding missing column 'check.price'")
            with op_batch('check') as batch_op:
                batch_op.add_column(sa.Column('price', sa.Float(), nullable=True))
        
        if 'manufacturer' not in check_cols:
            logger.info("Repair: Adding missing column 'check.manufacturer'")
            with op_batch('check') as batch_op:
                batch_op.add_column(sa.Column('manufacturer', sa.String(length=100), nullable=True))

        # 2. Check table 'werkzeug'
        werkzeug_cols = [c['name'] for c in inspector.get_columns('werkzeug')]
        if 'price' not in werkzeug_cols:
            logger.info("Repair: Adding missing column 'werkzeug.price'")
            with op_batch('werkzeug') as batch_op:
                batch_op.add_column(sa.Column('price', sa.Float(), nullable=True))

    except Exception as e:
        logger.warning("Repair: Column check/repair skipped or failed: %s", e)


def op_batch(table_name):
    """Helper for batch operations outside Alembic files."""
    from alembic import op
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    
    ctx = MigrationContext.configure(db.engine.connect())
    ops = Operations(ctx)
    return ops.batch_alter_table(table_name)


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
