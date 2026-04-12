"""JSON-only error handlers for the public API blueprint."""

from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException

from exceptions import DomainError


_HTTP_ERROR_NAMES = {
    400: "bad_request",
    404: "not_found",
    405: "method_not_allowed",
    406: "not_acceptable",
    408: "timeout",
    409: "conflict",
    410: "gone",
    422: "unprocessable",
}


def register_error_handlers(bp: Blueprint) -> None:

    @bp.errorhandler(DomainError)
    def _handle_domain(exc):
        g.api_outcome = "validation_failed"
        detail = str(exc)[:500]
        g.api_error_detail = detail
        return jsonify({"error": "validation_failed", "detail": detail}), exc.status_code

    @bp.errorhandler(ValueError)
    def _handle_value(exc):
        g.api_outcome = "validation_failed"
        detail = str(exc)[:500]
        g.api_error_detail = detail
        return jsonify({"error": "validation_failed", "detail": detail}), 400

    @bp.errorhandler(SQLAlchemyError)
    def _handle_sql(exc):
        g.api_outcome = "server_error"
        g.api_error_detail = f"{type(exc).__name__}"  # type only, no PII from exc message
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
        code = exc.code or 500
        if code >= 500:
            g.api_outcome = "server_error"
            name = "internal_error"
        else:
            g.api_outcome = f"http_{code}"
            name = _HTTP_ERROR_NAMES.get(code, "client_error")
        body = {"error": name}
        if code >= 500:
            body["request_id"] = getattr(g, "api_request_id", "unknown")
        return jsonify(body), code
