"""UI/UX regression tests — assert template markers."""
from models import Worker


def _login(client, worker_name="Schmidt", pin="7391"):
    """Helper to log in; tests that need an authenticated view use this."""
    return client.post("/login", data={"worker_name": worker_name, "pin": pin},
                       follow_redirects=False)


def test_dashboard_has_no_dead_reload_hint(client, db):
    """Regression: #reloadHint div was removed from index.html (dashboard)."""
    # Create a real worker so validate_session() doesn't kill the session.
    worker = Worker(
        name="UITestWorker",
        pin_hash="x",
        role="admin",
        is_admin=True,
        needs_pin_change=False,
    )
    db.session.add(worker)
    db.session.commit()

    with client.session_transaction() as sess:
        sess["worker_id"] = worker.id
        sess["worker_name"] = worker.name
        sess["role"] = "admin"
        sess["is_admin"] = True

    resp = client.get("/")
    assert b'id="reloadHint"' not in resp.data


def test_login_page_has_no_happy_talk(client):
    resp = client.get("/login")
    assert b"Shopfloor" not in resp.data
    assert b"Echtzeit verfolgen" not in resp.data
    # CTA is shortened
    assert b"Jetzt Einloggen" not in resp.data


def test_new_ticket_has_no_redundant_subheading(client):
    resp = client.get("/ticket/new")
    # Subheading duplicated the H2; it must be gone.
    assert b"Erstellen Sie ein neues Ticket" not in resp.data


def test_mobile_new_ticket_cta_is_unambiguous(client):
    resp = client.get("/login")
    # 'Melden' alone is ambiguous; the short mobile label should be 'Neu'.
    # The full desktop label stays 'Neues Ticket'.
    assert b'>Melden<' not in resp.data
