"""Tests for services/api_key_service.py."""

import hashlib

import pytest

from models import ApiAuditLog
from services.api_key_service import ApiKeyService
from exceptions import InvalidApiKey, IpNotAllowed


def test_create_returns_plaintext_token_once(app, db_session, admin_worker, default_assignee):
    key, plaintext = ApiKeyService.create_key(
        name="HalloPetra Prod",
        scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60,
        created_by_worker_id=admin_worker.id,
    )
    assert plaintext.startswith("tsk_")
    assert len(plaintext) == 52  # "tsk_" + 48 chars
    assert key.key_prefix == plaintext[:12]
    # Hash stimmt
    expected_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    assert key.key_hash == expected_hash
    # Reload from DB to confirm Klartext not stored anywhere accessible.
    db_session.refresh(key)
    assert key.key_hash != plaintext
    assert plaintext[4:] not in (key.key_prefix or "")  # body not in prefix


def test_lookup_by_token_returns_key(app, db_session, admin_worker, default_assignee):
    key, plaintext = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_worker.id,
    )
    result = ApiKeyService.authenticate(plaintext)
    assert result.id == key.id


def test_lookup_wrong_token_raises_invalid(app, db_session, admin_worker, default_assignee):
    ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_worker.id,
    )
    with pytest.raises(InvalidApiKey):
        ApiKeyService.authenticate("tsk_" + "x" * 48)


def test_lookup_invalid_format_raises_invalid(app, db_session):
    with pytest.raises(InvalidApiKey):
        ApiKeyService.authenticate("not_a_token")
    with pytest.raises(InvalidApiKey):
        ApiKeyService.authenticate("")
    with pytest.raises(InvalidApiKey):
        ApiKeyService.authenticate(None)


def test_lookup_revoked_key_raises_invalid(app, db_session, admin_worker, default_assignee):
    key, plaintext = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_worker.id,
    )
    ApiKeyService.revoke_key(key.id, revoked_by_worker_id=admin_worker.id)
    with pytest.raises(InvalidApiKey):
        ApiKeyService.authenticate(plaintext)


def test_ip_check_empty_allowlist_allows_all(app, db_session, admin_worker, default_assignee):
    key, _ = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_worker.id,
    )
    # Keine Ranges vorhanden → alles OK
    ApiKeyService.check_ip(key, "203.0.113.1")
    ApiKeyService.check_ip(key, "198.51.100.99")
    ApiKeyService.check_ip(key, "::1")


def test_ip_check_with_allowlist_enforces(app, db_session, admin_worker, default_assignee):
    key, _ = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_worker.id,
    )
    ApiKeyService.add_ip_range(
        key.id, "203.0.113.0/24",
        note="test", created_by_worker_id=admin_worker.id,
    )
    ApiKeyService.check_ip(key, "203.0.113.5")      # okay
    with pytest.raises(IpNotAllowed):
        ApiKeyService.check_ip(key, "198.51.100.1")  # draußen


def test_ip_check_invalid_source_raises(app, db_session, admin_worker, default_assignee):
    key, _ = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_worker.id,
    )
    ApiKeyService.add_ip_range(
        key.id, "203.0.113.0/24",
        note="t", created_by_worker_id=admin_worker.id,
    )
    with pytest.raises(IpNotAllowed):
        ApiKeyService.check_ip(key, "not-an-ip")


def test_has_scope(app, db_session, admin_worker, default_assignee):
    key, _ = ApiKeyService.create_key(
        name="K", scopes=["write:tickets", "read:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_worker.id,
    )
    assert key.has_scope("write:tickets")
    assert key.has_scope("read:tickets")
    assert not key.has_scope("admin:tickets")


def test_mark_used_updates_within_60s_throttled(app, db_session, admin_worker, default_assignee):
    key, _ = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_worker.id,
    )
    ApiKeyService.mark_used(key, "203.0.113.1")
    first = key.last_used_at
    ApiKeyService.mark_used(key, "203.0.113.2")  # innerhalb 60s
    # last_used_at sollte nicht aktualisiert worden sein
    assert key.last_used_at == first
    # last_used_ip KANN aktualisiert sein oder nicht — konservativ: auch throttled
    assert key.last_used_ip == "203.0.113.1"


def test_log_audit_success(app, db_session, admin_worker, default_assignee):
    key, _ = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_worker.id,
    )
    ApiKeyService.log_audit(
        api_key=key, key_prefix=key.key_prefix,
        source_ip="203.0.113.1", method="POST", path="/api/v1/webhook/calls",
        status_code=201, latency_ms=42, outcome="success",
        external_ref="call_abc", assignment_method="default",
        request_id="abc-123",
    )
    entry = ApiAuditLog.query.filter_by(request_id="abc-123").one()
    assert entry.outcome == "success"
    assert entry.api_key_id == key.id


def test_log_audit_failed_auth_without_key(app, db_session):
    ApiKeyService.log_audit(
        api_key=None, key_prefix=None,
        source_ip="45.131.112.9", method="POST", path="/api/v1/webhook/calls",
        status_code=401, latency_ms=2, outcome="auth_failed",
        request_id="xyz-789",
    )
    entry = ApiAuditLog.query.filter_by(request_id="xyz-789").one()
    assert entry.api_key_id is None
    assert entry.outcome == "auth_failed"


def test_authenticate_does_not_crash_under_many_invalid_tokens(
    app, db_session, admin_worker, default_assignee,
):
    """Smoke test: authenticate handles many invalid-format and wrong-hash calls
    without raising unexpected errors or leaking state.

    NOTE: This is NOT a timing-attack guarantee — DB latency dominates the
    hash comparison step. Timing-safety is verified by inspecting the code:
    authenticate uses hmac.compare_digest (see code).
    """
    key, plaintext = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_worker.id,
    )
    wrong_prefix = "tsk_" + "z" * 48
    wrong_hash_same_prefix = key.key_prefix + "a" * (52 - len(key.key_prefix))

    for token in (wrong_prefix, wrong_hash_same_prefix):
        for _ in range(10):
            try:
                ApiKeyService.authenticate(token)
            except InvalidApiKey:
                pass
