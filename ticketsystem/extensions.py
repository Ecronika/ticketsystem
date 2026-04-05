"""Extensions module.

Initializes Flask extensions (SQLAlchemy, Limiter, CSRF, Scheduler)
and provides centralised configuration helpers.
"""

import os
from typing import List

from flask_apscheduler import APScheduler
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event

db = SQLAlchemy()


# ---------------------------------------------------------------------------
# Global Transaction Lifecycle Hooks for Orphaned File Cleanup
# ---------------------------------------------------------------------------

@event.listens_for(db.session, "after_rollback")
def _handle_rollback_cleanup(session: db.session.__class__) -> None:
    """Delete files that were saved during a rolled-back transaction."""
    pending_files: List[str] = session.info.get("pending_files", [])
    for filepath in pending_files:
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except OSError:
            pass
    session.info["pending_files"] = []


@event.listens_for(db.session, "after_commit")
def _handle_commit_cleanup(session: db.session.__class__) -> None:
    """Clear the pending-files list after a successful commit."""
    session.info["pending_files"] = []


csrf = CSRFProtect()
scheduler = APScheduler()
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
)


class Config:
    """Central configuration logic for paths and directories."""

    @staticmethod
    def get_base_dir() -> str:
        """Return the application root directory."""
        return os.path.abspath(os.path.dirname(__file__))

    @staticmethod
    def get_data_dir() -> str:
        """Determine the data directory.

        Priority:
            1. ``DATA_DIR`` environment variable
            2. Parent directory of ``DB_PATH`` environment variable
            3. Application root (fallback)
        """
        data_dir_env = os.environ.get("DATA_DIR")
        if data_dir_env:
            return os.path.abspath(data_dir_env)

        db_path_env = os.environ.get("DB_PATH")
        if db_path_env:
            return os.path.dirname(os.path.abspath(db_path_env))

        return Config.get_base_dir()

    @staticmethod
    def get_db_path() -> str:
        """Return the absolute path to the SQLite database."""
        db_path_env = os.environ.get("DB_PATH")
        if db_path_env:
            return os.path.abspath(db_path_env)
        return os.path.join(Config.get_data_dir(), "werkzeug.db")

    @staticmethod
    def get_ha_options_path() -> str:
        """Return path to Home Assistant options (configurable)."""
        return os.environ.get("HA_OPTIONS_PATH", "/data/options.json")
