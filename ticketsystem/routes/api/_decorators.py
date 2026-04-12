"""Decorators for the public REST API."""

from __future__ import annotations

import functools
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Callable

from flask import g, jsonify, request

from exceptions import InvalidApiKey, IpNotAllowed
from services.api_key_service import ApiKeyService


_CF_IP_HEADER = "CF-Connecting-IP"
_REAL_IP_HEADER = "X-Real-IP"

_rate_windows: dict[int, deque] = defaultdict(deque)
_rate_lock = Lock()


def _client_ip() -> str:
    """Extract source IP, prefer Cloudflare header over X-Real-IP over remote_addr."""
    return (
        request.headers.get(_CF_IP_HEADER)
        or request.headers.get(_REAL_IP_HEADER)
        or request.remote_addr
        or ""
    )


def _extract_bearer_token() -> str | None:
    auth = request.headers.get("Authorization", "")
    if not auth:
        return None
    parts = auth.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def api_key_required(view: Callable) -> Callable:
    """Authenticate via Authorization: Bearer <token>.

    On success: g.api_key is set. On failure: 401/403 with generic body,
    outcome logged to api_audit_log (via @api_audit_log later; here we
    set g.api_outcome for deferred logging).
    """
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        g.api_request_start = time.perf_counter()
        g.api_outcome = "success"  # overwritten on failure

        token = _extract_bearer_token()
        try:
            key = ApiKeyService.authenticate(token)
        except InvalidApiKey:
            g.api_outcome = "auth_failed"
            g.api_key = None
            g.api_key_prefix = token[:12] if token else None
            return jsonify({"error": "unauthorized"}), 401

        try:
            ApiKeyService.check_ip(key, _client_ip())
        except IpNotAllowed:
            g.api_outcome = "ip_blocked"
            g.api_key = key
            g.api_key_prefix = key.key_prefix
            return jsonify({"error": "forbidden"}), 403

        g.api_key = key
        g.api_key_prefix = key.key_prefix
        ApiKeyService.mark_used(key, _client_ip())
        return view(*args, **kwargs)

    return wrapper


def require_scope(scope: str) -> Callable:
    def decorator(view: Callable) -> Callable:
        @functools.wraps(view)
        def wrapper(*args, **kwargs):
            key = getattr(g, "api_key", None)
            if key is None or not key.has_scope(scope):
                g.api_outcome = "scope_denied"
                return jsonify({"error": "forbidden"}), 403
            return view(*args, **kwargs)
        return wrapper
    return decorator


def api_rate_limit(view: Callable) -> Callable:
    """Token-bucket-ähnliches Sliding-Window pro api_key.id.

    Limit wird dynamisch aus g.api_key.rate_limit_per_minute gelesen.
    In-Memory; nur für Single-Worker-Deployment geeignet.
    """
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        key = g.api_key
        limit = key.rate_limit_per_minute
        now = time.time()
        window_start = now - 60.0

        with _rate_lock:
            q = _rate_windows[key.id]
            # Fenster bereinigen
            while q and q[0] < window_start:
                q.popleft()
            if len(q) >= limit:
                g.api_outcome = "rate_limited"
                retry_after = int(60 - (now - q[0])) + 1
                return jsonify({
                    "error": "rate_limited",
                    "retry_after": retry_after,
                }), 429
            q.append(now)

        return view(*args, **kwargs)

    return wrapper
