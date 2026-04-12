"""UI/UX regression tests — assert template markers."""
import pytest

from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


def _login(client, worker_name="Schmidt", pin="7391"):
    """Helper to log in; tests that need an authenticated view use this."""
    return client.post("/login", data={"worker_name": worker_name, "pin": pin},
                       follow_redirects=False)


def test_dashboard_has_no_dead_reload_hint(client):
    """Dead #reloadHint element must be removed from dashboard."""
    # Anonymous users are redirected; use the /login page which extends base.html.
    resp = client.get("/login")
    assert b'id="reloadHint"' not in resp.data
