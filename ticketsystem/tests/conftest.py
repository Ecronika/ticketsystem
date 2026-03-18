"""Test configuration and fixtures."""
# pylint: disable=redefined-outer-name
import os
import sys

# Add package folder to path before importing local modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest  # noqa: E402

from app import app as flask_app  # noqa: E402
from extensions import db  # noqa: E402
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
        db.create_all()

        # Seed basic data
        ticket = db.session.get(Ticket, 1) or Ticket.query.first()
        if not ticket:
            ticket = Ticket(title="Test Ticket", description="Initial test ticket")
            db.session.add(ticket)

        db.session.commit()

        yield flask_app

        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(test_app):
    """Create a test client."""
    return test_app.test_client()


@pytest.fixture
def runner(test_app):
    """Create a test CLI runner."""
    return test_app.test_cli_runner()
