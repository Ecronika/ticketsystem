"""Tests for services/api_key_service.py."""

import hashlib

import pytest

from models import ApiKey, ApiKeyIpRange, Worker
from services.api_key_service import ApiKeyService
from exceptions import InvalidApiKey, IpNotAllowed


def test_create_returns_plaintext_token_once(app, db_session, admin_fixture, worker_fixture):
    key, plaintext = ApiKeyService.create_key(
        name="HalloPetra Prod",
        scopes=["write:tickets"],
        default_assignee_id=worker_fixture.id,
        rate_limit_per_minute=60,
        created_by_worker_id=admin_fixture.id,
    )
    assert plaintext.startswith("tsk_")
    assert len(plaintext) == 52  # "tsk_" + 48 chars
    assert key.key_prefix == plaintext[:12]
    # Hash stimmt
    expected_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    assert key.key_hash == expected_hash
    # Klartext wird NICHT gespeichert
    assert plaintext not in str(key.__dict__.values())


def test_lookup_by_token_returns_key(app, db_session, admin_fixture, worker_fixture):
    key, plaintext = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=worker_fixture.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_fixture.id,
    )
    result = ApiKeyService.authenticate(plaintext)
    assert result.id == key.id


def test_lookup_wrong_token_raises_invalid(app, db_session, admin_fixture, worker_fixture):
    ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=worker_fixture.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_fixture.id,
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


def test_lookup_revoked_key_raises_invalid(app, db_session, admin_fixture, worker_fixture):
    key, plaintext = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=worker_fixture.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_fixture.id,
    )
    ApiKeyService.revoke_key(key.id, revoked_by_worker_id=admin_fixture.id)
    with pytest.raises(InvalidApiKey):
        ApiKeyService.authenticate(plaintext)
