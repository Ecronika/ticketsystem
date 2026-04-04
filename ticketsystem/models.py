"""
Database Models for Ticket System.
"""
import os
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError

from extensions import db, Config
from utils import get_utc_now
from enums import TicketStatus, TicketPriority, WorkerRole





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
    email = db.Column(db.String(120), nullable=True)  # Optional email for notifications

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
    members = db.relationship('Worker', secondary=worker_team, backref=db.backref('teams', lazy='dynamic'), cascade="all, delete")

    @staticmethod
    def team_ids_for_worker(worker_id):
        """Return list of team IDs the given worker belongs to."""
        rows = db.session.query(worker_team.c.team_id).filter(
            worker_team.c.worker_id == worker_id
        ).all()
        return [r[0] for r in rows]

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
    status = db.Column(db.String(20), default=TicketStatus.OFFEN.value, nullable=False)
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
    
    # Kundendienst / Customer Contact (v1.15.0)
    contact_name = db.Column(db.String(100), nullable=True)
    contact_phone = db.Column(db.String(50), nullable=True)
    contact_channel = db.Column(db.String(20), nullable=True)  # telefon, email, persoenlich, petra
    callback_requested = db.Column(db.Boolean, default=False, nullable=False)
    callback_due = db.Column(db.DateTime, nullable=True)

    # Approval Workflow
    approval_status = db.Column(db.String(20), default='none', nullable=False) # none, pending, approved, rejected
    approved_by_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=True)
    approved_by = db.relationship('Worker', foreign_keys=[approved_by_id])
    approved_at = db.Column(db.DateTime, nullable=True)
    rejected_by_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=True)
    rejected_by = db.relationship('Worker', foreign_keys=[rejected_by_id])
    reject_reason = db.Column(db.Text, nullable=True)
    last_escalated_at = db.Column(db.DateTime, nullable=True)  # SLA: tracks last escalation to prevent spam

    checklists = db.relationship('ChecklistItem', backref='ticket', cascade='all, delete-orphan')
    
    tags = db.relationship('Tag', secondary=ticket_tags, backref=db.backref('tickets', lazy='dynamic'))
    
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, 
                           onupdate=get_utc_now)

    def __repr__(self):
        return f'<Ticket {self.title} ({self.status})>'

    def is_accessible_by(self, worker_id, role):
        """Return True if the given worker may access this ticket.

        Non-confidential tickets are always accessible.
        Confidential tickets are only accessible to:
          - Admins, HR, and Management roles
          - The assigned worker
          - Any worker assigned to a checklist item
          - The original author (identified via TICKET_CREATED event comment)
        """
        if not self.is_confidential:
            return True

        if role in (WorkerRole.ADMIN.value, WorkerRole.HR.value, WorkerRole.MANAGEMENT.value):
            return True
        if self.assigned_to_id == worker_id:
            return True
        if any(c.assigned_to_id == worker_id for c in self.checklists):
            return True
        # Team-based access: worker is member of assigned team
        _tids = Team.team_ids_for_worker(worker_id) if worker_id else []
        if _tids:
            if self.assigned_team_id in _tids:
                return True
            if any(c.assigned_team_id in _tids for c in self.checklists):
                return True
        # PERF-2: Avoid lazy-loading all comments — use a targeted COUNT query
        # instead of iterating self.comments (which can be hundreds of rows).
        from sqlalchemy.orm import object_session
        sess = object_session(self)
        if sess is not None:
            from models import Comment # local import to avoid circular ref / early access
            exists = sess.query(Comment).filter(
                Comment.ticket_id == self.id,
                Comment.author_id == worker_id,
                Comment.event_type == 'TICKET_CREATED'
            ).limit(1).count()
            if exists:
                return True
        return False


class Notification(db.Model):
    """
    In-App Notification model for tracking user alerts (Mentions, Assignments).
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=False)
    user = db.relationship('Worker', backref=db.backref('notifications', lazy='dynamic', cascade='all, delete-orphan'))
    
    message = db.Column(db.String(255), nullable=False)
    link = db.Column(db.String(255), nullable=True) # E.g., '/ticket/123'
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: get_utc_now())

    def __repr__(self):
        return f'<Notification for Worker {self.user_id}: {self.message[:20]}>'


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
def queue_file_deletion(mapper, connection, target):
    """Queue the physical file for deletion after a successful commit."""
    if target.path:
        # PYLINT: Using the session as a place to store pending deletions
        from sqlalchemy.orm import object_session
        session = object_session(target)
        if session:
            if 'pending_deletions' not in session.info:
                session.info['pending_deletions'] = set()
            
            safe_filename = os.path.basename(target.path)
            if safe_filename and safe_filename not in ['.', '..']:
                data_dir = Config.get_data_dir()
                filepath = os.path.join(data_dir, 'attachments', safe_filename)
                session.info['pending_deletions'].add(filepath)

@event.listens_for(db.session, 'after_commit')
def process_file_deletions(session):
    """Physically delete files queued during the session."""
    pending = session.info.get('pending_deletions', [])
    for filepath in pending:
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                logging.getLogger(__name__).info("Deleted attachment file after commit: %s", filepath)
        except Exception as e:
            logging.getLogger(__name__).error("Failed to delete attachment %s: %s", filepath, e)
    session.info.pop('pending_deletions', None)

@event.listens_for(db.session, 'after_rollback')
def clear_pending_deletions(session):
    """Clear the deletion queue if the transaction is rolled back."""
    session.info.pop('pending_deletions', None)

