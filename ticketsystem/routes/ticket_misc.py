"""Miscellaneous endpoints: notifications, push, theme, worker names."""

from flask import Blueprint, Response, current_app, jsonify, request, session

from extensions import db
from models import Notification, Worker
from routes.auth import worker_required
from services._helpers import api_endpoint, api_error, api_ok


# ------------------------------------------------------------------
# Notification APIs
# ------------------------------------------------------------------

@worker_required
def _api_get_notifications() -> Response:
    """Fetch recent notifications for the dropdown."""
    worker_id = session.get("worker_id")
    notifs = (
        Notification.query
        .filter_by(user_id=worker_id)
        .order_by(Notification.created_at.desc())
        .limit(15)
        .all()
    )
    return jsonify({
        "notifications": [
            {
                "id": n.id,
                "message": n.message,
                "link": n.link or "#",
                "is_read": n.is_read,
            }
            for n in notifs
        ],
        "unread_count": sum(1 for n in notifs if not n.is_read),
    })


@worker_required
def _api_read_notification(notif_id: int) -> tuple[Response, int] | Response:
    """Mark a single notification as read."""
    worker_id = session.get("worker_id")
    notif = db.session.get(Notification, notif_id)
    if notif and notif.user_id == worker_id:
        notif.is_read = True
        db.session.commit()
        return api_ok()
    return api_error("Not found", 404)


@worker_required
def _api_read_all_notifications() -> Response:
    """Mark all notifications for the current worker as read."""
    worker_id = session.get("worker_id")
    Notification.query.filter_by(
        user_id=worker_id, is_read=False,
    ).update({"is_read": True})
    db.session.commit()
    return api_ok()


# ------------------------------------------------------------------
# Theme preference
# ------------------------------------------------------------------

@worker_required
@api_endpoint
def _save_theme_api() -> Response:
    """Save the authenticated user's UI theme preference."""
    worker_id = session.get("worker_id")
    if not worker_id:
        return api_error("Nicht angemeldet.", 401)

    data = request.get_json(silent=True) or {}
    theme = data.get("theme", "").strip()
    if theme not in ("light", "dark", "hc", "auto"):
        return api_error("Ungültiges Theme.", 400)

    worker = db.session.get(Worker, worker_id)
    if worker:
        worker.ui_theme = theme
        db.session.commit()
    return api_ok()


# ------------------------------------------------------------------
# Push notifications
# ------------------------------------------------------------------

@worker_required
def _push_vapid_key_api() -> Response:
    """Return the VAPID public key for push subscription."""
    try:
        from services.push_service import get_vapid_public_key, get_or_create_vapid_keys
        pub = get_vapid_public_key()
        if not pub:
            _, pub = get_or_create_vapid_keys()
        return jsonify({"public_key": pub})
    except Exception as exc:
        current_app.logger.error("VAPID key retrieval error: %s", exc)
        return jsonify({"error": "Interner Serverfehler."}), 500


@worker_required
def _push_subscribe_api() -> Response:
    """Store a push subscription for the authenticated worker."""
    data = request.get_json(silent=True) or {}
    endpoint = data.get("endpoint")
    keys = data.get("keys", {})
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")

    if not endpoint or not p256dh or not auth:
        return jsonify({"success": False, "error": "Unvollständige Subscription-Daten."}), 400

    worker_id = session.get("worker_id")
    if not worker_id:
        return jsonify({"success": False, "error": "Nicht authentifiziert."}), 401

    worker = db.session.get(Worker, worker_id)
    if worker and not worker.push_notifications_enabled:
        return jsonify({"success": False, "error": "Push-Benachrichtigungen sind deaktiviert."}), 403

    try:
        from services.push_service import save_subscription
        save_subscription(worker_id, endpoint, p256dh, auth)
        return jsonify({"success": True})
    except Exception as exc:
        current_app.logger.error("Push subscribe error: %s", exc)
        return jsonify({"success": False, "error": "Interner Serverfehler."}), 500


@worker_required
def _push_unsubscribe_api() -> Response:
    """Remove a push subscription."""
    data = request.get_json(silent=True) or {}
    endpoint = data.get("endpoint")
    if not endpoint:
        return jsonify({"success": False, "error": "Kein Endpoint angegeben."}), 400
    try:
        from services.push_service import delete_subscription
        delete_subscription(endpoint)
        return jsonify({"success": True})
    except Exception as exc:
        current_app.logger.error("Push unsubscribe error: %s", exc)
        return jsonify({"success": False, "error": "Interner Serverfehler."}), 500


# ------------------------------------------------------------------
# Worker mention autocomplete
# ------------------------------------------------------------------

@worker_required
def _worker_mention_names_api() -> Response:
    """Return active worker names for @mention autocomplete."""
    workers = Worker.query.filter_by(is_active=True).order_by(Worker.name).all()
    return jsonify({"names": [w.name for w in workers]})


def register_routes(bp: Blueprint) -> None:
    """Register miscellaneous routes."""
    bp.add_url_rule(
        "/api/notifications", "get_notifications",
        view_func=_api_get_notifications, methods=["GET"],
    )
    bp.add_url_rule(
        "/api/notifications/<int:notif_id>/read", "read_notification",
        view_func=_api_read_notification, methods=["POST"],
    )
    bp.add_url_rule(
        "/api/notifications/read_all", "read_all_notifications",
        view_func=_api_read_all_notifications, methods=["POST"],
    )
    bp.add_url_rule(
        "/api/user/theme", "save_theme_api",
        view_func=_save_theme_api, methods=["POST"],
    )
    bp.add_url_rule(
        "/api/workers/mention-names", "worker_mention_names",
        view_func=_worker_mention_names_api,
    )
    bp.add_url_rule(
        "/api/push/vapid-key", "push_vapid_key",
        view_func=_push_vapid_key_api,
    )
    bp.add_url_rule(
        "/api/push/subscribe", "push_subscribe",
        view_func=_push_subscribe_api, methods=["POST"],
    )
    bp.add_url_rule(
        "/api/push/unsubscribe", "push_unsubscribe",
        view_func=_push_unsubscribe_api, methods=["POST"],
    )
