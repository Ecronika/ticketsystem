"""
Models module.

Defines SQLAlchemy database models for Apprentice, Tool, Check, etc.
"""
from datetime import datetime
from enum import Enum
from extensions import db

# pylint: disable=too-few-public-methods


class SystemSettings(db.Model):
    """
    Key-Value store for system-wide configuration
    Used for: Backup Schedules, Retention Policy, Feature Flags
    """
    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.String(200), nullable=True)

    @staticmethod
    def get_setting(key, default=None):
        """Retrieve a setting value."""
        setting = SystemSettings.query.get(key)
        return setting.value if setting else default

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


class CheckType(Enum):
    """Enumeration of check types."""
    CHECK = 'check'
    ISSUE = 'issue'
    RETURN = 'return'
    EXCHANGE = 'exchange'


class Azubi(db.Model):
    """Model representing an apprentice."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    lehrjahr = db.Column(db.Integer, default=1)
    is_archived = db.Column(db.Boolean, default=False)
    checks = db.relationship('Check', backref='azubi', lazy=True)

    def __repr__(self):
        """String representation."""
        return f'<Azubi {self.name}>'


class Werkzeug(db.Model):
    """Model representing a tool."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    material_category = db.Column(db.String(20), default="standard")
    tech_param_label = db.Column(db.String(50), nullable=True)
    checks = db.relationship(
        'Check',
        backref='werkzeug',
        lazy=True,
        cascade="all, delete-orphan")

    def __repr__(self):
        """String representation."""
        return f'<Werkzeug {self.name}>'


class Examiner(db.Model):
    """Model representing an examiner."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

    def __repr__(self):
        """String representation."""
        return f'<Examiner {self.name}>'


class Check(db.Model):
    """Model representing a check/transaction."""
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(36), nullable=True, index=True)
    datum = db.Column(db.DateTime, default=datetime.now, index=True)
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
