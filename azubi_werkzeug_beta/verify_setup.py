from app import app, setup_database
from extensions import db
from models import Azubi, Werkzeug
import sys


def verify_setup():
    print("Verifying Setup...")
    # Ensure DB is created
    with app.app_context():
        setup_database()

    client = app.test_client()

    # 1. Routes
    print("1. Checking Routes...")
    try:
        # Check /manage because it has forms with CSRF tokens
        resp = client.get('/manage')
        if resp.status_code == 200:
            print("OK: /manage (Management) loaded.")
        else:
            print(f"FAIL: /manage Failed with status: {resp.status_code}")
            # Print first 500 chars of response to see error
            print(f"Response: {resp.data[:500]}")
            sys.exit(1)

        # Check CSRF
        if b'csrf_token' in resp.data:
            print("OK: CSRF Token present in /manage forms.")
        else:
            print("WARN: CSRF Token MISSING in /manage forms.")

    except Exception as e:
        print(f"ERROR: Exception checking routes: {e}")
        sys.exit(1)

    print("Setup Verification Passed.")


if __name__ == '__main__':
    verify_setup()
