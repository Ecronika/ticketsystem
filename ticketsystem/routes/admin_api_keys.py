"""Admin UI for API key management, IP allowlist, and audit log viewer."""

from __future__ import annotations

from collections import Counter
from typing import Any

from flask import flash, redirect, render_template, request, session, url_for
from werkzeug.wrappers import Response as WerkzeugResponse

from models import ApiAuditLog, ApiKey, ApiKeyIpRange, Worker
from routes.admin import admin_bp
from routes.auth import admin_required
from services.api_key_service import ApiKeyService


def _current_worker() -> Worker | None:
    """Return the currently logged-in worker from session."""
    from extensions import db

    wid = session.get("worker_id")
    if not wid:
        return None
    return db.session.get(Worker, wid)


def _summarise_ips(rows: Any) -> list[dict]:
    """Group source IPs from audit rows; return top-10 with count and last_seen."""
    counts: Counter = Counter(r.source_ip for r in rows)
    last_seen: dict = {}
    for r in rows:
        if r.source_ip not in last_seen:
            last_seen[r.source_ip] = r.timestamp
    result = []
    for ip, count in counts.most_common(10):
        result.append({"ip": ip, "count": count, "last_seen": last_seen[ip]})
    return result


# ------------------------------------------------------------------
# API key list
# ------------------------------------------------------------------

@admin_bp.route("/api-keys", methods=["GET"])
@admin_required
def _api_keys_list() -> str:
    """List all API keys ordered by creation date."""
    keys = ApiKey.query.order_by(ApiKey.created_at.desc()).all()
    return render_template("admin_api_keys_list.html", keys=keys)


# ------------------------------------------------------------------
# Create new API key
# ------------------------------------------------------------------

@admin_bp.route("/api-keys/new", methods=["GET", "POST"])
@admin_required
def _api_keys_new() -> str | WerkzeugResponse:
    """Create form + submit for a new API key."""
    workers = Worker.query.filter_by(is_active=True).order_by(Worker.name).all()
    if request.method == "POST":
        try:
            assignee_raw = request.form.get("default_assignee_id", "")
            assignee_id = int(assignee_raw) if assignee_raw else None
            key, plaintext = ApiKeyService.create_key(
                name=request.form["name"],
                scopes=request.form.getlist("scopes"),
                default_assignee_id=assignee_id,
                rate_limit_per_minute=int(request.form.get("rate_limit_per_minute", 60)),
                created_by_worker_id=_current_worker().id,
                expected_webhook_id=(request.form.get("expected_webhook_id") or None),
                create_confidential_tickets=bool(
                    request.form.get("create_confidential_tickets")
                ),
            )
            session["_just_created_token"] = plaintext
            return redirect(url_for("admin._api_keys_created", key_id=key.id))
        except (ValueError, TypeError) as exc:
            flash(str(exc), "danger")
    return render_template("admin_api_key_form.html", workers=workers, key=None)


# ------------------------------------------------------------------
# One-time token display (after create)
# ------------------------------------------------------------------

@admin_bp.route("/api-keys/<int:key_id>/created", methods=["GET"])
@admin_required
def _api_keys_created(key_id: int) -> str | WerkzeugResponse:
    """Display the plaintext token exactly once after key creation."""
    plaintext = session.pop("_just_created_token", None)
    if not plaintext:
        return redirect(url_for("admin._api_keys_list"))
    key = ApiKey.query.get_or_404(key_id)
    return render_template("admin_api_key_created.html", key=key, plaintext=plaintext)


# ------------------------------------------------------------------
# Edit / revoke API key
# ------------------------------------------------------------------

