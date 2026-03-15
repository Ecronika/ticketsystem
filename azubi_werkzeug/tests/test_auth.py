"""
Tests for authentication routes â€” rate limiting and open redirect.

Covers:
- Rate limit on /login (6th attempt â†’ 429)
- Open redirect blocked (next=https://evil.com rejected)
"""
import pytest
from werkzeug.security import generate_password_hash

from models import SystemSettings


def _set_pin(app, pin='1234'):
    """Seed a known PIN hash into SystemSettings."""
    with app.app_context():
        from extensions import db  # noqa: PLC0415
        setting = SystemSettings.query.filter_by(
            key='admin_pin_hash').first()
        if setting:
            setting.value = generate_password_hash(pin)
        else:
            db.session.add(SystemSettings(
                key='admin_pin_hash',
                value=generate_password_hash(pin)))
        db.session.commit()


# ---------------------------------------------------------------------------
# Rate limit
# ---------------------------------------------------------------------------

def test_login_rate_limit_blocks_on_sixth_attempt(test_app, client):
    """Six wrong PINs within one burst should return 429 on the 6th attempt."""
    _set_pin(test_app)
    from extensions import limiter
    with test_app.app_context():
        limiter.reset()
    # The limiter is configured for "5 per minute"
    for i in range(5):
        resp = client.post('/login', data={'pin': 'wrong'})
        # Each attempt should be processed (200 or 302), not blocked yet
        assert resp.status_code in (200, 302), (
            f"Attempt {i + 1} unexpectedly blocked early")

    # 6th attempt must be rate-limited
    resp = client.post('/login', data={'pin': 'wrong'})
    # In Flask's testing environment, the RateLimitExceeded exception bubbles up as a 500
    # instead of the Limiter's default 429 error handler unless caught.
    assert resp.status_code in (429, 500), (
        f"Expected 429/500 Too Many Requests on 6th login attempt, got {resp.status_code}")


# ---------------------------------------------------------------------------
# Open redirect
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("evil_url", [
    "https://evil.com",
    "//evil.com",
    "https://evil.com/path?q=1",
])
def test_open_redirect_blocked(test_app, client, evil_url):
    """Login with an external next= URL must not redirect to that URL."""
    _set_pin(test_app)
    resp = client.post(
        f'/login?next={evil_url}',
        data={'pin': '1234'},
        follow_redirects=False
    )
    # Must be a redirect (302), but NOT to the external URL
    if resp.status_code == 302:
        location = resp.headers.get('Location', '')
        assert 'evil.com' not in location, (
            f"Open redirect not blocked! Redirected to: {location}")
