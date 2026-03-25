from utils import get_utc_now
import binascii
import base64
import os
import uuid
from datetime import datetime, timezone
from flask import current_app
from extensions import db
from models import Ticket, Comment, Worker, Tag, Attachment
from sqlalchemy.exc import SQLAlchemyError
from enums import TicketStatus, TicketPriority
from .email_service import EmailService

class TicketService:
    """
    Service for handling ticket and comment operations.
    """

    @staticmethod
    def _urgency_score(ticket, now=None):
        """
        Kombinierter Dringlichkeitswert. Kleinerer Score = dringender.
        
        Logik:
        - Überfällig: 0-99 (Prio 1 überfällig = 0, Prio 3 überfällig = 20)
        - Heute fällig: 100-199
        - Diese Woche (2-7 Tage): 200-299
        - Später (> 7 Tage): 300-499
        - Kein Datum: Fallback auf 500 + Prio * 100
        """
        if now is None:
            now = get_utc_now()
        
        prio = ticket.priority  # 1=Hoch, 2=Mittel, 3=Niedrig
        
        if ticket.due_date is None:
            return 500 + prio * 100
        
        # Deadlines immer als naive Datetimes für SQLite Vergleich
        _due = ticket.due_date
        if _due.tzinfo is not None:
            _due = _due.astimezone(timezone.utc).replace(tzinfo=None)

        days_left = (_due.date() - now.date()).days
        
        if days_left < 0:      # Überfällig
            return 0 + prio * 5 + max(-50, days_left)  # Negativere days_left = dringender
        elif days_left == 0:   # Heute
            return 100 + prio * 10
        elif days_left <= 7:   # Diese Woche
            return 200 + days_left * 10 + prio * 2
        else:                  # Später
            return 300 + min(150, days_left) + prio * 10

    @staticmethod
    def create_ticket(title, description=None, priority=TicketPriority.MITTEL, author_name="System", author_id=None, assigned_to_id=None, assigned_team_id=None, due_date=None, tags=None, attachments=None, order_reference=None, reminder_date=None, is_confidential=False, recurrence_rule=None):
        """Create a new ticket and an initial comment."""
        try:
            ticket = Ticket(
                title=title,
                description=description,
                priority=int(priority.value if hasattr(priority, 'value') else priority),
                status=TicketStatus.OFFEN.value,
                assigned_to_id=assigned_to_id,
                assigned_team_id=assigned_team_id,
                is_confidential=is_confidential,
                recurrence_rule=recurrence_rule,
                due_date=due_date,
                order_reference=order_reference,
                reminder_date=reminder_date
            )
            
            if tags:
                # Assuming tags is a list of Tag objects or names
                for tag_name in tags:
                    tag = Tag.query.filter_by(name=tag_name).first()
                    if not tag:
                        tag = Tag(name=tag_name)
                        db.session.add(tag)
                    ticket.tags.append(tag)

            db.session.add(ticket)
            db.session.flush()  # Get ticket ID

            # Add initial comment if description exists
            comment_text = f"Ticket erstellt von {author_name}. Beschreibung: {description}" if description else f"Ticket erstellt von {author_name}."
            
            comment = Comment(
                ticket_id=ticket.id,
                author=author_name,
                author_id=author_id,
                text=comment_text,
                is_system_event=True,
                event_type='TICKET_CREATED'
            )
            db.session.add(comment)

            # Handle Multi-File Attachments
            if attachments:
                from extensions import Config
                data_dir = current_app.config.get('DATA_DIR', Config.get_data_dir())
                attachments_dir = os.path.join(data_dir, 'attachments')
                os.makedirs(attachments_dir, exist_ok=True)
                for file in attachments:
                    if file.filename == '':
                        continue
                    try:
                        mime_type = file.mimetype or 'application/octet-stream'
                        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'bin'
                        new_filename = f"ticket_{ticket.id}_{uuid.uuid4().hex[:8]}.{ext}"
                        filepath = os.path.join(attachments_dir, new_filename)
                        
                        file.save(filepath)
                        attachment = Attachment(
                            ticket_id=ticket.id,
                            path=new_filename,
                            filename=file.filename,
                            mime_type=mime_type
                        )
                        db.session.add(attachment)
                        current_app.logger.info("Saved attachment %s for ticket %s", new_filename, ticket.id)
                    except Exception as err:
                        current_app.logger.error("Error saving attachment %s: %s", file.filename, err)

            db.session.commit()
            return ticket
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error("Database error creating ticket: %s", e)
            raise
        except Exception as e:
            db.session.rollback()
            current_app.logger.error("Unexpected error creating ticket: %s", e)
            raise

    @staticmethod
    def update_ticket(ticket_id, title=None, description=None, priority=None, due_date=None, author_name="System", author_id=None):
        """Update ticket basic details."""
        try:
            ticket = db.session.get(Ticket, ticket_id)
            if not ticket or ticket.is_deleted:
                return None
            
            changes = []
            if title and ticket.title != title:
                changes.append(f"Titel: {ticket.title} -> {title}")
                ticket.title = title
            if description and ticket.description != description:
                changes.append("Beschreibung aktualisiert")
                ticket.description = description
            if priority and ticket.priority != int(priority):
                changes.append(f"Priorität: {ticket.priority} -> {priority}")
                ticket.priority = int(priority)
            if due_date is not None and ticket.due_date != due_date:
                old_date = ticket.due_date.strftime('%d.%m.%Y') if ticket.due_date else "Keines"
                new_date = due_date.strftime('%d.%m.%Y') if due_date else "Keines"
                changes.append(f"Fälligkeit: {old_date} -> {new_date}")
                ticket.due_date = due_date

            if changes:
                ticket.updated_at = get_utc_now()
                comment = Comment(
                    ticket_id=ticket.id,
                    author=author_name,
                    author_id=author_id,
                    text=f"Ticket aktualisiert: {', '.join(changes)}",
                    is_system_event=True,
                    event_type='TICKET_UPDATE'
                )
                db.session.add(comment)
                db.session.commit()
            
            return ticket
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error("Database error updating ticket: %s", e)
            raise
        except Exception as e:
            db.session.rollback()
            current_app.logger.error("Unexpected error updating ticket: %s", e)
            raise

    @staticmethod
    def delete_ticket(ticket_id, author_name="System", author_id=None):
        """Soft-delete a ticket."""
        try:
            ticket = db.session.get(Ticket, ticket_id)
            if not ticket or ticket.is_deleted:
                return False
            
            ticket.is_deleted = True
            ticket.updated_at = get_utc_now()
            
            comment = Comment(
                ticket_id=ticket.id,
                author=author_name,
                author_id=author_id,
                text="Ticket wurde vom System archiviert.",
                is_system_event=True,
                event_type='TICKET_DELETED'
            )
            db.session.add(comment)
            db.session.commit()
            return True
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error("Database error deleting ticket: %s", e)
            raise
        except Exception as e:
            db.session.rollback()
            current_app.logger.error("Unexpected error deleting ticket: %s", e)
            raise

    @staticmethod
    def add_comment(ticket_id, author_name, author_id, text):
        """Add a comment to an existing ticket."""
        try:
            comment = Comment(
                ticket_id=ticket_id,
                author=author_name,
                author_id=author_id,
                text=text,
                is_system_event=False
            )
            db.session.add(comment)
            
            # Update updated_at on ticket
            ticket = db.session.get(Ticket, ticket_id)
            if ticket:
                ticket.updated_at = get_utc_now()
            
            db.session.commit()
            return comment
        except Exception as e:
            db.session.rollback()
            current_app.logger.error("Error adding comment: %s", e)
            raise

    @staticmethod
    def update_status(ticket_id, status, author_name="System", author_id=None):
        """Update ticket status and add a system comment."""
        try:
            ticket = db.session.get(Ticket, ticket_id)
            if not ticket or ticket.is_deleted:
                return None
            
            old_status = ticket.status
            new_status = status.value if hasattr(status, 'value') else status
            
            if old_status != new_status:
                ticket.status = new_status
                ticket.updated_at = get_utc_now()
                
                comment = Comment(
                    ticket_id=ticket_id,
                    author=author_name,
                    author_id=author_id,
                    text=f"Status geändert: {old_status} -> {new_status}",
                    is_system_event=True,
                    event_type='STATUS_CHANGE'
                )
                db.session.add(comment)
                db.session.commit()
            
            return ticket
        except Exception as e:
            db.session.rollback()
            current_app.logger.error("Error updating status: %s", e)
            raise

    @staticmethod
    def get_dashboard_tickets(worker_id=None, search=None, status_filter=None, page=1, per_page=10, 
                             assigned_to_me=False, unassigned_only=False, 
                             start_date=None, end_date=None, author_name=None, worker_role=None):
        """Fetch tickets for the dashboard with search, filtering, and pagination."""
        from sqlalchemy.orm import joinedload, selectinload
        from models import ChecklistItem
        query = Ticket.query.filter_by(is_deleted=False).options(
            joinedload(Ticket.comments),
            joinedload(Ticket.assigned_to),
            selectinload(Ticket.tags),
            selectinload(Ticket.checklists)
        )
        
        if worker_role not in ['admin', 'management'] and worker_id is not None:
            author_subquery = db.session.query(Comment.ticket_id).filter(
                Comment.event_type == 'TICKET_CREATED',
                Comment.author_id == worker_id
            ).subquery()
            query = query.filter(
                db.or_(
                    Ticket.is_confidential == False,
                    Ticket.id.in_(author_subquery),
                    Ticket.assigned_to_id == worker_id,
                    Ticket.checklists.any(ChecklistItem.assigned_to_id == worker_id)
                )
            )

        if assigned_to_me and worker_id:
            query = query.filter(
                db.or_(
                    Ticket.assigned_to_id == worker_id,
                    Ticket.checklists.any(
                        db.and_(
                            ChecklistItem.assigned_to_id == worker_id,
                            ChecklistItem.is_completed == False
                        )
                    )
                )
            )
        elif unassigned_only:
            query = query.filter(Ticket.assigned_to_id == None)

        if start_date:
            query = query.filter(Ticket.created_at >= start_date)
        if end_date:
            query = query.filter(Ticket.created_at <= end_date)
            
        if author_name:
            # Subquery to find tickets created by a specific author
            author_subquery = db.session.query(Comment.ticket_id).filter(
                Comment.event_type == 'TICKET_CREATED',
                Comment.author.ilike(f"%{author_name}%")
            ).subquery()
            query = query.filter(Ticket.id.in_(author_subquery))

        if search:
            query = query.filter(
                (Ticket.title.ilike(f"%{search}%")) | 
                (Ticket.description.ilike(f"%{search}%")) |
                (Ticket.order_reference.ilike(f"%{search}%"))
            )
        
        if status_filter:
            query = query.filter(Ticket.status == status_filter)
        elif not search and not assigned_to_me:
            # Default: hide closed tickets unless searching or specifically looking at "My Tickets"
            query = query.filter(Ticket.status != TicketStatus.ERLEDIGT.value)

        # Focus / General list (Paginated)
        focus_pagination = query.order_by(
            Ticket.priority.asc(), 
            Ticket.created_at.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)

        # Self: Always keep an eye on "My Tickets" (limit to top 5 for sidebar)
        self_tickets = []
        self_total = 0
        if worker_id:
            self_query = Ticket.query.filter_by(
                is_deleted=False
            ).options(
                joinedload(Ticket.comments),
                joinedload(Ticket.assigned_to),
                selectinload(Ticket.tags),
                selectinload(Ticket.checklists)
            ).filter(
                Ticket.status != TicketStatus.ERLEDIGT.value
            ).filter(
                db.or_(
                    Ticket.assigned_to_id == worker_id,
                    Ticket.checklists.any(
                        db.and_(
                            ChecklistItem.assigned_to_id == worker_id,
                            ChecklistItem.is_completed == False
                        )
                    )
                )
            )
            if worker_role not in ['admin', 'management']:
                author_subs = db.session.query(Comment.ticket_id).filter(
                    Comment.event_type == 'TICKET_CREATED',
                    Comment.author_id == worker_id
                ).subquery()
                self_query = self_query.filter(
                    db.or_(
                        Ticket.is_confidential == False,
                        Ticket.id.in_(author_subs),
                        Ticket.assigned_to_id == worker_id,
                        Ticket.checklists.any(ChecklistItem.assigned_to_id == worker_id)
                    )
                )
            self_total = self_query.count()
            self_tickets = self_query.order_by(Ticket.updated_at.desc()).limit(5).all()

        from sqlalchemy import func
        counts = db.session.query(
            Ticket.status, func.count(Ticket.id)
        ).filter_by(is_deleted=False).filter(
            Ticket.status.in_([TicketStatus.OFFEN.value, TicketStatus.IN_BEARBEITUNG.value, TicketStatus.WARTET.value])
        ).group_by(Ticket.status).all()
        
        summary_counts = {s: 0 for s in ['offen', 'in_bearbeitung', 'wartet']}
        for status, count in counts:
            summary_counts[status] = count

        return {
            'focus_pagination': focus_pagination,
            'self': self_tickets,
            'self_total': self_total,
            'summary_counts': summary_counts
        }

    @staticmethod
    def assign_ticket(ticket_id, worker_id, author_name, author_id=None):
        """Assign a ticket to a worker and log the change."""
        try:
            ticket = db.session.get(Ticket, ticket_id)
            if not ticket or ticket.is_deleted:
                raise ValueError("Ticket nicht gefunden.")
            
            old_worker_name = ticket.assigned_to.name if ticket.assigned_to else "Niemand"
            
            if worker_id:
                worker = db.session.get(Worker, worker_id)
                if not worker:
                    raise ValueError("Mitarbeiter nicht gefunden.")
                new_worker_name = worker.name
            else:
                new_worker_name = "Niemand"

            if ticket.assigned_to_id == worker_id:
                return ticket
                
            ticket.assigned_to_id = worker_id
            ticket.updated_at = get_utc_now()
            
            # Log to history
            comment_text = f"Zuständigkeit geändert: {old_worker_name} -> {new_worker_name}."
            if author_name == new_worker_name:
                comment_text = f"Mitarbeiter {new_worker_name} hat sich das Ticket selbst zugewiesen."
            
            comment = Comment(
                ticket_id=ticket.id,
                author=author_name,
                author_id=author_id,
                text=comment_text,
                is_system_event=True,
                event_type='ASSIGNMENT'
            )
            db.session.add(comment)

            # Task 2.3: Email notification for high-priority tickets
            if ticket.priority == 1 and worker_id:
                EmailService.send_notification(new_worker_name, ticket.id, ticket.priority)
            
            db.session.commit()
            return ticket
        except Exception as e:
            db.session.rollback()
            current_app.logger.error("Error assigning ticket: %s", e)
            raise

    @staticmethod
    def update_ticket_meta(ticket_id, title, priority, author_name, author_id, due_date=None, order_reference=None, reminder_date=None, tags=None):
        """Update ticket title, priority and tags with system event log."""
        try:
            ticket = db.session.get(Ticket, ticket_id)
            if not ticket:
                raise ValueError("Ticket nicht gefunden")

            old_title = ticket.title
            old_prio = ticket.priority
            old_due = ticket.due_date
            old_order_ref = ticket.order_reference
            old_reminder = ticket.reminder_date
            old_tags = [t.name for t in ticket.tags]
            
            # Update fields
            ticket.title = title
            if priority is not None:
                ticket.priority = int(priority)
            ticket.due_date = due_date
            ticket.order_reference = order_reference
            ticket.reminder_date = reminder_date
            ticket.updated_at = get_utc_now()
            
            # Log changes
            changes = []
            if old_title != title:
                changes.append(f"Titel: '{old_title}' -> '{title}'")
            if priority is not None and int(old_prio) != int(priority):
                changes.append(f"Priorität: {old_prio} -> {priority}")
            
            if old_due != due_date:
                fmt = lambda d: d.strftime('%d.%m.%Y') if d else 'Keines'
                changes.append(f"Fälligkeit: {fmt(old_due)} -> {fmt(due_date)}")
            
            if old_order_ref != order_reference:
                changes.append(f"Auftragsreferenz: '{old_order_ref or 'Keine'}' -> '{order_reference or 'Keine'}'")
            
            if old_reminder != reminder_date:
                fmt = lambda d: d.strftime('%d.%m.%Y') if d else 'Keine'
                changes.append(f"Wiedervorlage: {fmt(old_reminder)} -> {fmt(reminder_date)}")
                
            if tags is not None:
                new_tags = [t.strip() for t in tags if t.strip()]
                if set(old_tags) != set(new_tags):
                    changes.append(f"Tags: {', '.join(old_tags) or 'Keine'} -> {', '.join(new_tags) or 'Keine'}")
                    # Clear and rebuild tags
                    ticket.tags = []
                    for tag_name in new_tags:
                        tag = Tag.query.filter_by(name=tag_name).first()
                        if not tag:
                            tag = Tag(name=tag_name)
                            db.session.add(tag)
                        ticket.tags.append(tag)

            if changes:
                comment = Comment(
                    ticket_id=ticket.id,
                    author=author_name,
                    author_id=author_id,
                    text="Metadaten geändert: " + ", ".join(changes),
                    is_system_event=True,
                    event_type='META_UPDATE'
                )
                db.session.add(comment)
                db.session.commit()
            
            return ticket
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error("Database error updating ticket meta: %s", e)
            raise
        except Exception as e:
            db.session.rollback()
            current_app.logger.error("Unexpected error updating ticket meta: %s", e)
            raise

    @staticmethod
    def approve_ticket(ticket_id, worker_id, worker_name):
        try:
            ticket = db.session.get(Ticket, ticket_id)
            if not ticket or ticket.is_deleted:
                raise ValueError("Ticket nicht gefunden.")
            
            if ticket.approved_by_id:
                return ticket  # already approved
                
            ticket.approved_by_id = worker_id
            ticket.approved_at = get_utc_now()
            
            comment = Comment(
                ticket_id=ticket.id,
                author="System",
                author_id=None,
                text=f"Kaufmännisch freigegeben durch {worker_name}",
                is_system_event=True,
                event_type='APPROVAL'
            )
            db.session.add(comment)
            db.session.commit()
            return ticket
        except Exception as e:
            db.session.rollback()
            current_app.logger.error("Error approving ticket: %s", e)
            raise

    @staticmethod
    def add_checklist_item(ticket_id, title, assigned_to_id=None):
        try:
            from models import ChecklistItem
            item = ChecklistItem(ticket_id=ticket_id, title=title, assigned_to_id=assigned_to_id)
            db.session.add(item)
            db.session.commit()
            return item
        except Exception as e:
            db.session.rollback()
            current_app.logger.error("Error adding checklist item: %s", e)
            raise

    @staticmethod
    def toggle_checklist_item(item_id, worker_name="System", worker_id=None):
        try:
            from models import ChecklistItem, Comment
            from enums import TicketStatus
            item = db.session.get(ChecklistItem, item_id)
            if item:
                item.is_completed = not item.is_completed
                ticket = item.ticket
                db.session.commit()
                
                if item.is_completed and ticket.status != TicketStatus.ERLEDIGT.value:
                    if len(ticket.checklists) > 0 and all(c.is_completed for c in ticket.checklists):
                        ticket.status = TicketStatus.ERLEDIGT.value
                        comment = Comment(
                            ticket_id=ticket.id,
                            author=worker_name,
                            author_id=worker_id,
                            text="Status automatisch auf ERLEDIGT gesetzt (alle Unteraufgaben beendet).",
                            is_system_event=True,
                            event_type='STATUS_CHANGE'
                        )
                        db.session.add(comment)
                        db.session.commit()
            return item
        except Exception as e:
            db.session.rollback()
            raise

    @staticmethod
    def delete_checklist_item(item_id):
        try:
            from models import ChecklistItem
            item = db.session.get(ChecklistItem, item_id)
            if item:
                db.session.delete(item)
                db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            raise
