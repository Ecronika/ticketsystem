"""Scheduler Service.

Background job definitions for recurring ticket processing and SLA
escalation.
"""

import logging
from collections import defaultdict
from typing import Dict, List

from dateutil.relativedelta import relativedelta
from flask import Flask

from enums import TicketPriority, TicketStatus
from extensions import db
from models import Comment, Ticket, TicketRecurrence, Worker
from services.email_service import EmailService
from services._ticket_helpers import _OPEN_STATUSES, _RECURRENCE_INCREMENTS
from services.checklist_service import ChecklistService
from services.ticket_core_service import TicketCoreService
from utils import get_utc_now

_logger = logging.getLogger(__name__)

_GRACE_DAYS: Dict[int, int] = {1: 0, 2: 1, 3: 3}
_ANTI_SPAM_HOURS = 23


# ---------------------------------------------------------------------------
# Recurring tickets
# ---------------------------------------------------------------------------

def process_recurring_tickets(app: Flask) -> None:
    """Process recurring tickets atomically.

    All service calls use ``commit=False`` so a single
    ``db.session.commit()`` at the end makes the entire batch atomic.
    """
    with app.app_context():
        now = get_utc_now()
        try:
            tickets = _fetch_due_recurring_tickets(now)
            count = _create_recurring_copies(tickets, now)
            if count > 0:
                db.session.commit()
                _logger.info("Processed %d recurring tickets.", count)
        except Exception as exc:
            db.session.rollback()
            _logger.error("Error processing recurring tickets: %s", exc)


def _fetch_due_recurring_tickets(now: object) -> List[Ticket]:
    """Return all non-deleted recurring tickets whose next date is due."""
    return Ticket.query.filter(
        Ticket.is_deleted.is_(False),
        Ticket.recurrence.has(TicketRecurrence.next_date <= now),
    ).all()


def _create_recurring_copies(tickets: List[Ticket], now: object) -> int:
    """Clone each due recurring ticket and advance its next-recurrence date."""
    count = 0
    for ticket in tickets:
        new_due_date = _compute_new_due_date(ticket, now)
        new_ticket = TicketCoreService.create_ticket(
            title=ticket.title,
            description=ticket.description,
            priority=ticket.priority,
            author_name="System",
            assigned_to_id=ticket.assigned_to_id,
            assigned_team_id=ticket.assigned_team_id,
            is_confidential=ticket.is_confidential,
            due_date=new_due_date,
            recurrence_rule=None,
            commit=False,
        )
        _clone_checklists(ticket, new_ticket)
        _advance_recurrence_date(ticket, now)
        count += 1
    return count


def _compute_new_due_date(ticket: Ticket, now: object) -> object:
    """Derive a new due date for the cloned ticket."""
    if ticket.due_date and ticket.created_at:
        delta = ticket.due_date - ticket.created_at.date()
        return (now.date() + delta)
    return ticket.due_date


def _clone_checklists(source: Ticket, target: Ticket) -> None:
    """Copy checklist items from *source* (or its template) to *target*."""
    if source.checklist_template_id and source.checklist_template:
        for item in source.checklist_template.items:
            ChecklistService.add_checklist_item(target.id, item.title)
    else:
        for item in source.checklists:
            ChecklistService.add_checklist_item(
                target.id, item.title, item.assigned_to_id
            )


def _advance_recurrence_date(ticket: Ticket, now: object) -> None:
    """Move the recurrence next_date forward by the ticket's rule."""
    rec = ticket.recurrence
    rule = rec.rule.lower()
    increment = _RECURRENCE_INCREMENTS.get(rule)
    if increment is None:
        _logger.warning(
            "Unknown recurrence rule '%s' for ticket %d — defaulting to monthly",
            rule, ticket.id,
        )
        increment = relativedelta(months=1)

    next_date = rec.next_date
    while next_date <= now:
        next_date += increment
    rec.next_date = next_date


# ---------------------------------------------------------------------------
# SLA escalation
# ---------------------------------------------------------------------------

def process_sla_escalations(app: Flask) -> None:
    """Daily SLA check: notify assignees and admins about overdue tickets.

    Grace periods before first escalation:
        Prio 1 (Hoch):   0 days
        Prio 2 (Mittel): 1 day
        Prio 3 (Niedrig):3 days

    Anti-spam: re-escalation only after 23 hours.

    Instead of sending one email per ticket, this job collects all escalated
    tickets and sends a **single digest email per worker** as a daily status
    report.  Admins receive a separate digest for all high-priority tickets.
    """
    with app.app_context():
        now = get_utc_now()
        try:
            overdue_tickets = _fetch_overdue_tickets(now)
            escalated = _escalate_tickets(overdue_tickets, now, EmailService)
            if escalated > 0:
                db.session.commit()
                _logger.info(
                    "SLA escalation: %d ticket(s) escalated.", escalated
                )
        except Exception as exc:
            db.session.rollback()
            _logger.error("Error in SLA escalation job: %s", exc)


