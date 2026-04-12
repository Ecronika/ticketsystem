from flask import Blueprint, jsonify


def register_routes(bp: Blueprint) -> None:
    @bp.route("/health", methods=["GET"])
    def _health():
        return jsonify({"status": "ok"}), 200
