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
