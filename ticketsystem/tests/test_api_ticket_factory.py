"""Tests for services/api_ticket_factory.py."""

from werkzeug.security import generate_password_hash

from models import Worker
from services.api_key_service import ApiKeyService
from services.api_ticket_factory import ApiTicketFactory
from routes.api._schemas import HalloPetraWebhookPayload


def _sample_payload(call_id: str = "call_abc123") -> dict:
    return {
        "webhook_id": "wh_xyz",
        "data": {
            "id": call_id,
            "duration": 125,
            "phone": "+491234567890",
            "topic": "Heizungswartung anfragen",
            "summary": "Kunde möchte einen Termin.",
            "messages": [
                {"role": "assistant", "content": "Guten Tag"},
                {"role": "user", "content": "Ich möchte..."},
            ],
            "collected_data": {"wunschtermin": "Dienstag"},
            "contact_data": {
                "id": "c_xyz", "name": "Max Mustermann",
                "phone": "+491234567890", "email": "max@mustermann.de",
                "address": "Musterstraße 1",
            },
            "email_send_to": "info@beispiel.de",
            "forwarded_to": "+4930987654",
            "previous_webhook_calls": [],
        },
    }


def test_create_ticket_sets_basics(app, db_session, petra_key):
    payload = HalloPetraWebhookPayload(**_sample_payload())
    ticket, method = ApiTicketFactory.create_from_payload(petra_key, payload)
    assert ticket.external_call_id == "call_abc123"
    assert "Heizungswartung" in ticket.title
    assert ticket.contact.name == "Max Mustermann"
    assert ticket.contact.phone == "+491234567890"
    assert ticket.contact.email == "max@mustermann.de"
    assert ticket.contact.channel == "Telefon (KI-Agent)"
    assert "Dienstag" in ticket.description or "Kunde möchte" in ticket.description


def test_create_ticket_stores_transcripts(app, db_session, petra_key):
    payload = HalloPetraWebhookPayload(**_sample_payload())
    ticket, _ = ApiTicketFactory.create_from_payload(petra_key, payload)
    assert len(ticket.transcripts) == 2
    assert ticket.transcripts[0].role == "assistant"
    assert ticket.transcripts[0].position == 0
    assert ticket.transcripts[1].role == "user"
    assert ticket.transcripts[1].position == 1


def test_create_ticket_metadata_contains_address(app, db_session, petra_key):
    payload = HalloPetraWebhookPayload(**_sample_payload())
    ticket, _ = ApiTicketFactory.create_from_payload(petra_key, payload)
    meta = ticket.get_external_metadata()
    assert meta["contact_data"]["address"] == "Musterstraße 1"
    assert meta["duration"] == 125
    assert "forwarded_to" in meta


def test_assignment_email_match(app, db_session, admin_worker):
    matched = Worker(name="InfoUser", is_active=True, role="WORKER",
                     email="info@beispiel.de",
                     pin_hash=generate_password_hash("9173"))
    db_session.add(matched)
    db_session.commit()
    key, _ = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=matched.id,  # auch default, aber Match soll greifen
        rate_limit_per_minute=60, created_by_worker_id=admin_worker.id,
    )
    payload = HalloPetraWebhookPayload(**_sample_payload())
    ticket, method = ApiTicketFactory.create_from_payload(key, payload)
    assert ticket.assigned_to_id == matched.id
    assert method == "email_match"


def test_assignment_fallback_to_default(app, db_session, petra_key, default_assignee):
    payload_dict = _sample_payload()
    payload_dict["data"]["email_send_to"] = "unbekannt@nirgendwo.xx"
    payload = HalloPetraWebhookPayload(**payload_dict)
    ticket, method = ApiTicketFactory.create_from_payload(petra_key, payload)
    assert ticket.assigned_to_id == default_assignee.id
    assert method == "default"


def test_assignment_inactive_worker_fallback(app, db_session, admin_worker, default_assignee):
    inactive = Worker(name="Inactive", is_active=False, role="WORKER",
                      email="info@beispiel.de",
                      pin_hash=generate_password_hash("6482"))
    db_session.add(inactive)
    db_session.commit()
    key, _ = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_worker.id,
    )
    payload = HalloPetraWebhookPayload(**_sample_payload())
    ticket, method = ApiTicketFactory.create_from_payload(key, payload)
    assert ticket.assigned_to_id == default_assignee.id
    assert method == "inactive_worker_fallback"


def test_confidential_flag_applied(app, db_session, petra_key):
    payload = HalloPetraWebhookPayload(**_sample_payload())
    ticket, _ = ApiTicketFactory.create_from_payload(petra_key, payload)
    assert ticket.is_confidential is True
