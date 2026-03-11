import urllib.request
import urllib.parse
from app import app
from models import SystemSettings
from werkzeug.security import generate_password_hash
from extensions import db

app.testing = True

with app.app_context():
    # Setup PIN to ensure login works
    SystemSettings.set_setting('admin_pin_hash', generate_password_hash('1234'))
    client = app.test_client()
    
    # Login
    resp = client.post('/login', data={'pin': '1234'})
    print("Login response:", resp.status_code)
    
    # Try adding Azubi via API without CSRF token
    resp = client.post('/api/azubi', data={'name': 'Test Azubi', 'lehrjahr': 1})
    print("API Response Code:", resp.status_code)
    try:
        print("API Response JSON:", resp.json)
    except Exception as e:
        print("Response was not JSON. Content snippet:")
        print(resp.data[:200].decode('utf-8'))
