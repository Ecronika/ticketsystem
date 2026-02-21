"""Test configuration and fixtures."""
# pylint: disable=redefined-outer-name
import os
import sys
import pytest

from models import Azubi, Werkzeug
from extensions import db
from app import app as flask_app

# Add beta folder to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

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
        # Was created in verify_setup.py or earlier? No, seed here
        azubi = Azubi.query.first()
        if not azubi:
            azubi = Azubi(name="Test Azubi", lehrjahr=1)
            db.session.add(azubi)

        tool = Werkzeug.query.first()
        if not tool:
            tool = Werkzeug(name="Test Tool", material_category="standard")
            db.session.add(tool)

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
