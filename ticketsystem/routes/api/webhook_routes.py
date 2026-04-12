"""Public webhook endpoint for HalloPetra call events."""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import Ticket
from routes.api._decorators import (
    api_key_required,
    api_preauth_rate_limit,
    api_rate_limit,
    require_scope,
)
from routes.api._schemas import HalloPetraWebhookPayload
from services.api_ticket_factory import ApiTicketFactory

_MAX_PAYLOAD_BYTES = 128 * 1024  # 128 KB; global MAX_CONTENT_LENGTH is 16 MB for file uploads


def register_routes(bp: Blueprint) -> None:

    @bp.route("/webhook/calls", methods=["POST"])
    @api_preauth_rate_limit
    @api_key_required
    @require_scope("write:tickets")
    @api_rate_limit
    def _webhook_calls():
        # Enforce per-endpoint payload size limit (128 KB).
        # The global MAX_CONTENT_LENGTH is 16 MB (for file uploads on main_bp).
        #
        # Two-step check:
        #   1. Require a Content-Length header (rejects chunked transfer
        #      encoding that would otherwise bypass the 128 KB limit and
        #      fall through to the 16 MB global cap — potential DoS vector).
        #   2. Enforce the 128 KB cap against the declared length.
        # Step (2) also gets enforced by Flask once get_json reads the body;
        # doing it up-front short-circuits oversized requests without parsing.
        if request.content_length is None:
            g.api_outcome = "length_required"
            return jsonify({"error": "length_required"}), 411
        if request.content_length > _MAX_PAYLOAD_BYTES:
            g.api_outcome = "payload_too_large"
            return jsonify({"error": "payload_too_large"}), 413

        if not request.is_json:
            g.api_outcome = "unsupported_media_type"
            return jsonify({"error": "unsupported_media_type"}), 415

        # Detail strings are stored in g.api_error_detail for audit-log use
        # only — never returned in the response body. This avoids leaking
        # exception text / payload fragments to external callers (CodeQL:
        # py/stack-trace-exposure). Operators correlate incidents via
        # request_id → api_audit_log.error_detail.
        def _validation_fail(detail: str, status: int = 400):
            g.api_outcome = "validation_failed"
            g.api_error_detail = detail
            return jsonify({
                "error": "validation_failed",
                "request_id": getattr(g, "api_request_id", "unknown"),
            }), status

        try:
            raw = request.get_json(force=False, silent=False)
        except Exception:
            return _validation_fail("invalid JSON")

        if raw is None:
            return _validation_fail("invalid JSON")

        if not isinstance(raw, dict):
            return _validation_fail("payload must be a JSON object")

        try:
            payload = HalloPetraWebhookPayload(**raw)
        except ValidationError as exc:
            return _validation_fail(str(exc)[:500])

        # Optional per-key webhook_id check
        if g.api_key.expected_webhook_id:
            if payload.webhook_id != g.api_key.expected_webhook_id:
                return _validation_fail("webhook_id mismatch")

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