@admin_bp.route("/api-keys/<int:key_id>/edit", methods=["GET", "POST"])
@admin_required
def _api_keys_edit(key_id: int) -> str | WerkzeugResponse:
    """Edit key settings or revoke the key."""
    from extensions import db

    key = ApiKey.query.get_or_404(key_id)
    workers = Worker.query.filter_by(is_active=True).order_by(Worker.name).all()

    if request.method == "POST":
        action = request.form.get("action", "save")
        if action == "revoke":
            ApiKeyService.revoke_key(
                key.id, revoked_by_worker_id=_current_worker().id,
            )
            flash("Schlüssel widerrufen.", "success")
            return redirect(url_for("admin._api_keys_list"))

        # Save edits
        try:
            key.name = request.form["name"]
            key.rate_limit_per_minute = int(request.form.get("rate_limit_per_minute", 60))
            assignee_raw = request.form.get("default_assignee_id", "")
            key.default_assignee_worker_id = int(assignee_raw) if assignee_raw else None
            key.expected_webhook_id = request.form.get("expected_webhook_id") or None
            key.create_confidential_tickets = bool(
                request.form.get("create_confidential_tickets")
            )
            db.session.commit()
            flash("Änderungen gespeichert.", "success")
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        return redirect(url_for("admin._api_keys_edit", key_id=key.id))

    # Recent observed IPs from audit log
    recent_rows = (
        ApiAuditLog.query
        .filter_by(api_key_id=key.id)
        .with_entities(ApiAuditLog.source_ip, ApiAuditLog.timestamp)
        .order_by(ApiAuditLog.timestamp.desc())
        .limit(100)
        .all()
    )
    ip_summary = _summarise_ips(recent_rows)
    return render_template(
        "admin_api_key_form.html",
        key=key, workers=workers, recent_ips=ip_summary,
    )


# ------------------------------------------------------------------
# IP allowlist management
# ------------------------------------------------------------------

@admin_bp.route("/api-keys/<int:key_id>/ip-ranges", methods=["POST"])
@admin_required
def _api_keys_add_ip(key_id: int) -> WerkzeugResponse:
    """Add a CIDR range to the key's IP allowlist."""
    cidr = request.form.get("cidr", "").strip()
    note = request.form.get("note") or None
    try:
        ApiKeyService.add_ip_range(
            key_id=key_id, cidr=cidr, note=note,
            created_by_worker_id=_current_worker().id,
        )
        flash("IP-Range hinzugefügt.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("admin._api_keys_edit", key_id=key_id))


@admin_bp.route("/api-keys/ip-ranges/<int:range_id>/delete", methods=["POST"])
@admin_required
def _api_keys_remove_ip(range_id: int) -> WerkzeugResponse:
    """Remove a CIDR range from an API key's IP allowlist."""
    entry = ApiKeyIpRange.query.get_or_404(range_id)
    key_id = entry.api_key_id
    ApiKeyService.remove_ip_range(range_id)
    flash("IP-Range entfernt.", "success")
    return redirect(url_for("admin._api_keys_edit", key_id=key_id))


# ------------------------------------------------------------------
# Audit log viewer
# ------------------------------------------------------------------

@admin_bp.route("/api-audit-log", methods=["GET"])
@admin_required
def _api_audit_log() -> str:
    """View API audit log with optional filters and pagination."""
    outcome = request.args.get("outcome")
    key_id = request.args.get("key_id", type=int)
    page = request.args.get("page", 1, type=int)

    q = ApiAuditLog.query.order_by(ApiAuditLog.timestamp.desc())
    if outcome:
        q = q.filter_by(outcome=outcome)
    if key_id:
        q = q.filter_by(api_key_id=key_id)

    pagination = q.paginate(page=page, per_page=50, error_out=False)
    keys = ApiKey.query.order_by(ApiKey.name).all()
    return render_template(
        "admin_api_audit_log.html",
        pagination=pagination, keys=keys,
        selected_outcome=outcome, selected_key_id=key_id,
    )


# ------------------------------------------------------------------
# Static API documentation
# ------------------------------------------------------------------

@admin_bp.route("/api-docs", methods=["GET"])
@admin_required
def _api_docs() -> str:
    """Static API documentation page."""
    from flask import current_app

    api_base = current_app.config.get("API_PUBLIC_BASE_URL", "https://<your-domain>")
    return render_template("admin_api_docs.html", api_base=api_base)
