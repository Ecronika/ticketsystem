"""
Models module.

Defines SQLAlchemy database models for Apprentice, Tool, Check, etc.
"""
from datetime import datetime, timezone

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



class Worker(db.Model):
    """
    Worker model representing staff members in the enterprise.
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    pin_hash = db.Column(db.String(128), nullable=True) # Individual worker PIN
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    needs_pin_change = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<Worker {self.name}>'


class Ticket(db.Model):
    """
    Main Ticket model for tracking issues/tasks.
    """
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    
    # Use String for Enum persistence for simplicity in SQLite 
    # but handle via enums.py in the service layer.
    status = db.Column(db.String(20), default='offen', nullable=False)
    priority = db.Column(db.Integer, default=2, nullable=False) # 1=High, 2=Medium, 3=Low
    
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=True)
    assigned_to = db.relationship('Worker', backref='tickets')
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), 
                           onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<Ticket {self.title} ({self.status})>'


class Comment(db.Model):
    """
    Comment model for documenting the ticket history.
    """
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)
    ticket = db.relationship('Ticket', backref=db.backref('comments', cascade='all, delete-orphan'))
    
    author = db.Column(db.String(50), nullable=False) # String for unauthenticated flexibility
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<Comment by {self.author} on Ticket {self.ticket_id}>'

