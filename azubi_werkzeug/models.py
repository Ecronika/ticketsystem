"""
Models module.

Defines SQLAlchemy database models for Apprentice, Tool, Check, etc.
"""
from datetime import datetime, timezone
from enum import Enum
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


class CheckType(Enum):  # pylint: disable=too-few-public-methods
    """Enumeration of check types."""

    CHECK = 'check'
    ISSUE = 'issue'
    RETURN = 'return'
    EXCHANGE = 'exchange'


class Azubi(db.Model):
    """Model representing an apprentice."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    lehrjahr = db.Column(db.Integer, default=1)
    is_archived = db.Column(db.Boolean, default=False)
    checks = db.relationship('Check', backref='azubi', lazy=True)

    def get_dashboard_status(self, last_datum):
        """Compute dashboard status, CSS class, display text, sort order."""
        if not last_datum:
            return "Neu / Leer", "info", "Noch nie", 4
        now = datetime.now(timezone.utc)
        
        # Ensure last_datum is offset-aware to avoid TypeError
        if last_datum.tzinfo is None:
            last_datum = last_datum.replace(tzinfo=timezone.utc)
            
        days_since = (now - last_datum).days
        if days_since >= 90:
            return (
                "Überfällig (> 3 Mon.)", "danger",
                f"Vor {days_since} Tagen", 1)
        if days_since >= 62:
            return (
                "Prüfung fällig (< 4 Wochen)", "warning",
                f"Vor {days_since} Tagen", 2)
        from zoneinfo import ZoneInfo
        last_datum_local = last_datum.astimezone(ZoneInfo('Europe/Berlin'))
        return (
            "Geprüft", "success",
            last_datum_local.strftime("%d. %b %Y"), 3)

    def __repr__(self):
        """Return string representation."""
        return f'<Azubi {self.name}>'


class Werkzeug(db.Model):  # pylint: disable=too-few-public-methods
    """
    Werkzeug model.

    Represents a tool in the inventory.
    """

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    material_category = db.Column(db.String(20), default="standard")
    tech_param_label = db.Column(db.String(50), nullable=True)
    price = db.Column(db.Float, nullable=True, default=0.0)
    checks = db.relationship(
        'Check',
        backref='werkzeug',
        lazy=True,
        cascade="all, delete-orphan")

    def __repr__(self):
        """Return string representation."""
        return f'<Werkzeug {self.name}>'


class Examiner(db.Model):  # pylint: disable=too-few-public-methods
    """
    Examiner model.

    Represents an examiner/instructor.
    """

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

    def __repr__(self):
        """Return string representation."""
        return f'<Examiner {self.name}>'


class Check(db.Model):  # pylint: disable=too-few-public-methods
    """
    Check model.

    Represents a tool check/transaction.
    """

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(36), nullable=True, index=True)
    datum = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    azubi_id = db.Column(db.Integer, db.ForeignKey('azubi.id'), nullable=False)
    werkzeug_id = db.Column(
        db.Integer,
        db.ForeignKey('werkzeug.id'),
        nullable=False)
    bemerkung = db.Column(db.String(200), nullable=True)
    tech_param_value = db.Column(db.String(50), nullable=True)
    incident_reason = db.Column(db.String(50), nullable=True)

    # Audit Trail
    check_type = db.Column(db.String(20), default=CheckType.CHECK.value)
    examiner = db.Column(db.String(100), nullable=True)
    signature_azubi = db.Column(db.String(200), nullable=True)
    signature_examiner = db.Column(db.String(200), nullable=True)
    report_path = db.Column(db.String(200), nullable=True)
    manufacturer = db.Column(db.String(100), nullable=True)
