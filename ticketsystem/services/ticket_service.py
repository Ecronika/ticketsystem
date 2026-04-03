"""
Service Layer for Ticket Management.
"""
import base64
import binascii
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from utils import get_utc_now
from models import Ticket, Comment, Attachment, Tag, Worker
from enums import TicketStatus, TicketPriority, WorkerRole, EventType, ApprovalStatus
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
            return max(0, 50 + days_left) + prio * 5
        elif days_left == 0:   # Heute
            return 150 + prio * 5
        elif days_left <= 7:   # Diese Woche
            return 200 + days_left * 10 + prio * 5
        else:                  # Später
            # Use higher multiplier for priority to keep it significant
            return 300 + min(100, days_left) + prio * 20

    @staticmethod
    def create_ticket(title, description=None, priority=TicketPriority.MITTEL, author_name="System", author_id=None, assigned_to_id=None, assigned_team_id=None, due_date=None, tags=None, attachments=None, order_reference=None, reminder_date=None, is_confidential=False, recurrence_rule=None, checklist_template_id=None, contact_name=None, contact_phone=None, contact_channel=None, callback_requested=False, callback_due=None, commit=True):
        """Create a new ticket and an initial comment.

        Args:
            commit: If True (default), commits the transaction immediately.
                    Pass False in batch/scheduler contexts to keep the
                    transaction open and commit once for the entire batch.
        """
        try:
            path_logs = []
            if assigned_to_id:
                assigned_to_id, path_logs = TicketService._resolve_delegation(assigned_to_id)
                
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
                reminder_date=reminder_date,
                contact_name=contact_name,
                contact_phone=contact_phone,
                contact_channel=contact_channel,
                callback_requested=bool(callback_requested),
                callback_due=callback_due,
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

            if checklist_template_id:
                TicketService.apply_checklist_template(ticket.id, checklist_template_id, commit=False)

            # Add initial comment if description exists
            comment_text = f"Ticket erstellt von {author_name}. Beschreibung: {description}" if description else f"Ticket erstellt von {author_name}."
            if path_logs:
                comment_text += "\nDelegation:\n- " + "\n- ".join(path_logs)
            
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
            # FILE-1: Track saved paths in session.info for the global rollback listener (extensions.py)
            if 'pending_files' not in db.session.info:
                db.session.info['pending_files'] = []

            if attachments:
                from extensions import Config
                data_dir = current_app.config.get('DATA_DIR', Config.get_data_dir())
                attachments_dir = os.path.join(data_dir, 'attachments')
                os.makedirs(attachments_dir, exist_ok=True)
                ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt'}
                for file in attachments:
                    if file.filename == '':
                        continue
                    
                    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
                    if ext not in ALLOWED_EXTENSIONS:
                        current_app.logger.warning("Upload blocked: Illegal extension '%s' for file %s", ext, file.filename)
                        continue

                    try:
                        mime_type = file.mimetype or 'application/octet-stream'
                        new_filename = f"ticket_{ticket.id}_{uuid.uuid4().hex[:8]}.{ext}"
                        filepath = os.path.join(attachments_dir, new_filename)
                        file.save(filepath)
                        db.session.info['pending_files'].append(filepath)
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

            # TX-1: Commit if requested, else flush to get ID
            if commit:
                db.session.commit()
            else:
                db.session.flush()

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
    def create_notification(user_id, message, link=None):
        """Helper to create an in-app notification."""
        from models import Notification
        try:
            notif = Notification(user_id=user_id, message=message, link=link)
            db.session.add(notif)
        except Exception as e:
            current_app.logger.error("Failed to create notification: %s", e)

    @staticmethod
    def add_comment(ticket_id, author_name, author_id, text):
        """Add a comment to an existing ticket."""
        import re
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
                
            # Trigger Mention Notifications
            mentions = set(re.findall(r'@(\w+)', text))
            if mentions:
                for mention in mentions:
                    if mention.lower() == author_name.lower():
                        continue
                    mentioned_worker = Worker.query.filter(Worker.name.ilike(mention)).first()
                    if mentioned_worker:
                        TicketService.create_notification(
                            user_id=mentioned_worker.id,
                            message=f"{author_name} hat Sie in Ticket #{ticket_id} erwähnt.",
                            link=f"/ticket/{ticket_id}"
                        )
            
            db.session.commit()
            return comment
        except Exception as e:
            db.session.rollback()
            current_app.logger.error("Error adding comment: %s", e)
            raise

    @staticmethod
    def update_status(ticket_id, status, author_name="System", author_id=None, commit=True):
        """Update ticket status and add a system comment.

        Args:
            commit: If True (default), commits immediately. Pass False in
                    batch contexts to defer the commit to the caller.
        """
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
                # TX-1: Honour commit flag for batch-safe operation
                if commit:
                    db.session.commit()
                else:
                    db.session.flush()
            
            return ticket
        except Exception as e:
            db.session.rollback()
            current_app.logger.error("Error updating status: %s", e)
            raise

    @staticmethod
    def get_dashboard_tickets(worker_id=None, search=None, status_filter=None, page=1, per_page=10,
                             assigned_to_me=False, unassigned_only=False, callback_pending=False,
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
        
        if worker_role not in [WorkerRole.ADMIN.value, WorkerRole.HR.value, WorkerRole.MANAGEMENT.value] and worker_id is not None:
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

        if callback_pending:
            query = query.filter(
                Ticket.callback_requested == True,
                Ticket.status != TicketStatus.ERLEDIGT.value
            )

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
            if worker_role not in [WorkerRole.ADMIN.value, WorkerRole.HR.value, WorkerRole.MANAGEMENT.value]:
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
        from models import ChecklistItem as _CI
        counts_query = db.session.query(
            Ticket.status, func.count(Ticket.id)
        ).filter_by(is_deleted=False).filter(
            Ticket.status.in_([TicketStatus.OFFEN.value, TicketStatus.IN_BEARBEITUNG.value, TicketStatus.WARTET.value])
        )
        # Apply the same confidential filter so counts match visible tickets
        if worker_role not in [WorkerRole.ADMIN.value, WorkerRole.HR.value, WorkerRole.MANAGEMENT.value] and worker_id is not None:
            _author_sub = db.session.query(Comment.ticket_id).filter(
                Comment.event_type == 'TICKET_CREATED',
                Comment.author_id == worker_id
            ).subquery()
            counts_query = counts_query.filter(
                db.or_(
                    Ticket.is_confidential == False,
                    Ticket.id.in_(_author_sub),
                    Ticket.assigned_to_id == worker_id,
                    Ticket.checklists.any(_CI.assigned_to_id == worker_id)
                )
            )
        counts = counts_query.group_by(Ticket.status).all()
        
        summary_counts = {s.value: 0 for s in [TicketStatus.OFFEN, TicketStatus.IN_BEARBEITUNG, TicketStatus.WARTET]}
        for status, count in counts:
            summary_counts[status] = count

        return {
            'focus_pagination': focus_pagination,
            'self': self_tickets,
            'self_total': self_total,
            'summary_counts': summary_counts
        }

    @staticmethod
    def get_pending_approvals(page=1, per_page=15):
        """Fetch all tickets that are currently pending GF/admin approval."""
        from sqlalchemy.orm import joinedload, selectinload
        query = Ticket.query.filter_by(
            is_deleted=False, 
            approval_status='pending'
        ).options(
            joinedload(Ticket.assigned_to),
            selectinload(Ticket.tags)
        ).order_by(Ticket.updated_at.desc())
        
        return query.paginate(page=page, per_page=per_page, error_out=False)

    @staticmethod
    def get_projects_summary():
        """Fetch all projects (grouped by order_reference) and calculate progress."""
        from sqlalchemy.orm import selectinload
        from models import Ticket
        from enums import TicketStatus
        
        query = Ticket.query.filter(
            Ticket.is_deleted == False,
            Ticket.order_reference != None,
            Ticket.order_reference != ''
        ).options(selectinload(Ticket.checklists))
        
        tickets = query.all()
        projects = {}
        
        for t in tickets:
            ref = t.order_reference.strip()
            if not ref:
                continue
                
            if ref not in projects:
                projects[ref] = {
                    'order_reference': ref,
                    'total_tickets': 0,
                    'completed_tickets': 0,
                    'last_updated': t.updated_at or t.created_at,
                    'ticket_progress_sum': 0.0,
                    'status_counts': {s.value: 0 for s in TicketStatus}
                }
            
            p = projects[ref]
            p['total_tickets'] += 1
            
            t_time = t.updated_at or t.created_at
            if t_time and (not p['last_updated'] or t_time > p['last_updated']):
                p['last_updated'] = t_time
                
            if t.status in p['status_counts']:
                p['status_counts'][t.status] += 1
            else:
                p['status_counts'][t.status] = 1
                
            is_ticket_erledigt = (t.status == TicketStatus.ERLEDIGT.value)
            if is_ticket_erledigt:
                p['completed_tickets'] += 1
                
            # Ticket Progress Calculation
            if t.checklists:
                completed_cl = sum(1 for c in t.checklists if c.is_completed)
                total_cl = len(t.checklists)
                t_prog = completed_cl / total_cl if total_cl > 0 else 0.0
            else:
                t_prog = 1.0 if is_ticket_erledigt else 0.0
                
            p['ticket_progress_sum'] += t_prog

        project_list = []
        for ref, p in projects.items():
            if p['total_tickets'] > 0:
                p['progress'] = int((p['ticket_progress_sum'] / p['total_tickets']) * 100)
            else:
                p['progress'] = 0
            
            p['is_completed'] = (p['progress'] == 100)
            project_list.append(p)
            
        # Sort: Active projects first, then by last_updated descending
        project_list.sort(key=lambda x: (x['is_completed'], -x['last_updated'].timestamp() if x['last_updated'] else 0))
        return project_list

    @staticmethod
    def _resolve_delegation(worker_id):
        """Resolves the final worker ID, gracefully handling OOO and loops."""
        if not worker_id:
            return None, []
        
        visited = set()
        path_logs = []
        current_id = worker_id
        
        while current_id:
            if current_id in visited:
                path_logs.append("Zirkuläre Vertretung erkannt. Fallback: Unzugewiesen.")
                return None, path_logs
                
            visited.add(current_id)
            w = db.session.get(Worker, current_id)
            
            if not w:
                return None, path_logs
                
            if w.is_out_of_office:
                if w.delegate_to_id:
                    delegate = db.session.get(Worker, w.delegate_to_id)
                    delegate_name = delegate.name if delegate else "Unbekannt"
                    path_logs.append(f"{w.name} abwesend -> delegiert an {delegate_name}")
                    current_id = w.delegate_to_id
                else:
                    path_logs.append(f"{w.name} abwesend (kein Vertreter). Fallback: Unzugewiesen.")
                    return None, path_logs
            else:
                return current_id, path_logs
                
        return None, path_logs

    @staticmethod
    def assign_ticket(ticket_id, worker_id, author_name, author_id=None, team_id=None):
        """Assign a ticket to a worker and log the change."""
        try:
            ticket = db.session.get(Ticket, ticket_id)
            if not ticket or ticket.is_deleted:
                raise ValueError("Ticket nicht gefunden.")
            
            old_worker_name = ticket.assigned_to.name if ticket.assigned_to else "Niemand"
            
            path_logs = []
            if worker_id:
                worker_id, path_logs = TicketService._resolve_delegation(worker_id)
                
            if worker_id:
                worker = db.session.get(Worker, worker_id)
                if not worker:
                    raise ValueError("Mitarbeiter nicht gefunden.")
                new_worker_name = worker.name
            else:
                new_worker_name = "Niemand"

            if ticket.assigned_to_id == worker_id and ticket.assigned_team_id == team_id and not path_logs:
                return ticket

            ticket.assigned_to_id = worker_id
            ticket.assigned_team_id = team_id
            ticket.updated_at = get_utc_now()
            
            # Trigger Assignment Notification
            if worker_id and worker_id != author_id:
                TicketService.create_notification(
                    user_id=worker_id,
                    message=f"Ihnen wurde Ticket #{ticket_id} zugewiesen.",
                    link=f"/ticket/{ticket_id}"
                )
            
            # Log to history
            comment_text = f"Zuständigkeit geändert: {old_worker_name} -> {new_worker_name}."
            if author_name == new_worker_name:
                comment_text = f"Mitarbeiter {new_worker_name} hat sich das Ticket selbst zugewiesen."
                
            if path_logs:
                comment_text += "\nDelegation:\n- " + "\n- ".join(path_logs)
            
            comment = Comment(
                ticket_id=ticket.id,
                author=author_name,
                author_id=author_id,
                text=comment_text,
                is_system_event=True,
                event_type='ASSIGNMENT'
            )
            db.session.add(comment)

            # Email notification for high-priority tickets
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
    def request_approval(ticket_id, worker_id, worker_name):
        try:
            ticket = db.session.get(Ticket, ticket_id)
            if not ticket or ticket.is_deleted:
                raise ValueError("Ticket nicht gefunden.")
                
            if ticket.approval_status == ApprovalStatus.PENDING.value:
                return False, "Freigabe bereits angefragt."
                
            ticket.approval_status = ApprovalStatus.PENDING.value
            ticket.updated_at = get_utc_now()
            
            comment = Comment(
                ticket_id=ticket.id,
                author=worker_name,
                author_id=worker_id,
                text="Freigabe wurde angefordert. Das Ticket ist nun gesperrt.",
                is_system_event=True,
                event_type='APPROVAL_REQUEST'
            )
            db.session.add(comment)
            db.session.commit()
            return True, "Freigabe angefragt."
        except Exception as e:
            db.session.rollback()
            current_app.logger.error("Error requesting approval: %s", e)
            raise

    @staticmethod
    def approve_ticket(ticket_id, worker_id, worker_name):
        try:
            ticket = db.session.get(Ticket, ticket_id)
            if not ticket or ticket.is_deleted:
                raise ValueError("Ticket nicht gefunden.")
            
            if ticket.approval_status == ApprovalStatus.APPROVED.value:
                return False, "Ticket bereits freigegeben."
                
            ticket.approval_status = ApprovalStatus.APPROVED.value
            ticket.approved_by_id = worker_id
            ticket.approved_at = get_utc_now()
            ticket.updated_at = get_utc_now()
            
            comment = Comment(
                ticket_id=ticket.id,
                author="System",
                author_id=None,
                text=f"Freigegeben durch {worker_name}",
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
    def reject_ticket(ticket_id, worker_id, worker_name, reason):
        try:
            ticket = db.session.get(Ticket, ticket_id)
            if not ticket or ticket.is_deleted:
                raise ValueError("Ticket nicht gefunden.")
                
            ticket.approval_status = ApprovalStatus.REJECTED.value
            ticket.rejected_by_id = worker_id
            ticket.reject_reason = reason
            ticket.status = TicketStatus.OFFEN.value
            ticket.updated_at = get_utc_now()
            
            comment = Comment(
                ticket_id=ticket.id,
                author="System",
                author_id=None,
                text=f"Freigabe abgelehnt durch {worker_name}. Grund: {reason}",
                is_system_event=True,
                event_type='APPROVAL_REJECTED'
            )
            db.session.add(comment)
            db.session.commit()
            return ticket
        except Exception as e:
            db.session.rollback()
            current_app.logger.error("Error rejecting ticket: %s", e)
            raise

    @staticmethod
    def add_checklist_item(ticket_id, title, assigned_to_id=None, assigned_team_id=None, due_date=None, depends_on_item_id=None):
        try:
            from models import ChecklistItem
            item = ChecklistItem(
                ticket_id=ticket_id, 
                title=title, 
                assigned_to_id=assigned_to_id,
                assigned_team_id=assigned_team_id,
                due_date=due_date,
                depends_on_item_id=depends_on_item_id
            )
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
                if not item.is_completed and item.depends_on_item_id:
                    parent_item = db.session.get(ChecklistItem, item.depends_on_item_id)
                    if parent_item and not parent_item.is_completed:
                        raise ValueError(f"Abhängigkeit nicht erfüllt: '{parent_item.title}' muss zuerst abgeschlossen werden.")
                        
                item.is_completed = not item.is_completed
                ticket = item.ticket
                
                # FIX: Removed intermediate commit here to keep everything atomic
                
                if item.is_completed and ticket.status != TicketStatus.ERLEDIGT.value:
                    # Check if all items are now finished
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
                
                # Single final commit for everything
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

    @staticmethod
    def apply_checklist_template(ticket_id, template_id, commit=True):
        """Applies a checklist template to a ticket."""
        from models import Ticket, ChecklistTemplate, ChecklistItem
        try:
            ticket = db.session.get(Ticket, ticket_id)
            template = db.session.get(ChecklistTemplate, template_id)
            
            if not ticket or not template:
                raise ValueError("Ticket oder Vorlage nicht gefunden.")
                
            for t_item in template.items:
                new_item = ChecklistItem(
                    ticket_id=ticket.id,
                    title=t_item.title,
                    is_completed=False
                )
                db.session.add(new_item)
            
            # System-Kommentar hinzufügen
            comment = Comment(
                ticket_id=ticket.id,
                author="System",
                text=f"Checklisten-Vorlage '{template.title}' angewendet.",
                is_system_event=True,
                event_type='CHECKLIST_TEMPLATE_APPLIED'
            )
            db.session.add(comment)

            if commit:
                db.session.commit()
            return True
        except Exception as e:
            if commit:
                db.session.rollback()
            current_app.logger.error("Error applying template: %s", e)
            raise

    @staticmethod
    def get_workload_overview():
        """
        Auslastungsübersicht für Admin/Management.

        Gibt eine Liste von Dicts zurück, gruppiert nach:
        1. Abwesende Mitarbeiter mit kritischen Tickets (Handlungsbedarf)
        2. Anwesende Mitarbeiter mit offenen Tickets

        Kritisch = überfällig ODER fällig in laufender Kalenderwoche ODER Priorität Hoch.
        'wartet'-Tickets werden nie als kritisch eingestuft (bewusst geparkt).

        Rückgabeformat pro Eintrag:
        {
            'worker': Worker,
            'open_count': int,
            'critical_count': int,   # nur bei abwesenden Mitarbeitern relevant
            'tickets': [Ticket, ...],          # alle offenen Tickets, sortiert
            'critical_tickets': [Ticket, ...], # nur die kritischen (Subset)
            'other_tickets': [Ticket, ...],    # nicht kritische
        }
        """
        from datetime import date
        now = get_utc_now()
        today = now.date()

        # Montag und Freitag der laufenden Kalenderwoche
        week_start = today - timedelta(days=today.weekday())  # Montag
        week_end = week_start + timedelta(days=4)             # Freitag

        open_statuses = [
            TicketStatus.OFFEN.value,
            TicketStatus.IN_BEARBEITUNG.value,
            TicketStatus.WARTET.value,
        ]

        tickets = (
            Ticket.query
            .filter(
                Ticket.is_deleted == False,
                Ticket.status.in_(open_statuses),
                Ticket.assigned_to_id.isnot(None),
            )
            .all()
        )

        # Gruppierung nach Mitarbeiter-ID
        tickets_by_worker = {}
        for t in tickets:
            tickets_by_worker.setdefault(t.assigned_to_id, []).append(t)

        workers = Worker.query.filter_by(is_active=True).all()

        absent_entries = []
        present_entries = []

        for worker in workers:
            worker_tickets = tickets_by_worker.get(worker.id, [])
            if not worker_tickets:
                continue

            def _is_critical(t):
                """Kritisch wenn: hohe Prio ODER überfällig ODER Fälligkeit in dieser Woche."""
                if t.status == TicketStatus.WARTET.value:
                    return False
                if t.priority == TicketPriority.HOCH.value:
                    return True
                if t.due_date:
                    due = t.due_date.date() if hasattr(t.due_date, 'date') else t.due_date
                    if due <= week_end:   # überfällig oder in laufender KW
                        return True
                return False

            critical = [t for t in worker_tickets if _is_critical(t)]
            other = [t for t in worker_tickets if not _is_critical(t)]

            # Sortierung: überfällig zuerst, dann nach Priorität, dann KW
            def _sort_key(t):
                if t.due_date:
                    due = t.due_date.date() if hasattr(t.due_date, 'date') else t.due_date
                    days_left = (due - today).days
                else:
                    days_left = 999
                return (days_left, t.priority)

            critical.sort(key=_sort_key)
            other.sort(key=_sort_key)
            all_sorted = critical + other

            entry = {
                'worker': worker,
                'open_count': len(worker_tickets),
                'critical_count': len(critical),
                'tickets': all_sorted,
                'critical_tickets': critical,
                'other_tickets': other,
            }

            if worker.is_out_of_office:
                absent_entries.append(entry)
            else:
                present_entries.append(entry)

        # Abwesende: zuerst die mit meisten kritischen Tickets
        absent_entries.sort(key=lambda x: (-x['critical_count'], -x['open_count']))
        # Anwesende: nach Anzahl offener Tickets
        present_entries.sort(key=lambda x: -x['open_count'])

        return absent_entries, present_entries

    @staticmethod
    def reassign_ticket(ticket_id, to_worker_id, author_name, author_id):
        """
        Weist ein einzelnes Ticket einem anderen Mitarbeiter zu.
        Direkter Admin-Eingriff — kein OOO-Delegations-Mechanismus.
        Gibt das aktualisierte Ticket zurück.
        """
        try:
            ticket = db.session.get(Ticket, ticket_id)
            if not ticket or ticket.is_deleted:
                raise ValueError("Ticket nicht gefunden.")

            to_worker = db.session.get(Worker, to_worker_id)
            if not to_worker or not to_worker.is_active:
                raise ValueError("Ziel-Mitarbeiter nicht gefunden oder inaktiv.")

            from_name = ticket.assigned_to.name if ticket.assigned_to else "Nicht zugewiesen"
            ticket.assigned_to_id = to_worker_id
            ticket.updated_at = get_utc_now()

            comment = Comment(
                ticket_id=ticket.id,
                author=author_name,
                author_id=author_id,
                text=f"Umgezuweisen durch {author_name}: {from_name} → {to_worker.name}",
                is_system_event=True,
                event_type='ASSIGNMENT'
            )
            db.session.add(comment)

            # Ziel-Mitarbeiter benachrichtigen
            TicketService.create_notification(
                user_id=to_worker_id,
                message=f"Ticket #{ticket.id} wurde Ihnen zugewiesen (von {from_name}).",
                link=f"/ticket/{ticket.id}"
            )

            db.session.commit()
            return ticket
        except Exception as e:
            db.session.rollback()
            current_app.logger.error("Error reassigning ticket %s: %s", ticket_id, e)
            raise
