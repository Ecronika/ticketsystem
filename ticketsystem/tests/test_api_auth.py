"""Tests for API authentication decorators.

Test blueprints used by these tests (test_api_auth, test_scope, test_rl) are
registered in conftest.py at module scope so they are available before any
HTTP request triggers Flask's "first request handled" flag.
"""

from services.api_key_service import ApiKeyService


def test_missing_header_returns_401(app, client, db_session):
    r = client.get("/test_api_v1/protected")
    assert r.status_code == 401
    assert r.get_json() == {"error": "unauthorized"}


def test_wrong_bearer_returns_401(app, client, db_session):
    r = client.get(
        "/test_api_v1/protected",
        headers={"Authorization": "Bearer tsk_" + "x" * 48},
    )
    assert r.status_code == 401
    assert r.get_json() == {"error": "unauthorized"}


def test_wrong_scheme_returns_401(app, client, db_session, admin_worker, default_assignee):
    key, plaintext = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_worker.id,
    )
    r = client.get(
        "/test_api_v1/protected",
        headers={"Authorization": f"Basic {plaintext}"},
    )
    assert r.status_code == 401


def test_valid_token_returns_200(app, client, db_session, admin_worker, default_assignee):
    key, plaintext = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_worker.id,
    )
    r = client.get(
        "/test_api_v1/protected",
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert r.status_code == 200
    assert r.get_json()["key_id"] == key.id


def test_scope_denied_returns_403(app, client, db_session, admin_worker, default_assignee):
    _, plaintext = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],  # fehlt admin:tickets
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_worker.id,
    )
    r = client.get(
        "/test_scope_v1/admin_only",
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert r.status_code == 403
    assert r.get_json() == {"error": "forbidden"}


def test_rate_limit_per_key(app, client, db_session, admin_worker, default_assignee):
    _, plaintext = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=3,  # niedrig für Test
        created_by_worker_id=admin_worker.id,
    )
    hdr = {"Authorization": f"Bearer {plaintext}"}
    assert client.get("/test_rl_v1/rl", headers=hdr).status_code == 200
    assert client.get("/test_rl_v1/rl", headers=hdr).status_code == 200
    assert client.get("/test_rl_v1/rl", headers=hdr).status_code == 200
    r = client.get("/test_rl_v1/rl", headers=hdr)
    assert r.status_code == 429
    body = r.get_json()
    assert body["error"] == "rate_limited"


def test_audit_log_written_on_auth_failure(app, client, db_session):
    from models import ApiAuditLog
    count_before = ApiAuditLog.query.count()
    # POST to /api/v1/webhook/calls (placeholder, @api_key_required) without auth
    # → 401; api_bp.after_request fires and writes audit log entry
    r = client.post("/api/v1/webhook/calls", json={"webhook_id": "x", "data": {}})
    assert r.status_code == 401
    assert r.get_json() == {"error": "unauthorized"}
    # Audit log must have been written by _write_audit_log after_request hook
    assert ApiAuditLog.query.count() == count_before + 1
    last = ApiAuditLog.query.order_by(ApiAuditLog.id.desc()).first()
    assert last.outcome == "auth_failed"
    assert last.status_code == 401
