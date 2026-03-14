
from datetime import datetime, timezone
import enum

# Mocking the minimal environment needed for CheckService.group_checks_into_sessions
class CheckType(enum.Enum):
    CHECK = 'check'
    ISSUE = 'issue'
    RETURN = 'return'
    EXCHANGE = 'exchange'

def parse_check_type(val):
    if val == 'check': return CheckType.CHECK
    if val == 'issue': return CheckType.ISSUE
    if val == 'return': return CheckType.RETURN
    if val == 'exchange': return CheckType.EXCHANGE
    return CheckType.CHECK

class MockAzubi:
    def __init__(self, name):
        self.name = name
        self.id = 1

class MockWerkzeug:
    def __init__(self, price):
        self.price = price

class MockCheck:
    def __init__(self, sid, azubi, werkzeug, ctype, bemerkung):
        self.session_id = sid
        self.azubi = azubi
        self.werkzeug = werkzeug
        self.check_type = ctype
        self.bemerkung = bemerkung
        self.datum = datetime.now(timezone.utc)
        self.azubi_id = azubi.id

# We import the service but we need to mock its globals since we can't easily import from the app context
from azubi_werkzeug.services import CheckService

# Override the globals in services if necessary, or just test the logic
# Actually, the logic in services.py uses CheckType and parse_check_type which it imports.
# If I run it as a script, I might have issues with imports within services.py.

def test_logic():
    print("Testing isolated logic...")
    
    azubi = MockAzubi("Test")
    w_cheap = MockWerkzeug(10.0)
    w_none = MockWerkzeug(0.0)
    
    # 1. TEST: Simple Check
    c1 = MockCheck("sid1", azubi, w_cheap, "check", "Status: ok")
    res = CheckService.group_checks_into_sessions([c1])
    assert res[0]['type'] == 'check'
    assert res[0]['total_price'] == 0.0
    
    # 2. TEST: Payable Exchange
    # An exchange usually has a RETURN and an ISSUE in the same session
    c2 = MockCheck("sid2", azubi, w_cheap, "return", "Austausch: Defekt (Kostenpflichtig)")
    c3 = MockCheck("sid2", azubi, w_cheap, "issue", "Austausch (Neuteil) (Kostenpflichtig)")
    res = CheckService.group_checks_into_sessions([c2, c3])
    assert res[0]['type'] == 'exchange'
    assert res[0]['is_payable'] == True
    # Should only count the ISSUE part (10.0), not both (20.0)
    assert abs(res[0]['total_price'] - 10.0) < 0.01
    
    # 3. TEST: Multiple Issues (Payable)
    c4 = MockCheck("sid3", azubi, w_cheap, "issue", "(Kostenpflichtig)")
    c5 = MockCheck("sid3", azubi, w_cheap, "issue", "(Kostenpflichtig)")
    res = CheckService.group_checks_into_sessions([c4, c5])
    assert res[0]['type'] == 'issue'
    assert res[0]['total_price'] == 20.0

    print("LOGIC VERIFICATION SUCCESSFUL!")

if __name__ == "__main__":
    test_logic()
