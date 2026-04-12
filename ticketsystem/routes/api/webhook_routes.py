from flask import Blueprint, jsonify

from routes.api._decorators import api_key_required


def register_routes(bp: Blueprint) -> None:
    @bp.route("/webhook/calls", methods=["POST"])
    @api_key_required
    def _webhook_calls_placeholder():
        """Placeholder — vollständige Implementierung in Phase 4."""
        return jsonify({"error": "not_implemented"}), 501
