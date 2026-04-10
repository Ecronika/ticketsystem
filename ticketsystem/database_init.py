"""Database Initialization module.

Handles creation of tables, migrations, and seeding of default data.
Uses dependency injection to decouple from the global Flask app object.
"""

import logging
import sys
import traceback
from typing import List, Optional

from flask import Flask
from flask_migrate import upgrade as flask_upgrade
from werkzeug.security import generate_password_hash

from enums import WorkerRole
from extensions import db
from models import SystemSettings, Worker


def _seed_default_settings(logger: logging.Logger) -> None:
    """Seed initial system settings and bootstrap worker."""
    _seed_setting("admin_pin_hash", generate_password_hash("0000"))
    _seed_setting("ticket_shortcuts", "Prüfen,Bestellt,Erledigt,Rückruf")
    _seed_setting("onboarding_complete", "false")
    _seed_bootstrap_admin(logger)
    db.session.commit()


def _seed_setting(key: str, value: str) -> None:
    """Insert a system setting only if it does not already exist."""
    if not SystemSettings.query.filter_by(key=key).first():
        db.session.add(SystemSettings(key=key, value=value))


def _seed_bootstrap_admin(logger: logging.Logger) -> None:
    """Create the initial admin worker when no workers exist."""
    if Worker.query.first():
        return
    bootstrap_admin = Worker(
        name="Admin (Bootstrap)",
        pin_hash=generate_password_hash("0000"),
        is_admin=True,
        role=WorkerRole.ADMIN.value,
        is_active=True,
    )
    db.session.add(bootstrap_admin)
    logger.info(
        "Database: Seeded bootstrap worker 'Admin (Bootstrap)' with PIN '0000'"
    )


def _ensure_critical_columns(logger: logging.Logger) -> None:
    """Manually ensure critical columns exist before migrations run.

    This fixes inconsistent states from previous failed or non-Alembic
    upgrades.
    """
    try:
        engine = db.engine
        inspector = db.inspect(engine)
        tables = inspector.get_table_names()

        with engine.begin() as conn:
            _repair_worker_table(conn, inspector, tables, logger)
            _repair_ticket_table(conn, inspector, tables, logger)
            _repair_comment_table(conn, inspector, tables, logger)
    except Exception as exc:
        logger.warning(
            "Repair: Auto-repair encountered an issue (non-fatal): %s", exc
        )


def _get_column_names(inspector: object, table: str) -> List[str]:
    """Return column names for the given table."""
    return [c["name"] for c in inspector.get_columns(table)]


def _add_column_if_missing(
    conn: object,
    columns: List[str],
    column_name: str,
    ddl: str,
    logger: logging.Logger,
) -> None:
    """Execute an ALTER TABLE only when the column is absent."""
    if column_name not in columns:
        logger.info("Repair: Adding %s", column_name)
        conn.execute(db.text(ddl))


def _repair_worker_table(
    conn: object,
    inspector: object,
    tables: List[str],
    logger: logging.Logger,
) -> None:
    """Ensure all required worker columns exist."""
    if "worker" not in tables:
        return
    columns = _get_column_names(inspector, "worker")
    repairs = [
        ("failed_login_count", "ALTER TABLE worker ADD COLUMN failed_login_count INTEGER DEFAULT 0"),
        ("locked_until", "ALTER TABLE worker ADD COLUMN locked_until DATETIME"),
        ("needs_pin_change", "ALTER TABLE worker ADD COLUMN needs_pin_change BOOLEAN DEFAULT 0"),
        ("role", "ALTER TABLE worker ADD COLUMN role VARCHAR(20)"),
        ("is_active", "ALTER TABLE worker ADD COLUMN is_active BOOLEAN DEFAULT 1"),
        ("is_admin", "ALTER TABLE worker ADD COLUMN is_admin BOOLEAN DEFAULT 0"),
        ("is_out_of_office", "ALTER TABLE worker ADD COLUMN is_out_of_office BOOLEAN DEFAULT 0"),
        ("delegate_to_id", "ALTER TABLE worker ADD COLUMN delegate_to_id INTEGER"),
    ]
    for col_name, ddl in repairs:
        _add_column_if_missing(conn, columns, col_name, ddl, logger)


def _repair_ticket_table(
    conn: object,
    inspector: object,
    tables: List[str],
    logger: logging.Logger,
) -> None:
    """Ensure all required ticket columns exist."""
    if "ticket" not in tables:
        return
    columns = _get_column_names(inspector, "ticket")
    repairs = [
        ("is_deleted", "ALTER TABLE ticket ADD COLUMN is_deleted BOOLEAN DEFAULT 0"),
        ("due_date", "ALTER TABLE ticket ADD COLUMN due_date DATE"),
    ]
    for col_name, ddl in repairs:
        _add_column_if_missing(conn, columns, col_name, ddl, logger)

    # due_date changed from DateTime to Date.  Truncate leftover datetime
    # strings so SQLAlchemy's Date processor can parse them.
    if "due_date" in columns:
        conn.execute(db.text(
            "UPDATE ticket SET due_date = substr(due_date, 1, 10)"
            " WHERE due_date IS NOT NULL AND length(due_date) > 10"
        ))


def _repair_comment_table(
    conn: object,
    inspector: object,
    tables: List[str],
    logger: logging.Logger,
) -> None:
    """Ensure all required comment columns exist."""
    if "comment" not in tables:
        return
    columns = _get_column_names(inspector, "comment")
    repairs = [
        ("author_id", "ALTER TABLE comment ADD COLUMN author_id INTEGER"),
        ("is_system_event", "ALTER TABLE comment ADD COLUMN is_system_event BOOLEAN DEFAULT 0"),
        ("event_type", "ALTER TABLE comment ADD COLUMN event_type VARCHAR(30)"),
    ]
    for col_name, ddl in repairs:
        _add_column_if_missing(conn, columns, col_name, ddl, logger)


def init_database(app: Flask, *, logger: Optional[logging.Logger] = None) -> None:
    """Run migrations and seed defaults.  Must be called within app context."""
    if logger is None:
        logger = app.logger

    if "pytest" in sys.modules and not app.config.get("TESTING"):
        return

    _ensure_critical_columns(logger)

    logger.info("Database: Running migrations...")
    try:
        flask_upgrade()
        logger.info("Database: Schema is up to date.")
    except Exception as exc:
        logger.critical(
            "Database: Migration FAILED. Manual intervention required: %s", exc
        )
        logger.error(traceback.format_exc())
        db.session.rollback()
        raise

    logger.info("Database: Seeding defaults...")
    try:
        _seed_default_settings(logger)
        logger.info("Database: Initialization finished successfully.")
    except Exception as exc:
        db.session.rollback()
        logger.error("Database: Seeding failed: %s", exc)
        raise
