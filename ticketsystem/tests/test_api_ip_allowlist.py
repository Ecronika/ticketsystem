"""End-to-end IP allowlist enforcement via CF-Connecting-IP header."""

import pytest

from services.api_key_service import ApiKeyService


@pytest.fixture
def allowlisted(admin_worker, default_assignee):
    key, plaintext = ApiKeyService.create_key(
        name="HP", scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=1000, created_by_worker_id=admin_worker.id,
    )
    ApiKeyService.add_ip_range(
        key.id, "203.0.113.0/24", note="test",
        created_by_worker_id=admin_worker.id,
    )
    return plaintext


def test_allowed_ip_passes(client, allowlisted):
    r = client.post(
        "/api/v1/webhook/calls",
        json={"webhook_id": "w", "data": {"id": "ip_ok", "duration": 1,
                                          "topic": "t", "summary": "s",
                                          "messages": []}},
        headers={
            "Authorization": f"Bearer {allowlisted}",
            "CF-Connecting-IP": "203.0.113.42",
        },
    )
    assert r.status_code == 201


def test_blocked_ip_returns_403(client, allowlisted):
    r = client.post(
        "/api/v1/webhook/calls",
        json={"webhook_id": "w", "data": {"id": "ip_no", "duration": 1,
                                          "topic": "t", "summary": "s",
                                          "messages": []}},
        headers={
            "Authorization": f"Bearer {allowlisted}",
            "CF-Connecting-IP": "198.51.100.9",
        },
    )
    assert r.status_code == 403
    assert r.get_json() == {"error": "forbidden"}
