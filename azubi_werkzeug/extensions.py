"""
Extensions module.

Initializes Flask extensions (SQLAlchemy, Limiter, CSRF, Scheduler).
"""
import os
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_apscheduler import APScheduler  # pylint: disable=import-error

db = SQLAlchemy()
csrf = CSRFProtect()
scheduler = APScheduler()
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://"  # Explizit für Single-Worker-Setup
)


class Config:
    """Central Configuration Logic."""

    @staticmethod
    def get_base_dir():
        """Return the application root directory."""
        return os.path.abspath(os.path.dirname(__file__))

    @staticmethod
    def get_data_dir():
        """
        Determine the data directory.

        Priority:
        1. ENV 'DATA_DIR'
        2. Parent of ENV 'DB_PATH'
        3. Default: Application Root
        """
        if os.environ.get('DATA_DIR'):
            return os.path.abspath(os.environ.get('DATA_DIR'))

        if os.environ.get('DB_PATH'):
            return os.path.dirname(os.path.abspath(os.environ.get('DB_PATH')))

        return Config.get_base_dir()

    @staticmethod
    def get_db_path():
        """Return the absolute path to the SQLite database."""
        if os.environ.get('DB_PATH'):
            return os.environ.get('DB_PATH')
        return os.path.join(Config.get_data_dir(), 'werkzeug.db')

    @staticmethod
    def get_ha_options_path():
        """Return path to Home Assistant options (configurable)."""
        return os.environ.get('HA_OPTIONS_PATH', '/data/options.json')
