"""
Database Initialization module.

Handles creation of tables, migrations, and seeding of default data.
Uses Dependency Injection to decouple from the global Flask app object.
"""
import sys
from werkzeug.security import generate_password_hash
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
            is_active=True
        )
        db.session.add(bootstrap_admin)
        if logger:
            logger.info("Database: Seeded bootstrap worker 'Admin (Bootstrap)' with PIN '0000'")

    db.session.commit()

def _ensure_schema_sync(app, logger):
    """
    Manually check for and add missing columns for SQLite.
    (Pragmatic alternative to full Alembic migrations for SME setup).
    """
    from sqlalchemy import text
    
    # Missing columns in 'ticket' table
    migrations = [
        ("ticket", "status", "VARCHAR(20) DEFAULT 'offen'"),
        ("ticket", "priority", "INTEGER DEFAULT 2"),
        ("ticket", "assigned_to_id", "INTEGER"),
        ("ticket", "created_at", "DATETIME"),
        ("ticket", "updated_at", "DATETIME"),
        ("worker", "needs_pin_change", "BOOLEAN DEFAULT 1")
    ]
    
    for table, column, definition in migrations:
        try:
            # We use a raw SQL check or just try-except the ALTER
            db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
            db.session.commit()
            if logger:
                logger.info("Database Migration: Added missing '%s' column to '%s' table.", column, table)
        except Exception:
            db.session.rollback() # Column likely already exists or table doesn't exist yet

def init_database(app, *, logger=None):
    """Generic database initialization."""
    if logger is None:
        logger = app.logger

    # Guard against running during tests if not explicitly allowed
    if 'pytest' in sys.modules and not app.config.get('TESTING'):
        return

    with app.app_context():
        logger.info("Database: Initialization started...")
        
        try:
            # Create all tables defined in models.py
            db.create_all()
            logger.info("Database: Tables created (if not existing).")
            
            # Force schema sync for missing columns (create_all is no-op on existing tables)
            _ensure_schema_sync(app, logger)
            
            # Seed default system settings
            _seed_default_settings(app, logger)
            logger.info("Database: Initialization finished successfully.")
        except Exception as e:
            logger.error("Database: Initialization failed: %s", e)
            db.session.rollback()
