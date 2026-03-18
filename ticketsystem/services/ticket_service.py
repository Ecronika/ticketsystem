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
    def get_dashboard_tickets(worker_id=None):
        """Fetch tickets for the dashboard (Focus & Self)."""
        # Focus: Non-completed tickets sorted by priority and date
        focus_tickets = Ticket.query.filter(
            Ticket.status != TicketStatus.ERLEDIGT.value
        ).order_by(Ticket.priority.asc(), Ticket.created_at.desc()).all()

        # Self: Tickets assigned to the specific worker
        self_tickets = []
        if worker_id:
            self_tickets = Ticket.query.filter_by(
                assigned_to_id=worker_id
            ).filter(
                Ticket.status != TicketStatus.ERLEDIGT.value
            ).order_by(Ticket.updated_at.desc()).all()

        return {
            'focus': focus_tickets,
            'self': self_tickets
        }
