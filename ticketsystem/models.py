from utils import get_utc_now
from datetime import datetime, timezone

import os
import logging
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError
from extensions import db, Config



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
        except SQLAlchemyError:
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

    # Absence Management
    is_out_of_office = db.Column(db.Boolean, default=False)
    delegate_to_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=True)
    delegate_to = db.relationship('Worker', remote_side=[id], foreign_keys=[delegate_to_id])

    def __repr__(self):
        return f'<Worker {self.name}>'


# Association table for Tickets and Tags
ticket_tags = db.Table('ticket_tags',
    db.Column('ticket_id', db.Integer, db.ForeignKey('ticket.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True)
)

worker_team = db.Table('worker_team',
    db.Column('worker_id', db.Integer, db.ForeignKey('worker.id'), primary_key=True),
    db.Column('team_id', db.Integer, db.ForeignKey('team.id'), primary_key=True)
)

class Team(db.Model):
    """
    Team model for grouping workers.
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    members = db.relationship('Worker', secondary=worker_team, backref=db.backref('teams', lazy='dynamic'))

    def __repr__(self):
        return f'<Team {self.name}>'


class Tag(db.Model):
    """
    Tag model for categorizing tickets.
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True, nullable=False)

    def __repr__(self):
        return f'<Tag {self.name}>'


class ChecklistItem(db.Model):
    """
    Sub-tasks for a ticket.
    """
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    is_completed = db.Column(db.Boolean, default=False)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=True)
    assigned_to = db.relationship('Worker', foreign_keys=[assigned_to_id])
    assigned_team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=True)
    assigned_team = db.relationship('Team', foreign_keys=[assigned_team_id])
    due_date = db.Column(db.DateTime, nullable=True)
    depends_on_item_id = db.Column(db.Integer, db.ForeignKey('checklist_item.id'), nullable=True)
    depends_on_item = db.relationship('ChecklistItem', remote_side='ChecklistItem.id', backref='dependent_items')

    def __repr__(self):
        return f'<ChecklistItem {self.title}>'


class ChecklistTemplate(db.Model):
    """
    Template for standardized checklist items (e.g., recurring maintenance).
    """
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    
    items = db.relationship('ChecklistTemplateItem', backref='template', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<ChecklistTemplate {self.title}>'

class ChecklistTemplateItem(db.Model):
    """
    Individual items within a ChecklistTemplate.
    """
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('checklist_template.id'), nullable=False)
    title = db.Column(db.String(150), nullable=False)

    def __repr__(self):
        return f'<ChecklistTemplateItem {self.title}>'


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
    assigned_to = db.relationship('Worker', backref='tickets', foreign_keys=[assigned_to_id])
    
    due_date = db.Column(db.DateTime, nullable=True)
    order_reference = db.Column(db.String(50), nullable=True)
    reminder_date = db.Column(db.DateTime, nullable=True)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    
    # Handwerk-Edition features
    assigned_team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=True)
    assigned_team = db.relationship('Team', backref='tickets')
    is_confidential = db.Column(db.Boolean, default=False, nullable=False)
    recurrence_rule = db.Column(db.String(50), nullable=True)
    next_recurrence_date = db.Column(db.DateTime, nullable=True)
    checklist_template_id = db.Column(db.Integer, db.ForeignKey('checklist_template.id'), nullable=True)
    checklist_template = db.relationship('ChecklistTemplate', backref='legacy_tickets')
    
    # Approval Workflow
    approval_status = db.Column(db.String(20), default='none', nullable=False) # none, pending, approved, rejected
    approved_by_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=True)
    approved_by = db.relationship('Worker', foreign_keys=[approved_by_id])
    approved_at = db.Column(db.DateTime, nullable=True)
    rejected_by_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=True)
    rejected_by = db.relationship('Worker', foreign_keys=[rejected_by_id])
    reject_reason = db.Column(db.Text, nullable=True)
    
    checklists = db.relationship('ChecklistItem', backref='ticket', cascade='all, delete-orphan')
    
    tags = db.relationship('Tag', secondary=ticket_tags, backref=db.backref('tickets', lazy='dynamic'))
    
    created_at = db.Column(db.DateTime, default=lambda: get_utc_now())
    updated_at = db.Column(db.DateTime, default=lambda: get_utc_now(), 
                           onupdate=lambda: get_utc_now())

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
    created_at = db.Column(db.DateTime, default=lambda: get_utc_now())

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
    
    created_at = db.Column(db.DateTime, default=lambda: get_utc_now())

    def __repr__(self):
        return f'<Comment by {self.author} on Ticket {self.ticket_id}>'


@event.listens_for(Attachment, 'after_delete')
def receive_after_delete(mapper, connection, target):
    """Delete the physical file when Attachment is deleted from DB."""
    try:
        if target.path:
            safe_filename = os.path.basename(target.path)
            if safe_filename and safe_filename not in ['.', '..']:
                data_dir = Config.get_data_dir()
                filepath = os.path.join(data_dir, 'attachments', safe_filename)
                if os.path.exists(filepath):
                    os.remove(filepath)
                    logging.getLogger(__name__).info(f"Deleted orphaned attachment file: {filepath}")
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to delete attachment {target.path}: {e}")
