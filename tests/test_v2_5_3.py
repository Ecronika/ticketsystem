
import pytest
import sys
import os

# Add parent directory to path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from azubi_werkzeug.models import CheckType

def test_check_type_values():
    """Verify CheckType enum values."""
    assert CheckType.CHECK == 'check'
    assert CheckType.ISSUE == 'issue'
    assert CheckType.RETURN == 'return'
    assert CheckType.EXCHANGE == 'exchange'

def test_routes_compilation():
    """Verify routes.py compiles and imports successfully (fixing IndentationError)."""
    try:
        from azubi_werkzeug.routes import main_bp
        assert main_bp is not None
    except IndentationError:
        pytest.fail("routes.py still has IndentationError")
    except ImportError as e:
        pytest.fail(f"ImportError: {e}")
    except Exception as e:
        pytest.fail(f"Unexpected error importing routes: {e}")
