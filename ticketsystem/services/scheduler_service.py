"""
Scheduler Service.

Background job definitions for recurring ticket processing and SLA escalation.
"""
from utils import get_utc_now
from datetime import datetime, timezone, timedelta
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
    """Job to process recurring tickets atomically.

    TX-2: All service calls use commit=False so they only flush (getting IDs
    without hard-committing).  A single db.session.commit() at the end of the
    loop makes the entire batch atomic — if any ticket fails, db.session.rollback()
    in the except clause reverts every change from that run.
    """
    with app.app_context():
        now = get_utc_now()

        try:
            tickets = Ticket.query.filter(
                Ticket.is_deleted == False,
                Ticket.recurrence_rule != None,
                Ticket.next_recurrence_date <= now
            ).all()

            count = 0
            for ticket in tickets:
                # TX-2: commit=False keeps everything in one transaction
                new_due_date = None
                if ticket.due_date and ticket.created_at:
                    offset = ticket.due_date - ticket.created_at
                    new_due_date = now + offset
                elif ticket.due_date:
                    offset = ticket.due_date - now
                    new_due_date = now + offset

                new_ticket = TicketService.create_ticket(
                    title=ticket.title,
                    description=ticket.description,
                    priority=ticket.priority,
                    author_name="System",
                    assigned_to_id=ticket.assigned_to_id,
                    assigned_team_id=ticket.assigned_team_id,
                    is_confidential=ticket.is_confidential,
                    due_date=new_due_date,
                    commit=False,
                )

                # Clone checklists from template if one is tied, otherwise fallback
                if ticket.checklist_template_id and ticket.checklist_template:
                    for item in ticket.checklist_template.items:
                        TicketService.add_checklist_item(new_ticket.id, item.title)
                else:
                    for item in ticket.checklists:
                        TicketService.add_checklist_item(new_ticket.id, item.title, item.assigned_to_id)

                # Calculate next recurrence date using module-level lookup
                rule = ticket.recurrence_rule.lower()
                increment = _RECURRENCE_INCREMENTS.get(rule)
                if increment is None:
                    _logger.warning(
                        "Unknown recurrence_rule '%s' for ticket %d — defaulting to monthly",
                        rule, ticket.id
                    )
                    increment = relativedelta(months=1)

                next_date = ticket.next_recurrence_date
                while next_date <= now:
                    next_date += increment

                ticket.next_recurrence_date = next_date
                count += 1

            if count > 0:
                # TX-2: Single atomic commit for the entire batch
                db.session.commit()
                _logger.info("Processed %d recurring tickets.", count)

        except Exception as e:
            db.session.rollback()
            _logger.error("Error processing recurring tickets: %s", e)


def process_sla_escalations(app):
    """Daily SLA check: notify assignees and admins about overdue tickets.

    Grace periods before first escalation:
      Prio 1 (Hoch):   0 days  — escalate as soon as overdue
      Prio 2 (Mittel): 1 day
      Prio 3 (Niedrig):3 days

    Anti-spam: re-escalation only after 23 hours (via Ticket.last_escalated_at).
    """
    with app.app_context():
        from models import Comment, Worker
        from enums import TicketStatus, TicketPriority
        from services.email_service import EmailService

        now = get_utc_now()
        GRACE_DAYS = {1: 0, 2: 1, 3: 3}
        ANTI_SPAM_HOURS = 23

        try:
            open_statuses = [
                TicketStatus.OFFEN.value,
                TicketStatus.IN_BEARBEITUNG.value,
                TicketStatus.WARTET.value,
            ]
            overdue_tickets = Ticket.query.filter(
                Ticket.is_deleted == False,
                Ticket.status.in_(open_statuses),
                Ticket.due_date.isnot(None),
                Ticket.due_date < now,
            ).all()

            escalated = 0
            for ticket in overdue_tickets:
                prio = ticket.priority
                grace = GRACE_DAYS.get(prio, 1)
                days_overdue = (now.date() - ticket.due_date.date()).days
                if days_overdue < grace:
                    continue  # Within grace period

                # Anti-spam: skip if escalated within last 23h
                if ticket.last_escalated_at:
                    hours_since = (now - ticket.last_escalated_at).total_seconds() / 3600
                    if hours_since < ANTI_SPAM_HOURS:
                        continue

                # System comment
                comment = Comment(
                    ticket_id=ticket.id,
                    author="System",
                    text=(f"SLA-Eskalation: Ticket seit {days_overdue} Tag(en) überfällig "
                          f"(Fälligkeit: {ticket.due_date.strftime('%d.%m.%Y')})."),
                    is_system_event=True,
                    event_type='SLA_ESCALATION',
                )
                db.session.add(comment)
                ticket.last_escalated_at = now

                # In-app notification for assignee
                if ticket.assigned_to_id:
                    TicketService.create_notification(
                        user_id=ticket.assigned_to_id,
                        message=(f"SLA-Eskalation: Ticket #{ticket.id} ist seit "
                                 f"{days_overdue} Tag(en) überfällig."),
                        link=f"/ticket/{ticket.id}"
                    )
                    # Email assignee
                    if ticket.assigned_to and ticket.assigned_to.email:
                        EmailService.send_sla_escalation(
                            ticket.assigned_to.name, ticket.id, ticket.title,
                            days_overdue, prio,
                            recipient_email=ticket.assigned_to.email
                        )

                # Prio 1: also notify all active admins
                if prio == TicketPriority.HOCH.value:
                    admins = Worker.query.filter_by(role='admin', is_active=True).all()
                    for admin in admins:
                        if admin.id != ticket.assigned_to_id:
                            TicketService.create_notification(
                                user_id=admin.id,
                                message=(f"SLA-Eskalation (Prio HOCH): Ticket #{ticket.id} "
                                         f"seit {days_overdue} Tag(en) überfällig."),
                                link=f"/ticket/{ticket.id}"
                            )

                escalated += 1

            if escalated > 0:
                db.session.commit()
                _logger.info("SLA escalation: %d ticket(s) escalated.", escalated)

        except Exception as e:
            db.session.rollback()
            _logger.error("Error in SLA escalation job: %s", e)


def schedule_sla_job(app):
    """Register the SLA escalation job with APScheduler (runs daily at 07:00 UTC)."""
    try:
        from extensions import scheduler
        scheduler.add_job(
            id='process_sla_escalations_job',
            func=lambda: process_sla_escalations(app),
            trigger='cron',
            hour=7,
            minute=0,
            replace_existing=True,
        )
        _logger.info("Scheduled job: process_sla_escalations at 07:00")
    except Exception as e:
        _logger.error("Failed to schedule SLA escalation job: %s", e)


def schedule_recurring_job(app):
    """Register the recurring ticket job with APScheduler."""
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
        _logger.error("Failed to schedule recurring tickets job: %s", e)
