from datetime import datetime, timezone
from flask import current_app
from extensions import db
from models import Ticket, Comment, Worker
from enums import TicketStatus, TicketPriority

class TicketService:
    """
    Service for handling ticket and comment operations.
    """

    @staticmethod
    def create_ticket(title, description=None, priority=TicketPriority.MITTEL, author_name="System", assigned_to_id=None):
        """Create a new ticket and an initial comment."""
        try:
            ticket = Ticket(
                title=title,
                description=description,
                priority=int(priority.value if hasattr(priority, 'value') else priority),
                status=TicketStatus.OFFEN.value,
                assigned_to_id=assigned_to_id
            )
            db.session.add(ticket)
            db.session.flush()  # Get ticket ID

            # Add initial comment if description exists
            if description:
                comment = Comment(
                    ticket_id=ticket.id,
                    author=author_name,
                    text=f"Ticket erstellt. Beschreibung: {description}"
                )
                db.session.add(comment)
            else:
                comment = Comment(
                    ticket_id=ticket.id,
                    author=author_name,
                    text="Ticket ohne Beschreibung erstellt."
                )
                db.session.add(comment)

            db.session.commit()
            return ticket
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating ticket: {e}")
            raise

    @staticmethod
    def add_comment(ticket_id, author_name, text):
        """Add a comment to an existing ticket."""
        try:
            comment = Comment(
                ticket_id=ticket_id,
                author=author_name,
                text=text
            )
            db.session.add(comment)
            
            # Update updated_at on ticket
            ticket = db.session.get(Ticket, ticket_id)
            if ticket:
                ticket.updated_at = datetime.now(timezone.utc)
            
            db.session.commit()
            return comment
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error adding comment: {e}")
            raise

    @staticmethod
    def update_status(ticket_id, status, author_name="System"):
        """Update ticket status and add a system comment."""
        try:
            ticket = db.session.get(Ticket, ticket_id)
            if not ticket:
                return None
            
            old_status = ticket.status
            new_status = status.value if hasattr(status, 'value') else status
            
            if old_status != new_status:
                ticket.status = new_status
                ticket.updated_at = datetime.now(timezone.utc)
                
                comment = Comment(
                    ticket_id=ticket_id,
                    author=author_name,
                    text=f"Status geändert: {old_status} -> {new_status}"
                )
                db.session.add(comment)
                db.session.commit()
            
            return ticket
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating status: {e}")
            raise

    @staticmethod
    def get_dashboard_tickets(worker_id=None, search=None, status_filter=None, page=1, per_page=10):
        """Fetch tickets for the dashboard with search, filtering, and pagination."""
        query = Ticket.query

        if search:
            query = query.filter(
                (Ticket.title.ilike(f"%{search}%")) | 
                (Ticket.description.ilike(f"%{search}%"))
            )
        
        if status_filter:
            query = query.filter(Ticket.status == status_filter)
        elif not search:
            # Default: hide closed tickets unless searching
            query = query.filter(Ticket.status != TicketStatus.ERLEDIGT.value)

        # Focus / General list (Paginated)
        focus_pagination = query.order_by(
            Ticket.priority.asc(), 
            Ticket.created_at.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)

        # Self: Always keep an eye on "My Tickets" (limit to top 5 for sidebar)
        self_tickets = []
        if worker_id:
            self_tickets = Ticket.query.filter_by(
                assigned_to_id=worker_id
            ).filter(
                Ticket.status != TicketStatus.ERLEDIGT.value
            ).order_by(Ticket.updated_at.desc()).limit(5).all()

        return {
            'focus_pagination': focus_pagination,
            'self': self_tickets
        }

    @staticmethod
    def assign_ticket(ticket_id, worker_id, author_name):
        """Assign a ticket to a worker and log the change."""
        try:
            ticket = db.session.get(Ticket, ticket_id)
            if not ticket:
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
            ticket.updated_at = datetime.now(timezone.utc)
            
            # Log to history
            comment_text = f"Zuständigkeit geändert: {old_worker_name} -> {new_worker_name}."
            if author_name == new_worker_name:
                comment_text = f"Mitarbeiter {new_worker_name} hat sich das Ticket selbst zugewiesen."
            
            comment = Comment(
                ticket_id=ticket.id,
                author=author_name,
                text=comment_text
            )
            db.session.add(comment)
            db.session.commit()
            return ticket
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error assigning ticket: {e}")
            raise
