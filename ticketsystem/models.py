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
    role = db.Column(db.String(20), nullable=True) # Role: admin, worker, viewer
    needs_pin_change = db.Column(db.Boolean, default=True)
    last_active = db.Column(db.DateTime, nullable=True)
    
    # Enterprise Security: Brute-force protection
    failed_login_count = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f'<Worker {self.name}>'


# Association table for Tickets and Tags
ticket_tags = db.Table('ticket_tags',
    db.Column('ticket_id', db.Integer, db.ForeignKey('ticket.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True)
)


class Tag(db.Model):
    """
    Tag model for categorizing tickets.
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True, nullable=False)

    def __repr__(self):
        return f'<Tag {self.name}>'


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
    
    due_date = db.Column(db.DateTime, nullable=True)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    
    tags = db.relationship('Tag', secondary=ticket_tags, backref=db.backref('tickets', lazy='dynamic'))
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.utcnow())
    updated_at = db.Column(db.DateTime, default=lambda: datetime.utcnow(), 
                           onupdate=lambda: datetime.utcnow())

    def __repr__(self):
        return f'<Ticket {self.title} ({self.status})>'


class Attachment(db.Model):
    """
    Attachment model for storing metadata about uploaded files/images.
    """
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)
    ticket = db.relationship('Ticket', backref=db.backref('attachments', cascade='all, delete-orphan'))
    
    path = db.Column(db.String(255), nullable=False)
    filename = db.Column(db.String(100), nullable=False)
    mime_type = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.utcnow())

    def __repr__(self):
        return f'<Attachment {self.filename} for Ticket {self.ticket_id}>'


class Comment(db.Model):
    """
    Comment model for documenting the ticket history.
    """
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)
    ticket = db.relationship('Ticket', backref=db.backref('comments', cascade='all, delete-orphan'))
    
    author = db.Column(db.String(50), nullable=False) # String for unauthenticated flexibility
    author_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=True) # Linked author for audit
    author_worker = db.relationship('Worker', foreign_keys=[author_id])
    
    text = db.Column(db.Text, nullable=False)
    is_system_event = db.Column(db.Boolean, default=False)
    event_type = db.Column(db.String(30), nullable=True) # e.g., 'STATUS_CHANGE', 'ASSIGNMENT'
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Comment by {self.author} on Ticket {self.ticket_id}>'

