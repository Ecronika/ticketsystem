"""Create Ticket objects from validated HalloPetra payloads.

Kept separate from TicketCoreService because the mapping logic is
vendor-specific; TicketCoreService stays clean of API concerns.
"""

from __future__ import annotations

from typing import Optional, Tuple

from sqlalchemy import func

from extensions import db
from models import ApiKey, Ticket, TicketTranscript, Worker
from routes.api._schemas import HalloPetraCallData, HalloPetraWebhookPayload
from services._helpers import db_transaction
from utils import get_utc_now


_CONTACT_CHANNEL = "Telefon (KI-Agent)"

# Column length constraints for TicketContact fields
_CONTACT_NAME_MAX = 100
_CONTACT_PHONE_MAX = 50
_CONTACT_EMAIL_MAX = 150

# Ticket title max length (DB column cap)
_TICKET_TITLE_MAX = 100

# Soft-wrap for summary-derived titles — intentionally shorter than the DB
# cap so long summaries become readable titles. Summary text is still stored
# in full in ticket.description.
_TITLE_SUMMARY_CAP = 80


class ApiTicketFactory:
    """Factory for API-created tickets. Static methods only."""

    @staticmethod
    @db_transaction
    def create_from_payload(
        api_key: ApiKey,
        payload: HalloPetraWebhookPayload,
    ) -> Tuple[Ticket, str]:
        """Create a new ticket from the payload. Return (ticket, assignment_method).

        Assumes caller has verified idempotency (no existing ticket with same
        external_call_id). Commits within db_transaction.
        """
        data = payload.data
        ticket = Ticket(
            title=_derive_title(data),
            description=_derive_description(data),
            external_call_id=data.id,
            is_confidential=api_key.create_confidential_tickets,
            created_at=get_utc_now(),
        )

        # Contact (via ensure_contact, respecting CLAUDE.md rule #3)
        contact = ticket.ensure_contact()
        contact.name = _clamp(_pick_name(data), _CONTACT_NAME_MAX)
        contact.phone = _clamp(_pick_phone(data), _CONTACT_PHONE_MAX)
        contact.email = _clamp(_pick_email(data), _CONTACT_EMAIL_MAX)
        contact.channel = _CONTACT_CHANNEL

        # Assignment
        assignee_id, method = _resolve_assignee(api_key, data.email_send_to)
        ticket.assigned_to_id = assignee_id

        # External metadata (everything not mapped to dedicated fields)
        ticket.set_external_metadata({
            "duration": data.duration,
            "main_task_id": data.main_task_id,
            "collected_data": data.collected_data,
            "contact_data": (data.contact_data.model_dump() if data.contact_data else None),
            "forwarded_to": data.forwarded_to,
            "previous_webhook_calls": data.previous_webhook_calls,
            "webhook_id": payload.webhook_id,
        })

        db.session.add(ticket)
        db.session.flush()  # ticket.id available

        # Transcripts
        for idx, msg in enumerate(data.messages):
            entry = TicketTranscript(
                ticket_id=ticket.id,
                position=idx,
                role=msg.role,
                content=msg.content,
            )
            db.session.add(entry)

        db.session.commit()
        return ticket, method


def _clamp(value: Optional[str], max_len: int) -> Optional[str]:
    """Truncate string to max_len if non-None."""
    if value is None:
        return None
    return value[:max_len]


def _derive_title(data: HalloPetraCallData) -> str:
    """Build ticket title from topic or summary, truncated to column max."""
    if data.topic:
        return data.topic[:_TICKET_TITLE_MAX]
    if data.summary:
        return data.summary[:_TITLE_SUMMARY_CAP]
    return f"Anruf {data.id}"[:_TICKET_TITLE_MAX]


def _derive_description(data: HalloPetraCallData) -> str:
    """Build ticket description from summary and forwarded_to note."""
    parts = []
    if data.summary:
        parts.append(data.summary)
    if data.forwarded_to:
        parts.append(f"\nWeitergeleitet an: {data.forwarded_to}")
    return "\n".join(parts)


def _pick_name(data: HalloPetraCallData) -> Optional[str]:
    """Return contact name: contact_data.name > collected_data.contact_name."""
    if data.contact_data and data.contact_data.name:
        return data.contact_data.name
    return data.collected_data.get("contact_name")


def _pick_phone(data: HalloPetraCallData) -> Optional[str]:
    """Pick the best phone number.

    Priority: contact_data.phone (structured) > collected_data.contact_phone
    (AI-extracted) > data.phone (call-level number, always present).
    The 3rd tier is unique to phone because the call itself has an inherent
    caller number — no equivalent for name or email.
    """
    if data.contact_data and data.contact_data.phone:
        return data.contact_data.phone
    return data.collected_data.get("contact_phone") or data.phone


def _pick_email(data: HalloPetraCallData) -> Optional[str]:
    """Return email for contact record: contact_data.email > collected_data.contact_email.

    NOTE: data.email_send_to is NOT used here — it is only for worker assignment.
    """
    if data.contact_data and data.contact_data.email:
        return data.contact_data.email
    return data.collected_data.get("contact_email")


def _resolve_assignee(api_key: ApiKey, email_send_to: Optional[str]) -> Tuple[int, str]:
    """Return (assignee_id, assignment_method).

    Priority: active email match > inactive_worker_fallback > ambiguous_fallback > default.
    """
    default_id = api_key.default_assignee_worker_id
    if not email_send_to:
        return default_id, "default"

    email_lower = email_send_to.strip().lower()
    matches = Worker.query.filter(
        func.lower(Worker.email) == email_lower
    ).all()

    if not matches:
        return default_id, "default"
    if len(matches) > 1:
        return default_id, "ambiguous_fallback"

    w = matches[0]
    if not w.is_active:
        return default_id, "inactive_worker_fallback"
    return w.id, "email_match"
