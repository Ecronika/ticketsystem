import pytest
import sys
import os

# Add application root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'azubi_werkzeug')))

from app import app, db, setup_database

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False # Disable CSRF for easier testing
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
