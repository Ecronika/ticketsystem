"""Idempotency tests including race-condition simulation."""

import threading

import pytest

from models import Ticket
from services.api_key_service import ApiKeyService


@pytest.fixture
def petra_token(app, db_session, admin_fixture, worker_fixture):
    _, plaintext = ApiKeyService.create_key(
        name="HP", scopes=["write:tickets"],
        default_assignee_id=worker_fixture.id,
        rate_limit_per_minute=1000, created_by_worker_id=admin_fixture.id,
    )
    return plaintext


def test_parallel_duplicate_creates_one_ticket(app, client, db_session, petra_token):
    """Two simultaneous requests with same external_call_id.

    Unique-constraint catches the race; second gets 200 (duplicate) or 201.
    At most one ticket must exist after both complete.
    """
    payload = {
        "webhook_id": "w", "data": {"id": "race_001", "duration": 1,
                                    "topic": "t", "summary": "s",
                                    "messages": []},
    }
    headers = {"Authorization": f"Bearer {petra_token}"}
    results = []

    def fire():
        with app.test_client() as c:
            r = c.post("/api/v1/webhook/calls", json=payload, headers=headers)
            results.append(r.status_code)

    t1 = threading.Thread(target=fire)
    t2 = threading.Thread(target=fire)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Exactly one ticket must exist
    assert Ticket.query.filter_by(external_call_id="race_001").count() == 1
    # Both requests must have succeeded (201 created or 200 duplicate)
    assert all(s in (200, 201) for s in results)
