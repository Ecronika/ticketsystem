"""
Unit tests for CheckService.
"""
from datetime import datetime
import pytest
from services import CheckService
from models import Check, CheckType, Azubi, Werkzeug


def test_check_submission_success(test_app):
    """Test successful check submission"""
    with test_app.test_request_context():
        # Setup data
        azubi = Azubi.query.first()
        tool = Werkzeug.query.first()

        sig = (
            "data:image/png;base64,iVBORw0KGgoAAAANSUh"
            "EUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
            "+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        form_data = {
            f'tool_{tool.id}': 'ok',
            'signature_azubi_data': sig,
            'signature_examiner_data': sig}

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
    with test_app.test_request_context():
        azubi = Azubi.query.first()
        tool = Werkzeug.query.first()

        custom_date = datetime(2023, 1, 1, 12, 0)

        sig = (
            "data:image/png;base64,iVBORw0KGgoAAAANSUh"
            "EUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
            "+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        form_data = {
            'signature_azubi_data': sig,
            'signature_examiner_data': sig
        }

        result = CheckService.process_check_submission(
            azubi_id=azubi.id,
            examiner_name="Test Examiner",
            tool_ids=[tool.id],
            form_data=form_data,
            check_date=custom_date,
            check_type=CheckType.CHECK
        )
        assert result['success'] is True

        check = Check.query.first()
        assert check.datum == custom_date


def test_exchange_enum_handling():
    """Verify CheckType Enum works correctly"""
    assert CheckType.ISSUE.value == 'issue'
    assert CheckType.RETURN.value == 'return'
    assert CheckType.EXCHANGE.value == 'exchange'


def test_check_submission_missing_azubi(test_app):
    """Test submission with invalid Azubi ID"""
    with test_app.test_request_context():
        tool = Werkzeug.query.first()

        sig = (
            "data:image/png;base64,iVBORw0KGgoAAAANSUh"
            "EUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
            "+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        with pytest.raises(ValueError, match="Azubi mit ID 99999 nicht gefunden"):
            CheckService.process_check_submission(
                azubi_id=99999,
                examiner_name="Test Examiner",
                tool_ids=[tool.id],
                form_data={'tool_' + str(tool.id): 'ok', 'signature_azubi_data': sig, 'signature_examiner_data': sig}
            )


def test_check_submission_invalid_tool(test_app):
    """Test submission with invalid Tool ID"""
    with test_app.test_request_context():
        azubi = Azubi.query.first()

        sig = (
            "data:image/png;base64,iVBORw0KGgoAAAANSUh"
            "EUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
            "+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        result = CheckService.process_check_submission(
            azubi_id=azubi.id,
            examiner_name="Test Examiner",
            tool_ids=[99999],
            form_data={'signature_azubi_data': sig, 'signature_examiner_data': sig}
        )
        # Should return success but count 0?
        assert result['success'] is True
        assert result['count'] == 0
