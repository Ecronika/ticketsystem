
import sys
import os
from datetime import datetime, timezone

# Add the app directory to sys.path
sys.path.append(os.path.join(os.getcwd(), 'azubi_werkzeug'))

# Mocking Flask-Migrate or other things if needed, but let's try direct import
from azubi_werkzeug.app import app
from azubi_werkzeug.extensions import db
from azubi_werkzeug.models import Check, CheckType, Werkzeug, Azubi
from azubi_werkzeug.services import CheckService

def verify_session_grouping():
    with app.app_context():
        print("Testing group_checks_into_sessions logic...")
        
        # 1. Mock objects (not real DB records to avoid DB state issues)
        class MockAzubi:
            def __init__(self, name):
                self.name = name
                self.id = 1

        class MockWerkzeug:
            def __init__(self, name, price):
                self.name = name
                self.price = price
                self.id = 1
                self.material_category = "test"

        class MockCheck:
            def __init__(self, sid, azubi, werkzeug, ctype, bemerkung):
                self.session_id = sid
                self.azubi = azubi
                self.werkzeug = werkzeug
                self.check_type = ctype
                self.bemerkung = bemerkung
                self.datum = datetime.now(timezone.utc)
                self.azubi_id = azubi.id

        azubi = MockAzubi("Test Azubi")
        w1 = MockWerkzeug("Tool 1", 10.0)
        
        sid_check = "test_session_check"
        c1 = MockCheck(sid_check, azubi, w1, CheckType.CHECK.value, "Status: ok")
        
        sid_exchange = "test_session_exchange"
        c2 = MockCheck(sid_exchange, azubi, w1, CheckType.RETURN.value, "Austausch: Defekt (Kostenpflichtig)")
        c3 = MockCheck(sid_exchange, azubi, w1, CheckType.ISSUE.value, "Austausch (Neuteil) (Kostenpflichtig)")

        all_checks = [c1, c2, c3]
        
        # Test grouping
        sessions = CheckService.group_checks_into_sessions(all_checks)
        
        for s in sessions:
            print(f"Session: {s['session_id']}")
            print(f"  Type: {s['type']}")
            print(f"  Is Payable: {s['is_payable']}")
            print(f"  Price: {s['total_price']}")
            
            if s['session_id'] == sid_check:
                assert s['type'] == 'check'
                assert s['is_payable'] == False
                assert s['total_price'] == 0.0
            
            if s['session_id'] == sid_exchange:
                assert s['type'] == 'exchange'
                assert s['is_payable'] == True
                assert abs(s['total_price'] - 10.0) < 0.01

        print("Verification SUCCESSFUL!")

if __name__ == "__main__":
    verify_session_grouping()
