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

# IPs from which forwarded-for headers (CF-Connecting-IP, X-Real-IP) are
# trusted. In our deployment, NGINX runs on the same host and proxies to
# Flask via the loopback interface; cloudflared likewise targets localhost.
# If a request arrives with a non-loopback peer, the Flask app is reachable
# directly — a misconfiguration — and any "forwarded" headers must be
# treated as attacker-controlled.
_TRUSTED_PROXY_PEERS = frozenset({"127.0.0.1", "::1"})

# ---------------------------------------------------------------------------
# Rate-limit storage (in-memory, per-process)
#
# DEPLOYMENT CONSTRAINT: This implementation assumes single-worker Flask
# (gunicorn --workers=1 or equivalent). With multiple workers each gets its
# own _rate_windows dict, so the effective limit becomes `limit * workers`.
# For the HA-Add-on single-worker case this is fine. If multi-worker deploy
# is ever needed, replace with a Redis-backed sliding window.
# ---------------------------------------------------------------------------

_rate_windows: dict[int, deque] = defaultdict(deque)
_rate_lock = Lock()

# Pre-auth IP-based rate limit (defense-in-depth vs. unauthenticated brute-force).
# Applied BEFORE @api_key_required so a spammer cannot flood the DB with
# authenticate() lookups. Separate storage from the per-key post-auth limit.
_ip_rate_windows: dict[str, deque] = defaultdict(deque)
_ip_rate_lock = Lock()
_PREAUTH_RATE_LIMIT_PER_MINUTE = 120  # 2 req/s sustained from one IP


def _client_ip() -> str:
    """Extract the true source IP, resistant to header spoofing.

    Trust model: CF-Connecting-IP / X-Real-IP are set by our own NGINX /
    cloudflared and are trustworthy ONLY if the direct peer
    (`request.remote_addr`) is a trusted proxy (loopback). If the app is
    ever reached directly from a non-loopback peer, we ignore the forwarded
    headers entirely to prevent IP-allowlist bypass via header spoofing.

    Returns the peer IP if the request did not come via a trusted proxy,
    otherwise the first value from CF-Connecting-IP / X-Real-IP (stripped
    of any proxy-chain commas).
    """
    peer = (request.remote_addr or "").strip()
    if peer not in _TRUSTED_PROXY_PEERS:
        # Direct (non-proxied) connection — headers are attacker-controlled.
        return peer
    raw = (
        request.headers.get(_CF_IP_HEADER)
        or request.headers.get(_REAL_IP_HEADER)
        or peer
    )
    # Split on comma for multi-hop headers; take first, strip whitespace
    return raw.split(",")[0].strip()


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


def api_preauth_rate_limit(view: Callable) -> Callable:
    """IP-based sliding-window rate limit BEFORE authentication.

    Defense-in-depth against unauthenticated brute-force / volume spam that
    would otherwise hit the DB via authenticate(). This complements (not
    replaces) any NGINX/Cloudflare-level rate-limiting at the infrastructure
    layer.

    Limit: _PREAUTH_RATE_LIMIT_PER_MINUTE per source IP per minute.
    """
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        ip = _client_ip() or "unknown"
        now = time.time()
        window_start = now - 60.0

        with _ip_rate_lock:
            q = _ip_rate_windows[ip]
            while q and q[0] < window_start:
                q.popleft()
            if len(q) >= _PREAUTH_RATE_LIMIT_PER_MINUTE:
                g.api_outcome = "rate_limited"
                retry_after = int(60 - (now - q[0])) + 1
                return jsonify({
                    "error": "rate_limited",
                    "retry_after": retry_after,
                }), 429
            q.append(now)

        return view(*args, **kwargs)
    return wrapper


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