def _fetch_overdue_tickets(now: object) -> List[Ticket]:
    """Return all non-deleted open tickets that are past their due date.

    Tickets due today are not flagged as overdue until the following day.
    """
    from sqlalchemy.orm import joinedload
    return Ticket.query.filter(
        Ticket.is_deleted.is_(False),
        Ticket.status.in_(_OPEN_STATUSES),
        Ticket.due_date.isnot(None),
        Ticket.due_date < now.date(),
    ).options(
        joinedload(Ticket.assigned_to),
    ).all()


def _escalate_tickets(
    tickets: List[Ticket], now: object, email_service: object
) -> int:
    """Evaluate and escalate each overdue ticket.  Returns count.

    Comments and in-app notifications are created per ticket, but emails
    are collected and sent as **one digest per recipient** at the end.
    """
    # Collect digest data: worker_id -> list of ticket info dicts
    assignee_digest: Dict[int, List[Dict[str, object]]] = defaultdict(list)
    high_prio_tickets: List[Dict[str, object]] = []

    escalated = 0
    for ticket in tickets:
        if not _should_escalate(ticket, now):
            continue
        days_overdue = (now.date() - ticket.due_date).days
        _add_escalation_comment(ticket, days_overdue)
        _create_escalation_notification(ticket, days_overdue)

        # Collect for digest email instead of sending immediately
        if ticket.assigned_to_id:
            assignee_digest[ticket.assigned_to_id].append({
                "id": ticket.id,
                "title": ticket.title,
                "days_overdue": days_overdue,
                "priority": ticket.priority,
            })

        if ticket.priority == TicketPriority.HOCH.value:
            high_prio_tickets.append({
                "id": ticket.id,
                "title": ticket.title,
                "days_overdue": days_overdue,
                "priority": ticket.priority,
                "assignee_name": (
                    ticket.assigned_to.name
                    if ticket.assigned_to else "—"
                ),
            })

        _create_admin_notifications_for_high_prio(ticket, days_overdue)
        ticket.last_escalated_at = now
        escalated += 1

    # Send one digest email per assignee
    _send_assignee_digests(assignee_digest, email_service)

    # Send one admin digest for all high-priority tickets
    _send_admin_digest(high_prio_tickets, email_service)

    return escalated


def _should_escalate(ticket: Ticket, now: object) -> bool:
    """Check grace period and anti-spam rules for a single ticket."""
    days_overdue = (now.date() - ticket.due_date).days
    grace = _GRACE_DAYS.get(ticket.priority, 1)
    if days_overdue < grace:
        return False
    if ticket.last_escalated_at:
        hours_since = (now - ticket.last_escalated_at).total_seconds() / 3600
        if hours_since < _ANTI_SPAM_HOURS:
            return False
    return True


def _add_escalation_comment(ticket: Ticket, days_overdue: int) -> None:
    """Add a system comment documenting the SLA escalation."""
    comment = Comment(
        ticket_id=ticket.id,
        author="System",
        text=(
            f"SLA-Eskalation: Ticket seit {days_overdue} Tag(en) überfällig "
            f"(Fälligkeit: {ticket.due_date.strftime('%d.%m.%Y')})."
        ),
        is_system_event=True,
        event_type="SLA_ESCALATION",
    )
    db.session.add(comment)


def _create_escalation_notification(
    ticket: Ticket, days_overdue: int
) -> None:
    """Create an in-app notification for the ticket assignee (no email)."""
    if not ticket.assigned_to_id:
        return
    TicketCoreService.create_notification(
        user_id=ticket.assigned_to_id,
        message=(
            f"SLA-Eskalation: Ticket #{ticket.id} ist seit "
            f"{days_overdue} Tag(en) überfällig."
        ),
        link=f"/ticket/{ticket.id}",
    )


def _create_admin_notifications_for_high_prio(
    ticket: Ticket, days_overdue: int
) -> None:
    """For high-priority tickets, create in-app notifications for admins."""
    if ticket.priority != TicketPriority.HOCH.value:
        return
    admins = Worker.query.filter_by(role="admin", is_active=True).all()
    for admin in admins:
        if admin.id != ticket.assigned_to_id:
            TicketCoreService.create_notification(
                user_id=admin.id,
                message=(
                    f"SLA-Eskalation (Prio HOCH): Ticket #{ticket.id} "
                    f"seit {days_overdue} Tag(en) überfällig."
                ),
                link=f"/ticket/{ticket.id}",
            )


