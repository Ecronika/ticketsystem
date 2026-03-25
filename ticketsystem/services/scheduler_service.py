from utils import get_utc_now
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from extensions import db
from models import Ticket
from services.ticket_service import TicketService
import logging

def process_recurring_tickets(app):
    """Job to process recurring tickets."""
    with app.app_context():
        now = get_utc_now()
        
        try:
            # Find all active recurring tickets that are due
            tickets = Ticket.query.filter(
                Ticket.is_deleted == False,
                Ticket.recurrence_rule != None,
                Ticket.next_recurrence_date <= now
            ).all()
            
            count = 0
            for ticket in tickets:
                # Clone the ticket
                new_ticket = TicketService.create_ticket(
                    title=ticket.title,
                    description=ticket.description,
                    priority=ticket.priority,
                    author_name="System",
                    assigned_to_id=ticket.assigned_to_id,
                    assigned_team_id=ticket.assigned_team_id,
                    is_confidential=ticket.is_confidential,
                )
                
                # Clone checklists from template if one is tied, otherwise fallback
                if ticket.checklist_template_id and ticket.checklist_template:
                    for item in ticket.checklist_template.items:
                        TicketService.add_checklist_item(new_ticket.id, item.title)
                else:
                    for item in ticket.checklists:
                        TicketService.add_checklist_item(new_ticket.id, item.title, item.assigned_to_id)
                
                # Calculate next date
                rule = ticket.recurrence_rule.lower()
                next_date = ticket.next_recurrence_date
                
                def get_increment():
                    if rule == 'monthly': return relativedelta(months=1)
                    if rule == 'quarterly': return relativedelta(months=3)
                    if rule == 'yearly': return relativedelta(years=1)
                    return relativedelta(months=1)
                
                increment = get_increment()
                while next_date <= now:
                    next_date += increment
                    
                ticket.next_recurrence_date = next_date
                count += 1
            
            if count > 0:
                db.session.commit()
                logging.getLogger(__name__).info(f"Processed {count} recurring tickets.")
                
        except Exception as e:
            db.session.rollback()
            logging.getLogger(__name__).error(f"Error processing recurring tickets: {e}")

def schedule_recurring_job(app):
    """Register the job with apscheduler."""
    try:
        from extensions import scheduler
        scheduler.add_job(
            id='process_recurring_tickets_job',
            func=lambda: process_recurring_tickets(app),
            trigger='cron',
            hour=2,
            minute=0
        )
        logging.getLogger(__name__).info("Scheduled job: process_recurring_tickets at 02:00")
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to schedule recurring tickets job: {e}")
