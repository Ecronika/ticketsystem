"""End-to-end tests for /api/v1/webhook/calls."""

import json

import pytest

from models import ApiAuditLog, Ticket
from services.api_key_service import ApiKeyService


def _payload(call_id="call_001"):
    return {
        "webhook_id": "wh_xxx",
        "data": {
            "id": call_id,
            "duration": 42,
            "topic": "Test-Anruf",
            "summary": "Summary",
            "messages": [{"role": "user", "content": "Hi"}],
            "contact_data": {
                "name": "Test Kunde",
                "email": "test@kunde.de",
                "phone": "+490000",
            },
            "email_send_to": "info@beispiel.de",
        },
    }


@pytest.fixture
def petra_token(app, db_session, admin_fixture, worker_fixture):
    _, plaintext = ApiKeyService.create_key(
        name="HP", scopes=["write:tickets"],
        default_assignee_id=worker_fixture.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_fixture.id,
    )
    return plaintext


def test_webhook_creates_ticket_201(client, db_session, petra_token):
    r = client.post(
        "/api/v1/webhook/calls",
        json=_payload(),
        headers={"Authorization": f"Bearer {petra_token}"},
    )
    assert r.status_code == 201
    body = r.get_json()
    assert body["status"] == "created"
    assert "ticket_id" in body
    t = db_session.get(Ticket, body["ticket_id"])
    assert t.external_call_id == "call_001"


def test_webhook_idempotent_returns_200(client, db_session, petra_token):
    r1 = client.post(
        "/api/v1/webhook/calls",
        json=_payload("call_002"),
        headers={"Authorization": f"Bearer {petra_token}"},
    )
    assert r1.status_code == 201
    first_id = r1.get_json()["ticket_id"]

    r2 = client.post(
        "/api/v1/webhook/calls",
        json=_payload("call_002"),
        headers={"Authorization": f"Bearer {petra_token}"},
    )
    assert r2.status_code == 200
    assert r2.get_json()["status"] == "duplicate"
    assert r2.get_json()["ticket_id"] == first_id

    assert Ticket.query.filter_by(external_call_id="call_002").count() == 1


def test_webhook_malformed_json_returns_400(client, petra_token):
    r = client.post(
        "/api/v1/webhook/calls",
        data="not-json",
        content_type="application/json",
        headers={"Authorization": f"Bearer {petra_token}"},
    )
    assert r.status_code == 400


def test_webhook_wrong_content_type_returns_415(client, petra_token):
    r = client.post(
        "/api/v1/webhook/calls",
        data=json.dumps(_payload()),
        content_type="text/plain",
        headers={"Authorization": f"Bearer {petra_token}"},
    )
    assert r.status_code == 415


def test_webhook_too_large_returns_413(client, petra_token):
    big = _payload("call_big")
    big["data"]["summary"] = "x" * 200_000
    r = client.post(
        "/api/v1/webhook/calls",
        json=big,
        headers={"Authorization": f"Bearer {petra_token}"},
    )
    assert r.status_code == 413


def test_webhook_missing_scope_returns_403(client, db_session, admin_fixture, worker_fixture):
    _, plaintext = ApiKeyService.create_key(
        name="K", scopes=["read:tickets"],  # fehlendes write:tickets
        default_assignee_id=worker_fixture.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_fixture.id,
    )
    r = client.post(
        "/api/v1/webhook/calls",
        json=_payload(),
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert r.status_code == 403


def test_webhook_expected_webhook_id_mismatch_rejects(
    client, db_session, admin_fixture, worker_fixture,
):
    _, plaintext = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=worker_fixture.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_fixture.id,
        expected_webhook_id="wh_expected",
    )
    r = client.post(
        "/api/v1/webhook/calls",
        json=_payload(),  # webhook_id="wh_xxx"
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert r.status_code == 400
    assert r.get_json()["error"] == "validation_failed"


def test_audit_log_external_ref_set(client, db_session, petra_token):
    client.post(
        "/api/v1/webhook/calls",
        json=_payload("call_audit"),
        headers={"Authorization": f"Bearer {petra_token}"},
    )
    entry = ApiAuditLog.query.order_by(ApiAuditLog.id.desc()).first()
    assert entry.external_ref == "call_audit"
    assert entry.outcome == "success"
    assert entry.assignment_method == "default"
