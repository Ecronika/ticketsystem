"""Tests for configurable report scheduling."""

import pytest
from datetime import date
from unittest.mock import patch, MagicMock
from datetime import datetime
from zoneinfo import ZoneInfo

from models import CustomHoliday
from extensions import db
from services.scheduler_service import _is_report_day


class TestCustomHolidayModel:
    """CustomHoliday CRUD tests."""

    def test_create_custom_holiday(self, app, db_session):
        """Custom holiday can be created and retrieved."""
        h = CustomHoliday(date=date(2026, 12, 24), label="Betriebsferien")
        db_session.add(h)
        db_session.commit()

        result = CustomHoliday.query.filter_by(date=date(2026, 12, 24)).first()
        assert result is not None
        assert result.label == "Betriebsferien"

    def test_custom_holiday_unique_date(self, app, db_session):
        """Duplicate dates are rejected."""
        h1 = CustomHoliday(date=date(2026, 12, 31), label="Silvester")
        db_session.add(h1)
        db_session.commit()

        h2 = CustomHoliday(date=date(2026, 12, 31), label="Duplikat")
        db_session.add(h2)
        with pytest.raises(Exception):
            db_session.commit()
        db_session.rollback()

    def test_delete_custom_holiday(self, app, db_session):
        """Custom holiday can be deleted."""
        h = CustomHoliday(date=date(2026, 12, 25), label="Weihnachten")
        db_session.add(h)
        db_session.commit()

        db_session.delete(h)
        db_session.commit()

        assert CustomHoliday.query.filter_by(date=date(2026, 12, 25)).first() is None


class TestReportDayGuard:
    """Tests for _is_report_day() guard function."""

    def test_weekday_allowed(self, app, db_session):
        """Monday (isoweekday=1) is allowed with default Mo-Fr config."""
        from models import SystemSettings
        SystemSettings.set_setting("report_weekdays", "1,2,3,4,5")
        monday = date(2026, 4, 20)
        assert _is_report_day(monday) is True

    def test_weekend_blocked(self, app, db_session):
        """Saturday (isoweekday=6) is blocked with default Mo-Fr config."""
        from models import SystemSettings
        SystemSettings.set_setting("report_weekdays", "1,2,3,4,5")
        saturday = date(2026, 4, 25)
        assert _is_report_day(saturday) is False

    def test_federal_holiday_blocked(self, app, db_session):
        """Neujahr is blocked when federal state is set."""
        from models import SystemSettings
        SystemSettings.set_setting("report_weekdays", "1,2,3,4,5")
        SystemSettings.set_setting("report_federal_state", "NW")
        neujahr = date(2026, 1, 1)
        assert _is_report_day(neujahr) is False

    def test_no_federal_state_no_holiday_check(self, app, db_session):
        """Without federal state configured, holidays are not checked."""
        from models import SystemSettings
        SystemSettings.set_setting("report_weekdays", "1,2,3,4,5")
        setting = SystemSettings.query.filter_by(key="report_federal_state").first()
        if setting:
            db_session.delete(setting)
            db_session.commit()
        neujahr = date(2026, 1, 1)
        assert _is_report_day(neujahr) is True

    def test_custom_holiday_blocked(self, app, db_session):
        """Custom holidays block report sending."""
        from models import SystemSettings
        SystemSettings.set_setting("report_weekdays", "1,2,3,4,5")
        h = CustomHoliday(date=date(2026, 6, 15), label="Betriebsferien")
        db_session.add(h)
        db_session.commit()
        assert _is_report_day(date(2026, 6, 15)) is False

    def test_no_weekdays_configured_uses_default(self, app, db_session):
        """Without config, defaults to Mo-Fr."""
        from models import SystemSettings
        setting = SystemSettings.query.filter_by(key="report_weekdays").first()
        if setting:
            db_session.delete(setting)
            db_session.commit()
        assert _is_report_day(date(2026, 4, 20)) is True
        assert _is_report_day(date(2026, 4, 25)) is False
