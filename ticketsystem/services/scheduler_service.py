from utils import get_utc_now
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from extensions import db
from models import Ticket
from services.ticket_service import TicketService
import logging

_logger = logging.getLogger(__name__)

# FIX-08: Module-level constant lookup replaces inline closure redefined per iteration
_RECURRENCE_INCREMENTS = {
    'monthly': relativedelta(months=1),
    'quarterly': relativedelta(months=3),
    'yearly': relativedelta(years=1),
}


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
                
                # Calculate next date using module-level lookup
                rule = ticket.recurrence_rule.lower()
                increment = _RECURRENCE_INCREMENTS.get(rule)
                if increment is None:
                    _logger.warning("Unknown recurrence_rule '%s' for ticket %d — defaulting to monthly", rule, ticket.id)
                    increment = relativedelta(months=1)

                next_date = ticket.next_recurrence_date
                while next_date <= now:
                    next_date += increment
                    
                ticket.next_recurrence_date = next_date
                count += 1
            
            if count > 0:
                db.session.commit()
                # FIX-11: Use %s format instead of f-strings
                _logger.info("Processed %d recurring tickets.", count)
                
        except Exception as e:
            db.session.rollback()
            _logger.error("Error processing recurring tickets: %s", e)


def schedule_recurring_job(app):
    """Register the job with apscheduler."""
    try:
        from extensions import scheduler
        # FIX-08: replace_existing=True prevents ConflictingIdError on app restart
        scheduler.add_job(
            id='process_recurring_tickets_job',
            func=lambda: process_recurring_tickets(app),
            trigger='cron',
            hour=2,
            minute=0,
            replace_existing=True
        )
        _logger.info("Scheduled job: process_recurring_tickets at 02:00")
    except Exception as e:
        # FIX-11: Use %s format
        _logger.error("Failed to schedule recurring tickets job: %s", e)
