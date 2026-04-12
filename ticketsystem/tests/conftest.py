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


@pytest.fixture
def app(test_app):
    """Alias for test_app to match newer test files."""
    return test_app


@pytest.fixture
def db_session(test_app, db):
    """Return the active db.session for direct use in tests."""
    return db.session


@pytest.fixture
def admin_fixture(app, db_session):
    """Admin worker (is_admin=True). Replaces plan's 'admin_worker' fixture."""
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
def worker_fixture(app, db_session):
    """Default-assignee worker. Replaces plan's 'default_assignee' fixture."""
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
