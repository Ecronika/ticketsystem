"""Service for API-key management (public REST API)."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from exceptions import InvalidApiKey, IpNotAllowed
from extensions import db
from models import ApiKey, ApiKeyIpRange, ApiAuditLog
from services._helpers import db_transaction
from utils import get_utc_now


TOKEN_PREFIX = "tsk_"
TOKEN_RANDOM_LENGTH = 48  # characters (not bytes)
_ALPHABET = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
)
_KEY_PREFIX_LENGTH = len(TOKEN_PREFIX) + 8  # prefix + 8 random chars for indexed lookup
_ALPHABET_SET = frozenset(_ALPHABET)


def _generate_token() -> str:
    body = "".join(secrets.choice(_ALPHABET) for _ in range(TOKEN_RANDOM_LENGTH))
    return f"{TOKEN_PREFIX}{body}"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _is_valid_format(token: str) -> bool:
    if not token.startswith(TOKEN_PREFIX):
        return False
    expected_len = len(TOKEN_PREFIX) + TOKEN_RANDOM_LENGTH
    if len(token) != expected_len:
        return False
    body = token[len(TOKEN_PREFIX):]
    return all(c in _ALPHABET_SET for c in body)


class ApiKeyService:
    """Static-method service for API key lifecycle."""

    @staticmethod
    @db_transaction
    def create_key(
        name: str,
        scopes: List[str],
        default_assignee_id: Optional[int],
        rate_limit_per_minute: int,
        created_by_worker_id: int,
        expected_webhook_id: Optional[str] = None,
        create_confidential_tickets: bool = True,
        expires_at: Optional[datetime] = None,
    ) -> Tuple[ApiKey, str]:
        """Create a new API key. Returns (key, plaintext_token).

        The plaintext is returned ONCE and never stored.
        """
        if not name or not name.strip():
            raise ValueError("Name darf nicht leer sein.")
        if not scopes:
            raise ValueError("Mindestens ein Scope erforderlich.")
        if "write:tickets" in scopes and default_assignee_id is None:
            raise ValueError(
                "Für Scope 'write:tickets' ist ein Standard-Zuweisungs-Worker Pflicht."
            )
        if rate_limit_per_minute < 1:
            raise ValueError("Rate-Limit muss mindestens 1 sein.")

        token = _generate_token()
        key = ApiKey(
            name=name.strip(),
            key_prefix=token[:_KEY_PREFIX_LENGTH],
            key_hash=_hash_token(token),
            scopes=",".join(scopes),
            rate_limit_per_minute=rate_limit_per_minute,
            default_assignee_worker_id=default_assignee_id,
            expected_webhook_id=expected_webhook_id,
            create_confidential_tickets=create_confidential_tickets,
            created_by_worker_id=created_by_worker_id,
            expires_at=expires_at,
        )
        db.session.add(key)
        db.session.commit()
        return key, token

    @staticmethod
    def authenticate(token: Optional[str]) -> ApiKey:
        """Look up and validate an API key by its plaintext token.

        Raises InvalidApiKey for any authentication failure (generic).
        """
        if not token or not isinstance(token, str):
            raise InvalidApiKey()
        if not _is_valid_format(token):
            raise InvalidApiKey()
        prefix = token[:_KEY_PREFIX_LENGTH]
        candidates = ApiKey.query.filter_by(key_prefix=prefix).all()
        expected_hash = _hash_token(token)
        for candidate in candidates:
            if hmac.compare_digest(candidate.key_hash, expected_hash):
                if not candidate.is_usable():
                    raise InvalidApiKey()
                return candidate
        raise InvalidApiKey()

    @staticmethod
    @db_transaction
    def revoke_key(key_id: int, revoked_by_worker_id: int) -> None:
        """Revoke an API key by ID. Idempotent."""
        key = db.session.get(ApiKey, key_id)
        if not key:
            raise ValueError(f"API-Key {key_id} nicht gefunden.")
        if key.revoked_at is not None:
            return  # idempotent
        key.revoked_at = get_utc_now()
        key.revoked_by_worker_id = revoked_by_worker_id
        key.is_active = False
        db.session.commit()

    @staticmethod
    def check_ip(key: ApiKey, source_ip: str) -> None:
        """Validate source_ip against key's allowlist. No-op if list empty."""
        if not key.ip_ranges:
            return
        try:
            ip = ipaddress.ip_address(source_ip)
        except (ValueError, TypeError):
            raise IpNotAllowed()
        for entry in key.ip_ranges:
            try:
                if ip in ipaddress.ip_network(entry.cidr, strict=False):
                    return
            except ValueError:
                continue  # skip malformed CIDR
        raise IpNotAllowed()

    @staticmethod
    @db_transaction
    def add_ip_range(
        key_id: int,
        cidr: str,
        note: Optional[str],
        created_by_worker_id: int,
    ) -> ApiKeyIpRange:
        """Add a CIDR allowlist entry to an API key."""
        try:
            ipaddress.ip_network(cidr, strict=False)
        except ValueError as exc:
            raise ValueError(f"Ungültiger CIDR-Ausdruck: {cidr}") from exc
        entry = ApiKeyIpRange(
            api_key_id=key_id,
            cidr=cidr,
            note=note,
            created_by_worker_id=created_by_worker_id,
        )
        db.session.add(entry)
        db.session.commit()
        return entry

    @staticmethod
    @db_transaction
    def remove_ip_range(range_id: int) -> None:
        """Remove a CIDR allowlist entry by ID."""
        entry = db.session.get(ApiKeyIpRange, range_id)
        if not entry:
            raise ValueError(f"IP-Range {range_id} nicht gefunden.")
        db.session.delete(entry)
        db.session.commit()

    @staticmethod
    @db_transaction
    def mark_used(key: ApiKey, source_ip: str) -> None:
        """Update last_used_at/last_used_ip, throttled to once per 60s."""
        now = get_utc_now()
        if key.last_used_at is not None:
            if (now - key.last_used_at) < timedelta(seconds=60):
                return
        key.last_used_at = now
        key.last_used_ip = source_ip
        db.session.commit()

    @staticmethod
    @db_transaction
    def log_audit(
        *,
        api_key: Optional[ApiKey],
        key_prefix: Optional[str],
        source_ip: str,
        method: str,
        path: str,
        status_code: int,
        latency_ms: int,
        outcome: str,
        request_id: str,
        external_ref: Optional[str] = None,
        assignment_method: Optional[str] = None,
        error_detail: Optional[str] = None,
    ) -> None:
        """Write a structured audit log entry."""
        entry = ApiAuditLog(
            api_key_id=api_key.id if api_key else None,
            key_prefix=key_prefix,
            source_ip=source_ip[:45],
            method=method,
            path=path[:255],
            status_code=status_code,
            latency_ms=latency_ms,
            outcome=outcome,
            external_ref=external_ref,
            assignment_method=assignment_method,
            request_id=request_id,
            error_detail=(error_detail or None),
        )
        db.session.add(entry)
        db.session.commit()
