"""Tests for configurable report scheduling."""

import pytest
from datetime import date

from models import CustomHoliday
from extensions import db


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
