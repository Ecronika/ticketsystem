"""WebPush / VAPID service.

Manages VAPID key generation, subscription storage and push delivery.
Requires ``pywebpush`` (added to requirements.txt).
"""

import logging
from typing import Optional

from flask import current_app

from extensions import db
from models import PushSubscription, SystemSettings, Worker

_logger = logging.getLogger(__name__)

_VAPID_PRIVATE_KEY = "vapid_private_key"
_VAPID_PUBLIC_KEY = "vapid_public_key"


# ---------------------------------------------------------------------------
# VAPID key management
# ---------------------------------------------------------------------------

def get_or_create_vapid_keys() -> tuple[str, str]:
    """Return (private_key_pem, public_key_urlsafe_b64), generating on first call."""
    priv = SystemSettings.get_setting(_VAPID_PRIVATE_KEY)
    pub = SystemSettings.get_setting(_VAPID_PUBLIC_KEY)
    if priv and pub:
        return priv, pub

    try:
        from py_vapid import Vapid
        vapid = Vapid()
        vapid.generate_keys()
        priv = vapid.private_key_pem.decode() if isinstance(vapid.private_key_pem, bytes) else vapid.private_key_pem
        pub = vapid.public_key_urlsafe_base64
        SystemSettings.set_setting(_VAPID_PRIVATE_KEY, priv)
        SystemSettings.set_setting(_VAPID_PUBLIC_KEY, pub)
        _logger.info("VAPID keys generated and stored.")
        return priv, pub
    except Exception as exc:
        _logger.error("Failed to generate VAPID keys: %s", exc)
        raise


def get_vapid_public_key() -> Optional[str]:
    """Return the stored VAPID public key, or None if not yet generated."""
    return SystemSettings.get_setting(_VAPID_PUBLIC_KEY)


# ---------------------------------------------------------------------------
# Subscription management
# ---------------------------------------------------------------------------

def save_subscription(worker_id: int, endpoint: str, p256dh: str, auth: str) -> None:
    """Upsert a WebPush subscription for *worker_id*."""
    existing = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if existing:
        existing.worker_id = worker_id
        existing.p256dh = p256dh
        existing.auth = auth
    else:
        db.session.add(PushSubscription(
            worker_id=worker_id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
        ))
    db.session.commit()


def delete_subscription(endpoint: str) -> None:
    """Remove a push subscription by endpoint URL."""
    PushSubscription.query.filter_by(endpoint=endpoint).delete()
    db.session.commit()


# ---------------------------------------------------------------------------
# Sending push notifications
# ---------------------------------------------------------------------------

def send_push_to_worker(worker_id: int, title: str, body: str, url: str = "/") -> None:
    """Send a WebPush notification to all subscriptions of *worker_id*."""
    worker = db.session.get(Worker, worker_id)
    if worker and not worker.push_notifications_enabled:
        return

    subscriptions = PushSubscription.query.filter_by(worker_id=worker_id).all()
    if not subscriptions:
        return

    try:
        priv, _ = get_or_create_vapid_keys()
        _do_send(subscriptions, priv, title, body, url)
    except Exception as exc:
        _logger.warning("WebPush send failed for worker %s: %s", worker_id, exc)


def _do_send(
    subscriptions: list,
    private_key_pem: str,
    title: str,
    body: str,
    url: str,
) -> None:
    import json
    try:
        from webpush import WebPusher
    except ImportError:
        try:
            from pywebpush import webpush, WebPushException
        except ImportError:
            _logger.warning("pywebpush not installed — WebPush disabled.")
            return

    vapid_claims = {"sub": "mailto:admin@ticketsystem.local"}
    payload = json.dumps({"title": title, "body": body, "url": url})

    dead_endpoints: list[str] = []
    for sub in subscriptions:
        try:
            webpush(
                subscription_info=sub.as_subscription_info(),
                data=payload,
                vapid_private_key=private_key_pem,
                vapid_claims=vapid_claims,
            )
        except Exception as exc:
            # 410 Gone → subscription expired, clean up
            if "410" in str(exc) or "404" in str(exc):
                dead_endpoints.append(sub.endpoint)
            else:
                _logger.debug("Push failed for sub %s: %s", sub.id, exc)

    for ep in dead_endpoints:
        PushSubscription.query.filter_by(endpoint=ep).delete()
    if dead_endpoints:
        db.session.commit()