def _send_assignee_digests(
    assignee_digest: Dict[int, List[Dict[str, object]]],
    email_service: object,
) -> None:
    """Send one consolidated SLA digest email per assignee."""
    for worker_id, ticket_list in assignee_digest.items():
        worker = db.session.get(Worker, worker_id)
        if not worker or not worker.email:
            continue
        if not worker.email_notifications_enabled:
            continue
        email_service.send_sla_escalation_digest(
            worker.name, ticket_list, recipient_email=worker.email,
        )


def _send_admin_digest(
    high_prio_tickets: List[Dict[str, object]],
    email_service: object,
) -> None:
    """Send one consolidated admin digest for all high-priority escalations."""
    if not high_prio_tickets:
        return
    admins = Worker.query.filter_by(role="admin", is_active=True).all()
    for admin in admins:
        if not admin.email:
            continue
        if not admin.email_notifications_enabled:
            continue
        email_service.send_sla_admin_digest(
            admin.name, high_prio_tickets, admin_email=admin.email,
        )


# ---------------------------------------------------------------------------
# Reminder notifications
# ---------------------------------------------------------------------------

def process_reminder_notifications(app: Flask) -> None:
    """Daily job: send in-app notifications for tickets with due reminders.

    Targets tickets where:
    - status is "wartet"
    - reminder_date <= today
    - no notification has been sent yet (reminder_notified_at is NULL)
    """
    with app.app_context():
        now = get_utc_now()
        try:
            tickets = _fetch_due_reminder_tickets(now)
            notified = _notify_reminder_tickets(tickets, now)
            if notified > 0:
                db.session.commit()
                _logger.info(
                    "Reminder notifications: %d ticket(s) notified.", notified
                )
        except Exception as exc:
            db.session.rollback()
            _logger.error("Error in reminder notification job: %s", exc)


def _fetch_due_reminder_tickets(now: object) -> List[Ticket]:
    """Return waiting tickets whose reminder_date is due and not yet notified."""
    return Ticket.query.filter(
        Ticket.is_deleted.is_(False),
        Ticket.status == TicketStatus.WARTET.value,
        Ticket.reminder_date.isnot(None),
        Ticket.reminder_date <= now,
        Ticket.reminder_notified_at.is_(None),
    ).all()


def _notify_reminder_tickets(tickets: List[Ticket], now: object) -> int:
    """Send a notification to the assignee for each due reminder ticket."""
    notified = 0
    for ticket in tickets:
        if ticket.assigned_to_id:
            TicketCoreService.create_notification(
                user_id=ticket.assigned_to_id,
                message=(
                    f"Wiedervorlage: Ticket #{ticket.id} "
                    f"\u201e{ticket.title}\u201c \u2014 bitte nachfassen."
                ),
                link=f"/ticket/{ticket.id}",
            )
        ticket.reminder_notified_at = now
        notified += 1
    return notified


# ---------------------------------------------------------------------------
# Scheduler registration
# ---------------------------------------------------------------------------

def schedule_sla_job(app: Flask) -> None:
    """Register the SLA escalation job (daily at 07:00 UTC)."""
    try:
        from extensions import scheduler

        scheduler.add_job(
            id="process_sla_escalations_job",
            func=lambda: process_sla_escalations(app),
            trigger="cron",
            hour=7,
            minute=0,
            replace_existing=True,
        )
        _logger.info("Scheduled job: process_sla_escalations at 07:00")
    except Exception as exc:
        _logger.error("Failed to schedule SLA escalation job: %s", exc)


def schedule_recurring_job(app: Flask) -> None:
    """Register the recurring ticket job (daily at 02:00 UTC)."""
    try:
        from extensions import scheduler

        scheduler.add_job(
            id="process_recurring_tickets_job",
            func=lambda: process_recurring_tickets(app),
            trigger="cron",
            hour=2,
            minute=0,
            replace_existing=True,
        )
        _logger.info("Scheduled job: process_recurring_tickets at 02:00")
    except Exception as exc:
        _logger.error("Failed to schedule recurring tickets job: %s", exc)


def schedule_reminder_job(app: Flask) -> None:
    """Register the reminder notification job (daily at 06:30 UTC)."""
    try:
        from extensions import scheduler

        scheduler.add_job(
            id="process_reminder_notifications_job",
            func=lambda: process_reminder_notifications(app),
            trigger="cron",
            hour=6,
            minute=30,
            replace_existing=True,
        )
        _logger.info("Scheduled job: process_reminder_notifications at 06:30")
    except Exception as exc:
        _logger.error("Failed to schedule reminder notification job: %s", exc)
