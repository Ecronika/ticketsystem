"""Public webhook endpoint for HalloPetra call events."""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import Ticket
from routes.api._decorators import api_key_required, api_rate_limit, require_scope
from routes.api._schemas import HalloPetraWebhookPayload
from services.api_ticket_factory import ApiTicketFactory

_MAX_PAYLOAD_BYTES = 128 * 1024  # 128 KB; global MAX_CONTENT_LENGTH is 16 MB for file uploads


def register_routes(bp: Blueprint) -> None:

    @bp.route("/webhook/calls", methods=["POST"])
    @api_key_required
    @require_scope("write:tickets")
    @api_rate_limit
    def _webhook_calls():
        # Enforce per-endpoint payload size limit (128 KB).
        # The global MAX_CONTENT_LENGTH is 16 MB (for file uploads on main_bp).
        if request.content_length is not None and request.content_length > _MAX_PAYLOAD_BYTES:
            g.api_outcome = "payload_too_large"
            return jsonify({"error": "payload_too_large"}), 413

        if not request.is_json:
            g.api_outcome = "unsupported_media_type"
            return jsonify({"error": "unsupported_media_type"}), 415

        try:
            raw = request.get_json(force=False, silent=False)
        except Exception:
            g.api_outcome = "validation_failed"
            g.api_error_detail = "invalid JSON"
            return jsonify({"error": "validation_failed", "detail": "invalid JSON"}), 400

        if raw is None:
            g.api_outcome = "validation_failed"
            g.api_error_detail = "invalid JSON"
            return jsonify({"error": "validation_failed", "detail": "invalid JSON"}), 400

        if not isinstance(raw, dict):
            g.api_outcome = "validation_failed"
            g.api_error_detail = "payload must be a JSON object"
            return jsonify({
                "error": "validation_failed",
                "detail": "payload must be a JSON object",
            }), 400

        try:
            payload = HalloPetraWebhookPayload(**raw)
        except ValidationError as exc:
            g.api_outcome = "validation_failed"
            detail = str(exc)[:500]
            g.api_error_detail = detail
            return jsonify({
                "error": "validation_failed",
                "detail": detail,
            }), 400

        # Optional per-key webhook_id check
        if g.api_key.expected_webhook_id:
            if payload.webhook_id != g.api_key.expected_webhook_id:
                g.api_outcome = "validation_failed"
                detail = "webhook_id mismatch"
                g.api_error_detail = detail
                return jsonify({
                    "error": "validation_failed",
                    "detail": detail,
                }), 400

        # Idempotency: check for existing ticket with same external_call_id
        existing = Ticket.query.filter_by(external_call_id=payload.data.id).first()
        if existing is not None:
            g.api_outcome = "idempotent_replay"
            g.api_external_ref = payload.data.id
            return jsonify({
                "ticket_id": existing.id,
                "status": "duplicate",
            }), 200

        # Create ticket; handle concurrent race via IntegrityError fallback
        try:
            ticket, method = ApiTicketFactory.create_from_payload(g.api_key, payload)
        except IntegrityError:
            db.session.rollback()
            existing = Ticket.query.filter_by(external_call_id=payload.data.id).first()
            if existing:
                g.api_outcome = "idempotent_replay"
                g.api_external_ref = payload.data.id
                return jsonify({
                    "ticket_id": existing.id,
                    "status": "duplicate",
                }), 200
            raise

        g.api_outcome = "success"
        g.api_external_ref = payload.data.id
        g.api_assignment_method = method

        return jsonify({
            "ticket_id": ticket.id,
            "status": "created",
        }), 201
