"""Test configuration and fixtures."""
# pylint: disable=redefined-outer-name
import os
import sys

# Add package folder to path before importing local modules
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest  # noqa: E402

from app import app as flask_app  # noqa: E402
from extensions import db as _db  # noqa: E402
from models import Ticket  # noqa: E402


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
