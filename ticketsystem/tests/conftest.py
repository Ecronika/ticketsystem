"""Test configuration and fixtures."""
# pylint: disable=redefined-outer-name
import pytest

from app import app as flask_app
from extensions import db as _db
from models import Ticket, SystemSettings


@pytest.fixture
def test_app():
    """Create a test application instance."""
    # Use the global app object
    flask_app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False
    })

    with flask_app.app_context():
        _db.create_all()

        # Seed basic data
        ticket = _db.session.get(Ticket, 1) or Ticket.query.first()
        if not ticket:
            ticket = Ticket(title="Test Ticket", description="Initial test ticket")
            _db.session.add(ticket)

        # Seed onboarding for tests
        if not SystemSettings.query.filter_by(key="onboarding_complete").first():
            _db.session.add(SystemSettings(key="onboarding_complete", value="true"))
        if not SystemSettings.query.filter_by(key="ticket_shortcuts").first():
            _db.session.add(SystemSettings(key="ticket_shortcuts", value="Prüfen,Bestellt,Erledigt,Rückruf"))

        _db.session.commit()

        yield flask_app

        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def db(test_app):
    """Return the database object."""
    return _db


@pytest.fixture
def client(test_app):
    """Create a test client."""
    return test_app.test_client()


@pytest.fixture
def runner(test_app):
    """Create a test CLI runner."""
    return test_app.test_cli_runner()


@pytest.fixture(autouse=True)
def _clear_dashboard_caches():
    """Verhindert, dass Cache-Einträge zwischen Tests bestehen bleiben."""
    from services.dashboard_service import _projects_cache, _workload_cache
    _projects_cache.clear()
    _workload_cache.clear()
    yield


# ---------------------------------------------------------------------------
# Compatibility aliases
#
# The original conftest exposes `test_app` and `db`. New tests (starting with
# the Public-API integration) use shorter names `app` and `db_session` that
# match the convention in the plan/spec documents. These aliases keep both
# conventions working without touching the 15+ existing tests.
# ---------------------------------------------------------------------------

@pytest.fixture
def app(test_app):
    """Alias for test_app to match newer test files."""
    return test_app


@pytest.fixture
def db_session(test_app, db):
    """Return the active db.session for direct use in tests."""
    return db.session


@pytest.fixture
def admin_worker(app, db_session):
    """Admin worker (is_admin=True)."""
    from werkzeug.security import generate_password_hash
    from models import Worker
    w = Worker(
        name="TestAdmin",
        pin_hash=generate_password_hash("7391"),
        is_admin=True, is_active=True, role="admin",
        needs_pin_change=False,
    )
    db_session.add(w)
    db_session.commit()
    return w


@pytest.fixture
def default_assignee(app, db_session):
    """Default-assignee worker."""
    from werkzeug.security import generate_password_hash
    from models import Worker
    w = Worker(
        name="Rezeption",
        pin_hash=generate_password_hash("8264"),
        is_active=True, role="worker",
        needs_pin_change=False,
    )
    db_session.add(w)
    db_session.commit()
    return w


@pytest.fixture
def petra_key(admin_worker, default_assignee):
    from services.api_key_service import ApiKeyService
    key, _ = ApiKeyService.create_key(
        name="HalloPetra Test",
        scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=1000,
        created_by_worker_id=admin_worker.id,
    )
    return key


@pytest.fixture
def petra_token(admin_worker, default_assignee):
    from services.api_key_service import ApiKeyService
    _, plaintext = ApiKeyService.create_key(
        name="HalloPetra Test Token",
        scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=1000,
        created_by_worker_id=admin_worker.id,
    )
    return plaintext


@pytest.fixture(autouse=True)
def _clear_api_rate_windows():
    """Prevent _rate_windows state leaking between tests.

    Imported lazily to avoid eager import of routes.api before tests need it.
    """
    try:
        from routes.api._decorators import _rate_windows, _rate_lock
    except ImportError:
        yield
        return
    with _rate_lock:
        _rate_windows.clear()
    yield
    with _rate_lock:
        _rate_windows.clear()
