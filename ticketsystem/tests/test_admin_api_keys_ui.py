"""UI route tests for admin API-key management."""


def _login_as_admin(client, admin_worker):
    with client.session_transaction() as s:
        s["worker_id"] = admin_worker.id
        s["is_admin"] = True
        s["role"] = "admin"
        s["worker_name"] = admin_worker.name


def _login_as_worker(client, default_assignee):
    with client.session_transaction() as s:
        s["worker_id"] = default_assignee.id
        s["is_admin"] = False
        s["role"] = "worker"
        s["worker_name"] = default_assignee.name


def test_list_requires_admin(client, default_assignee):
    _login_as_worker(client, default_assignee)
    r = client.get("/admin/api-keys")
    # Non-admin → redirect to login (admin_required redirects)
    assert r.status_code in (302, 403)


def test_list_as_admin_returns_200(client, admin_worker):
    _login_as_admin(client, admin_worker)
    r = client.get("/admin/api-keys")
    assert r.status_code == 200


def test_create_flow_shows_token_once(client, admin_worker, default_assignee):
    _login_as_admin(client, admin_worker)
    r = client.post("/admin/api-keys/new", data={
        "name": "Test",
        "scopes": ["write:tickets"],
        "default_assignee_id": str(default_assignee.id),
        "rate_limit_per_minute": "60",
        "create_confidential_tickets": "on",
    }, follow_redirects=False)
    assert r.status_code == 302
    r2 = client.get(r.headers["Location"])
    assert r2.status_code == 200
    assert b"tsk_" in r2.data
    # Reloading the same URL does NOT show the token again (session.pop consumed it)
    r3 = client.get(r.headers["Location"])
    assert b"tsk_" not in r3.data


def test_revoke_sets_status(client, admin_worker, default_assignee, db_session):
    _login_as_admin(client, admin_worker)
    from services.api_key_service import ApiKeyService

    key, _ = ApiKeyService.create_key(
        name="K",
        scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60,
        created_by_worker_id=admin_worker.id,
    )
    r = client.post(f"/admin/api-keys/{key.id}/edit", data={
        "action": "revoke",
    }, follow_redirects=False)
    assert r.status_code == 302
    db_session.refresh(key)
    assert key.revoked_at is not None
    assert key.is_active is False
