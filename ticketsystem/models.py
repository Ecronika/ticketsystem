"""
Models module.

Defines SQLAlchemy database models for Apprentice, Tool, Check, etc.
"""
from datetime import datetime, timezone

from enums import CheckType
from extensions import db



class SystemSettings(db.Model):
    """
    Key-Value store for system-wide configuration.

    Used for: Backup Schedules, Retention Policy, Feature Flags
    """

    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.String(200), nullable=True)

    @staticmethod
    def get_setting(key, default=None):
        """Retrieve a setting value."""
        try:
            setting = db.session.get(SystemSettings, key)
            return setting.value if setting else default
        except Exception:  # pylint: disable=broad-exception-caught
            return default

    @staticmethod
    def set_setting(key, value):
        """Set or update a system setting."""
        try:
            # Use with_for_update to lock the row (if supported by DB/Driver)
            setting = SystemSettings.query.filter_by(
                key=key).with_for_update().first()
            if not setting:
                setting = SystemSettings(key=key, value=str(value))
                db.session.add(setting)
            else:
                setting.value = str(value)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise


class Ticket(db.Model):
    """
    Placeholder model for the new Ticket System.
    """
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<Ticket {self.title}>'

