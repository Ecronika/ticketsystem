import pytest
from services import CheckService
from models import Check, CheckType, Azubi, Werkzeug
from datetime import datetime

def test_check_submission_success(test_app):
    """Test successful check submission"""
    with test_app.app_context():
        # Setup data
        azubi = Azubi.query.first()
        tool = Werkzeug.query.first()
        
        form_data = {
            f'tool_{tool.id}': 'ok',
            'signature_azubi_data': "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
            'signature_examiner_data': "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        }
        
        result = CheckService.process_check_submission(
            azubi_id=azubi.id,
            examiner_name="Test Examiner",
            tool_ids=[tool.id],
            form_data=form_data,
            check_date=datetime.now(),
            check_type=CheckType.CHECK
        )
        
        assert result['success'] is True
        assert result['count'] == 1
        
        # Verify DB
        check = Check.query.first()
        assert check.azubi_id == azubi.id
        assert check.werkzeug_id == tool.id
        assert check.check_type == CheckType.CHECK.value
        assert "Status: ok" in check.bemerkung

def test_check_date_override(test_app):
    """Test custom date handling"""
    with test_app.app_context():
        azubi = Azubi.query.first()
        tool = Werkzeug.query.first()
        
        custom_date = datetime(2023, 1, 1, 12, 0)
        
        result = CheckService.process_check_submission(
            azubi_id=azubi.id,
            examiner_name="Test Examiner",
            tool_ids=[tool.id],
            form_data={},
            check_date=custom_date
        )
        
        check = Check.query.first()
        assert check.datum == custom_date

def test_exchange_enum_handling(test_app):
    """Verify CheckType Enum works correctly"""
    assert CheckType.ISSUE == 'issue'
    assert CheckType.RETURN == 'return'
    assert CheckType.EXCHANGE == 'exchange'
