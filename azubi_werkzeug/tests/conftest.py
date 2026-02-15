import pytest
import sys
import os

# Add beta folder to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app as flask_app
from extensions import db
from models import Azubi, Werkzeug

@pytest.fixture
def test_app():
    # Use the global app object
    flask_app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False
    })
    
    with flask_app.app_context():
        db.create_all()
        
        # Seed basic data
        azubi = Azubi.query.first() # Was created in verify_setup.py or earlier? No, seed here
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
    return test_app.test_client()

@pytest.fixture
def runner(test_app):
    return test_app.test_cli_runner()
