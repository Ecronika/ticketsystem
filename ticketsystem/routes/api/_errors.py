"""JSON-only error handlers for the public API blueprint."""

from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException

from exceptions import DomainError


def register_error_handlers(bp: Blueprint) -> None:

    @bp.errorhandler(DomainError)
    def _handle_domain(exc):
        g.api_outcome = "validation_failed"
        return jsonify({"error": "validation_failed", "detail": str(exc)}), exc.status_code

    @bp.errorhandler(ValueError)
    def _handle_value(exc):
        g.api_outcome = "validation_failed"
        return jsonify({"error": "validation_failed", "detail": str(exc)}), 400

    @bp.errorhandler(SQLAlchemyError)
    def _handle_sql(exc):
        g.api_outcome = "server_error"
        current_app.logger.exception("API SQL error")
        return jsonify({
            "error": "internal_error",
            "request_id": getattr(g, "api_request_id", "unknown"),
        }), 500

    @bp.errorhandler(413)
    def _handle_413(exc):
        g.api_outcome = "payload_too_large"
        return jsonify({"error": "payload_too_large"}), 413

    @bp.errorhandler(415)
    def _handle_415(exc):
        g.api_outcome = "unsupported_media_type"
        return jsonify({"error": "unsupported_media_type"}), 415

    @bp.errorhandler(HTTPException)
    def _handle_http(exc):
        g.api_outcome = "server_error"
        return jsonify({
            "error": "internal_error",
            "request_id": getattr(g, "api_request_id", "unknown"),
        }), exc.code or 500
