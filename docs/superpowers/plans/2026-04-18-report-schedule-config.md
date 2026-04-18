# Konfigurierbarer Berichtsversand — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admins sollen Versandzeit, Wochentage und Feiertage (per Bundesland + eigene freie Tage) des SLA-Eskalationsjobs konfigurieren können.

**Architecture:** Drei neue SystemSettings-Keys (`report_send_time`, `report_weekdays`, `report_federal_state`) plus eine neue Tabelle `custom_holiday` steuern den SLA-Job. APScheduler wird dynamisch rescheduled, ein Guard-Check am Job-Anfang prüft Wochentag und Feiertage. Ein täglicher Hilfsjob (00:05 UTC) justiert die UTC-Uhrzeit bei Sommer-/Winterzeitwechsel.

**Tech Stack:** Flask, SQLAlchemy, Alembic, APScheduler, `holidays` (Python-Paket), `zoneinfo` (Standardbibliothek)

**Spec:** `docs/superpowers/specs/2026-04-18-report-schedule-config-design.md`

---

## File Map

| Aktion | Datei | Verantwortung |
|--------|-------|---------------|
| Modify | `requirements.txt` | `holidays` hinzufuegen |
| Modify | `models.py` | `CustomHoliday` Model |
| Create | `migrations/versions/xxxx_add_custom_holiday.py` | Alembic-Migration |
| Modify | `services/scheduler_service.py` | Guard-Check, Hilfsjob, Rescheduling-Helper |
| Modify | `app.py:257-279` | Hilfsjob registrieren, SLA-Job mit DB-Uhrzeit |
| Modify | `routes/admin.py` | Settings-Route erweitern, Custom-Holiday CRUD |
| Modify | `templates/settings.html` | Neuer Abschnitt "Berichtsversand" |
| Create | `tests/test_report_schedule.py` | Tests fuer Guard, Rescheduling, Admin-UI |

---

### Task 1: Dependency hinzufuegen

**Files:**
- Modify: `ticketsystem/requirements.txt`

- [ ] **Step 1: `holidays` zu requirements.txt hinzufuegen**

In `requirements.txt` nach `argon2-cffi` eine neue Zeile einfuegen:

```
holidays>=0.65,<1.0
```

- [ ] **Step 2: Paket installieren und verifizieren**

Run: `cd ticketsystem && pip install -r requirements.txt`

Dann verifizieren:

```bash
python -c "import holidays; de = holidays.Germany(state='NW', years=2026); print(list(de.items())[:3])"
```

Expected: Liste mit 3 Feiertagen (z.B. Neujahr, Karfreitag, Ostermontag)

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "feat: add holidays package for federal state holiday support"
```

---

### Task 2: CustomHoliday Model

**Files:**
- Modify: `ticketsystem/models.py` (nach Zeile 57, nach `SystemSettings`)

- [ ] **Step 1: Test schreiben**

Datei `ticketsystem/tests/test_report_schedule.py` anlegen:

```python
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
```

- [ ] **Step 2: Test ausfuehren — muss fehlschlagen**

Run: `cd ticketsystem && python -m pytest tests/test_report_schedule.py::TestCustomHolidayModel -v`

Expected: FAIL — `ImportError: cannot import name 'CustomHoliday' from 'models'`

- [ ] **Step 3: Model implementieren**

In `ticketsystem/models.py` nach Zeile 57 (Ende von `SystemSettings`) einfuegen:

```python


class CustomHoliday(db.Model):
    """Additional company holidays beyond federal state holidays."""

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=True, nullable=False)
    label = db.Column(db.String(100), nullable=False)

    def __repr__(self) -> str:
        return f"<CustomHoliday {self.date} {self.label!r}>"
```

- [ ] **Step 4: Tests erneut ausfuehren — muessen bestehen**

Run: `cd ticketsystem && python -m pytest tests/test_report_schedule.py::TestCustomHolidayModel -v`

Expected: 3 passed

- [ ] **Step 5: Bestehende Tests pruefen — keine Regressionen**

Run: `cd ticketsystem && python -m pytest tests/ -v`

Expected: Alle bestehenden Tests bestehen weiterhin.

- [ ] **Step 6: Commit**

```bash
git add models.py tests/test_report_schedule.py
git commit -m "feat: add CustomHoliday model for company-specific holidays"
```

---

### Task 3: Alembic-Migration

**Files:**
- Create: `ticketsystem/migrations/versions/xxxx_add_custom_holiday.py`

- [ ] **Step 1: Migration manuell erstellen**

Neue Datei `ticketsystem/migrations/versions/a1b2c3d4e5f6_add_custom_holiday.py`:

```python
"""Add custom_holiday table for company-specific holidays.

Revision ID: a1b2c3d4e5f6
Revises: f2a3b4c5d6e7
Branch Labels: None
Depends On: None
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = 'f2a3b4c5d6e7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'custom_holiday',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('label', sa.String(100), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('date'),
    )


def downgrade():
    op.drop_table('custom_holiday')
```

- [ ] **Step 2: Migration ausfuehren und verifizieren**

Run: `cd ticketsystem && flask db upgrade`

Dann pruefen:

```bash
python -c "from app import app; from extensions import db; print('OK')"
```

Expected: `OK` ohne Fehler.

- [ ] **Step 3: Commit**

```bash
git add migrations/
git commit -m "feat: add Alembic migration for custom_holiday table"
```

---

### Task 4: Guard-Check und Hilfsfunktionen im Scheduler

**Files:**
- Modify: `ticketsystem/services/scheduler_service.py`
- Modify: `ticketsystem/tests/test_report_schedule.py`

- [ ] **Step 1: Tests fuer Guard-Check schreiben**

In `ticketsystem/tests/test_report_schedule.py` am Ende anfuegen:

```python
from unittest.mock import patch, MagicMock
from datetime import datetime
from zoneinfo import ZoneInfo
from services.scheduler_service import _is_report_day


class TestReportDayGuard:
    """Tests for _is_report_day() guard function."""

    def test_weekday_allowed(self, app, db_session):
        """Monday (isoweekday=1) is allowed with default Mo-Fr config."""
        from models import SystemSettings
        SystemSettings.set_setting("report_weekdays", "1,2,3,4,5")
        # Monday 2026-04-20
        monday = date(2026, 4, 20)
        assert _is_report_day(monday) is True

    def test_weekend_blocked(self, app, db_session):
        """Saturday (isoweekday=6) is blocked with default Mo-Fr config."""
        from models import SystemSettings
        SystemSettings.set_setting("report_weekdays", "1,2,3,4,5")
        # Saturday 2026-04-25
        saturday = date(2026, 4, 25)
        assert _is_report_day(saturday) is False

    def test_federal_holiday_blocked(self, app, db_session):
        """German Unity Day is blocked when federal state is set."""
        from models import SystemSettings
        SystemSettings.set_setting("report_weekdays", "1,2,3,4,5")
        SystemSettings.set_setting("report_federal_state", "NW")
        # 2026-10-03 is Tag der Deutschen Einheit (Saturday, but test the holiday check)
        # Use 2026-01-01 Neujahr (Thursday)
        neujahr = date(2026, 1, 1)
        assert _is_report_day(neujahr) is False

    def test_no_federal_state_no_holiday_check(self, app, db_session):
        """Without federal state configured, holidays are not checked."""
        from models import SystemSettings
        SystemSettings.set_setting("report_weekdays", "1,2,3,4,5")
        # Ensure no federal state is set
        setting = SystemSettings.query.filter_by(key="report_federal_state").first()
        if setting:
            db_session.delete(setting)
            db_session.commit()
        # 2026-01-01 is Thursday (weekday 4) — allowed if no holiday check
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
        setting = SystemSettings.query.filter_by(key="report_weekdays").first()
        if setting:
            db_session.delete(setting)
            db_session.commit()
        # Monday
        assert _is_report_day(date(2026, 4, 20)) is True
        # Saturday
        assert _is_report_day(date(2026, 4, 25)) is False
```

- [ ] **Step 2: Tests ausfuehren — muessen fehlschlagen**

Run: `cd ticketsystem && python -m pytest tests/test_report_schedule.py::TestReportDayGuard -v`

Expected: FAIL — `ImportError: cannot import name '_is_report_day'`

- [ ] **Step 3: Guard-Funktion und Hilfsfunktionen implementieren**

In `ticketsystem/services/scheduler_service.py`:

Am Anfang der Imports (nach Zeile 10) hinzufuegen:

```python
from zoneinfo import ZoneInfo

import holidays as holidays_lib
```

Nach Zeile 26 (`_ANTI_SPAM_HOURS = 23`) einfuegen:

```python

_DEFAULT_SEND_TIME = "07:00"
_DEFAULT_WEEKDAYS = "1,2,3,4,5"
_BERLIN_TZ = ZoneInfo("Europe/Berlin")

FEDERAL_STATES = {
    "BW": "Baden-Württemberg",
    "BY": "Bayern",
    "BE": "Berlin",
    "BB": "Brandenburg",
    "HB": "Bremen",
    "HH": "Hamburg",
    "HE": "Hessen",
    "MV": "Mecklenburg-Vorpommern",
    "NI": "Niedersachsen",
    "NW": "Nordrhein-Westfalen",
    "RP": "Rheinland-Pfalz",
    "SL": "Saarland",
    "SN": "Sachsen",
    "ST": "Sachsen-Anhalt",
    "SH": "Schleswig-Holstein",
    "TH": "Thüringen",
}


def _get_allowed_weekdays() -> set[int]:
    """Return the set of allowed ISO weekdays (1=Mon .. 7=Sun) from settings."""
    raw = SystemSettings.get_setting("report_weekdays", _DEFAULT_WEEKDAYS)
    try:
        return {int(d.strip()) for d in raw.split(",") if d.strip()}
    except (ValueError, AttributeError):
        return {1, 2, 3, 4, 5}


def _is_report_day(check_date: object) -> bool:
    """Return True if *check_date* is a valid report-sending day.

    Checks: configured weekdays, federal state holidays, custom holidays.
    """
    from models import CustomHoliday

    weekday = check_date.isoweekday()
    if weekday not in _get_allowed_weekdays():
        return False

    state = SystemSettings.get_setting("report_federal_state")
    if state:
        de_holidays = holidays_lib.Germany(
            state=state, years=check_date.year,
        )
        if check_date in de_holidays:
            return False

    if CustomHoliday.query.filter_by(date=check_date).first():
        return False

    return True


def _local_time_to_utc(local_hhmm: str) -> tuple[int, int]:
    """Convert a local HH:MM string (Europe/Berlin) to UTC (hour, minute).

    Uses tomorrow's date to determine the correct DST offset for
    scheduling purposes.
    """
    from datetime import datetime as dt, timedelta
    h, m = (int(x) for x in local_hhmm.split(":"))
    tomorrow = (dt.now(_BERLIN_TZ) + timedelta(days=1)).date()
    local_dt = dt(tomorrow.year, tomorrow.month, tomorrow.day, h, m,
                  tzinfo=_BERLIN_TZ)
    utc_dt = local_dt.astimezone(ZoneInfo("UTC"))
    return utc_dt.hour, utc_dt.minute


def reschedule_sla_job() -> None:
    """Re-schedule the SLA job to the configured local time (UTC-converted)."""
    from extensions import scheduler
    send_time = SystemSettings.get_setting("report_send_time", _DEFAULT_SEND_TIME)
    utc_hour, utc_minute = _local_time_to_utc(send_time)
    try:
        scheduler.reschedule_job(
            "process_sla_escalations_job",
            trigger="cron",
            hour=utc_hour,
            minute=utc_minute,
        )
        _logger.info(
            "Rescheduled SLA job: %s local -> %02d:%02d UTC",
            send_time, utc_hour, utc_minute,
        )
    except Exception as exc:
        _logger.error("Failed to reschedule SLA job: %s", exc)
```

Ausserdem `SystemSettings` zum Import in Zeile 16 hinzufuegen:

```python
from models import Comment, Ticket, TicketRecurrence, Worker, SystemSettings
```

- [ ] **Step 4: Guard in `process_sla_escalations()` einbauen**

In `process_sla_escalations()` (Zeile 130) den Guard am Anfang der `with app.app_context():`-Block einfuegen. Die Funktion wird zu:

```python
def process_sla_escalations(app: Flask) -> None:
    """Daily SLA check: notify assignees and admins about overdue tickets.

    Grace periods before first escalation:
        Prio 1 (Hoch):   0 days
        Prio 2 (Mittel): 1 day
        Prio 3 (Niedrig):3 days

    Anti-spam: re-escalation only after 23 hours.

    Instead of sending one email per ticket, this job collects all escalated
    tickets and sends a **single digest email per worker** as a daily status
    report.  Admins receive a separate digest for all high-priority tickets.

    The job is skipped entirely on non-report days (weekends, holidays).
    """
    with app.app_context():
        today = datetime.now(_BERLIN_TZ).date()
        if not _is_report_day(today):
            _logger.info("SLA job skipped: %s is not a report day.", today)
            return

        now = get_utc_now()
        try:
            overdue_tickets = _fetch_overdue_tickets(now)
            escalated = _escalate_tickets(overdue_tickets, now, EmailService)
            if escalated > 0:
                db.session.commit()
                _logger.info(
                    "SLA escalation: %d ticket(s) escalated.", escalated
                )
        except Exception as exc:
            db.session.rollback()
            _logger.error("Error in SLA escalation job: %s", exc)
```

Dafuer wird `datetime` direkt importiert (oben in den Imports hinzufuegen):

```python
from datetime import datetime
```

- [ ] **Step 5: Tests erneut ausfuehren — muessen bestehen**

Run: `cd ticketsystem && python -m pytest tests/test_report_schedule.py::TestReportDayGuard -v`

Expected: 6 passed

- [ ] **Step 6: Alle Tests pruefen**

Run: `cd ticketsystem && python -m pytest tests/ -v`

Expected: Alle bestehenden Tests bestehen weiterhin.

- [ ] **Step 7: Commit**

```bash
git add services/scheduler_service.py tests/test_report_schedule.py
git commit -m "feat: add report-day guard check with weekday/holiday/custom-holiday support"
```

---

### Task 5: Zeitzonen-Hilfsjob und SLA-Job Rescheduling beim Start

**Files:**
- Modify: `ticketsystem/services/scheduler_service.py` (neue Funktion)
- Modify: `ticketsystem/app.py:257-279`
- Modify: `ticketsystem/tests/test_report_schedule.py`

- [ ] **Step 1: Tests schreiben**

In `ticketsystem/tests/test_report_schedule.py` anfuegen:

```python
from services.scheduler_service import _local_time_to_utc


class TestLocalTimeToUtc:
    """Tests for timezone conversion helper."""

    def test_winter_time_conversion(self):
        """In CET (UTC+1), 08:00 local = 07:00 UTC."""
        # January is always CET
        with patch("services.scheduler_service.datetime") as mock_dt:
            mock_now = datetime(2026, 1, 15, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            h, m = _local_time_to_utc("08:00")
            assert h == 7
            assert m == 0

    def test_summer_time_conversion(self):
        """In CEST (UTC+2), 08:00 local = 06:00 UTC."""
        with patch("services.scheduler_service.datetime") as mock_dt:
            mock_now = datetime(2026, 7, 15, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            h, m = _local_time_to_utc("08:00")
            assert h == 6
            assert m == 0
```

- [ ] **Step 2: Tests ausfuehren — muessen bestehen**

Run: `cd ticketsystem && python -m pytest tests/test_report_schedule.py::TestLocalTimeToUtc -v`

Expected: 2 passed

- [ ] **Step 3: Hilfsjob-Funktion in scheduler_service.py hinzufuegen**

Nach der Funktion `reschedule_sla_job()` einfuegen:

```python
def process_timezone_adjustment(app: Flask) -> None:
    """Daily job (00:05 UTC): re-schedule the SLA job for DST changes."""
    with app.app_context():
        try:
            reschedule_sla_job()
        except Exception as exc:
            _logger.error("Timezone adjustment failed: %s", exc)


def schedule_timezone_adjustment_job(app: Flask) -> None:
    """Register the daily timezone adjustment job (00:05 UTC)."""
    try:
        from extensions import scheduler
        scheduler.add_job(
            id="timezone_adjustment_job",
            func=lambda: process_timezone_adjustment(app),
            trigger="cron",
            hour=0,
            minute=5,
            replace_existing=True,
        )
        _logger.info("Scheduled job: timezone_adjustment at 00:05 UTC")
    except Exception as exc:
        _logger.error("Failed to schedule timezone adjustment job: %s", exc)
```

- [ ] **Step 4: `schedule_sla_job()` anpassen — DB-Uhrzeit lesen**

Die bestehende Funktion `schedule_sla_job()` (Zeile 386) aendern:

```python
def schedule_sla_job(app: Flask) -> None:
    """Register the SLA escalation job at the configured local time."""
    try:
        from extensions import scheduler

        send_time = SystemSettings.get_setting(
            "report_send_time", _DEFAULT_SEND_TIME,
        )
        utc_hour, utc_minute = _local_time_to_utc(send_time)

        scheduler.add_job(
            id="process_sla_escalations_job",
            func=lambda: process_sla_escalations(app),
            trigger="cron",
            hour=utc_hour,
            minute=utc_minute,
            replace_existing=True,
        )
        _logger.info(
            "Scheduled job: process_sla_escalations at %s local (%02d:%02d UTC)",
            send_time, utc_hour, utc_minute,
        )
    except Exception as exc:
        _logger.error("Failed to schedule SLA escalation job: %s", exc)
```

- [ ] **Step 5: `app.py` erweitern — Hilfsjob registrieren**

In `ticketsystem/app.py` den Import (Zeile 264-267) und den Aufruf erweitern:

```python
            from services.scheduler_service import (
                schedule_recurring_job,
                schedule_reminder_job,
                schedule_sla_job,
                schedule_timezone_adjustment_job,
            )
```

Und nach `schedule_api_retention_jobs(app)` (Zeile 273):

```python
            schedule_timezone_adjustment_job(app)
```

- [ ] **Step 6: Alle Tests pruefen**

Run: `cd ticketsystem && python -m pytest tests/ -v`

Expected: Alle Tests bestehen.

- [ ] **Step 7: Commit**

```bash
git add services/scheduler_service.py app.py tests/test_report_schedule.py
git commit -m "feat: add timezone adjustment job and DB-driven SLA schedule"
```

---

### Task 6: Admin-Route erweitern (Settings + Custom Holidays CRUD)

**Files:**
- Modify: `ticketsystem/routes/admin.py`
- Modify: `ticketsystem/tests/test_report_schedule.py`

- [ ] **Step 1: Tests fuer Admin-Route schreiben**

In `ticketsystem/tests/test_report_schedule.py` anfuegen:

```python
class TestReportSettingsAdmin:
    """Tests for admin settings route — report schedule section."""

    def _login_admin(self, client, admin_worker):
        """Log in as admin via session."""
        with client.session_transaction() as sess:
            sess["worker_id"] = admin_worker.id
            sess["worker_name"] = admin_worker.name
            sess["worker_role"] = "admin"

    def test_save_report_settings(self, app, client, admin_worker, db_session):
        """Saving report schedule settings persists to SystemSettings."""
        from models import SystemSettings
        self._login_admin(client, admin_worker)
        resp = client.post("/admin/settings", data={
            "action": "save_report_schedule",
            "report_send_time": "09:00",
            "report_weekdays": ["1", "2", "3", "4", "5"],
            "report_federal_state": "BY",
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert SystemSettings.get_setting("report_send_time") == "09:00"
        assert SystemSettings.get_setting("report_weekdays") == "1,2,3,4,5"
        assert SystemSettings.get_setting("report_federal_state") == "BY"

    def test_add_custom_holiday(self, app, client, admin_worker, db_session):
        """Adding a custom holiday creates DB entries."""
        self._login_admin(client, admin_worker)
        resp = client.post("/admin/settings", data={
            "action": "add_custom_holiday",
            "holiday_start": "2026-12-24",
            "holiday_end": "2026-12-26",
            "holiday_label": "Weihnachtsferien",
        }, follow_redirects=True)
        assert resp.status_code == 200
        holidays_list = CustomHoliday.query.all()
        assert len(holidays_list) == 3  # 24., 25., 26.
        assert all(h.label == "Weihnachtsferien" for h in holidays_list)

    def test_delete_custom_holiday(self, app, client, admin_worker, db_session):
        """Deleting a custom holiday removes it from DB."""
        self._login_admin(client, admin_worker)
        h = CustomHoliday(date=date(2026, 5, 1), label="Test")
        db_session.add(h)
        db_session.commit()
        hid = h.id

        resp = client.post("/admin/settings", data={
            "action": "delete_custom_holiday",
            "holiday_id": str(hid),
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert CustomHoliday.query.get(hid) is None
```

- [ ] **Step 2: Tests ausfuehren — muessen fehlschlagen**

Run: `cd ticketsystem && python -m pytest tests/test_report_schedule.py::TestReportSettingsAdmin -v`

Expected: FAIL — die Aktionen sind noch nicht implementiert.

- [ ] **Step 3: Import von CustomHoliday in admin.py**

In `ticketsystem/routes/admin.py` den Import (Zeile 23-29) erweitern — `CustomHoliday` hinzufuegen:

```python
from models import (
    ChecklistItem,
    ChecklistTemplate,
    ChecklistTemplateItem,
    Comment,
    CustomHoliday,
    SystemSettings,
    Team,
```

- [ ] **Step 4: Settings-Route erweitern — report_schedule-Daten ans Template geben**

Die `settings()`-Funktion (Zeile 360) aendern:

```python
@admin_bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings() -> str | WerkzeugResponse:
    """SMTP and system settings page."""
    if request.method == "POST":
        result = _dispatch_settings_action()
        if result is not None:
            return result
        return redirect(url_for("admin.settings"))

    current: dict[str, str] = {
        key: SystemSettings.get_setting(key, "") for key in _SMTP_KEYS
    }
    report_cfg = {
        "send_time": SystemSettings.get_setting("report_send_time", "07:00"),
        "weekdays": SystemSettings.get_setting("report_weekdays", "1,2,3,4,5"),
        "federal_state": SystemSettings.get_setting("report_federal_state", ""),
    }
    custom_holidays = (
        CustomHoliday.query.order_by(CustomHoliday.date).all()
    )

    from services.scheduler_service import FEDERAL_STATES
    return render_template(
        "settings.html",
        smtp=current,
        report_cfg=report_cfg,
        custom_holidays=custom_holidays,
        federal_states=FEDERAL_STATES,
    )
```

- [ ] **Step 5: Dispatch-Funktion erweitern**

In `_dispatch_settings_action()` (Zeile 376) neue Branches hinzufuegen:

```python
def _dispatch_settings_action() -> WerkzeugResponse | None:
    """Route the POST action to the appropriate settings handler."""
    action = request.form.get("action")
    if action == "save_smtp":
        _save_smtp()
    elif action == "test_smtp":
        _test_smtp()
    elif action == "clear_smtp_password":
        SystemSettings.set_setting("smtp_password", "")
        flash("SMTP-Passwort wurde entfernt.", "success")
    elif action == "generate_tokens":
        return _generate_tokens()
    elif action == "save_report_schedule":
        _save_report_schedule()
    elif action == "add_custom_holiday":
        _add_custom_holiday()
    elif action == "delete_custom_holiday":
        _delete_custom_holiday()
    return None
```

- [ ] **Step 6: Handler-Funktionen implementieren**

Nach `_test_smtp()` (nach Zeile 427) einfuegen:

```python
def _save_report_schedule() -> None:
    """Persist report schedule settings and reschedule the SLA job."""
    send_time = request.form.get("report_send_time", "07:00").strip()
    weekdays = ",".join(request.form.getlist("report_weekdays"))
    federal_state = request.form.get("report_federal_state", "").strip()

    SystemSettings.set_setting("report_send_time", send_time)
    SystemSettings.set_setting("report_weekdays", weekdays or "1,2,3,4,5")
    if federal_state:
        SystemSettings.set_setting("report_federal_state", federal_state)
    else:
        # Remove setting to disable holiday check
        setting = SystemSettings.query.filter_by(
            key="report_federal_state",
        ).first()
        if setting:
            db.session.delete(setting)
            db.session.commit()

    # Reschedule the SLA job to the new time
    try:
        from services.scheduler_service import reschedule_sla_job
        reschedule_sla_job()
    except Exception:
        pass  # Scheduler may not be running in dev/test

    flash("Berichtsversand-Einstellungen gespeichert.", "success")


def _add_custom_holiday() -> None:
    """Add one or more custom holidays (date range + label)."""
    from datetime import date, timedelta

    start_str = request.form.get("holiday_start", "").strip()
    end_str = request.form.get("holiday_end", "").strip()
    label = request.form.get("holiday_label", "").strip()

    if not start_str or not label:
        flash("Datum und Bezeichnung sind Pflichtfelder.", "warning")
        return

    try:
        start = date.fromisoformat(start_str)
        end = date.fromisoformat(end_str) if end_str else start
    except ValueError:
        flash("Ungültiges Datumsformat.", "danger")
        return

    if end < start:
        flash("Enddatum darf nicht vor dem Startdatum liegen.", "warning")
        return

    added = 0
    current = start
    while current <= end:
        existing = CustomHoliday.query.filter_by(date=current).first()
        if not existing:
            db.session.add(CustomHoliday(date=current, label=label))
            added += 1
        current += timedelta(days=1)

    if added > 0:
        db.session.commit()
        flash(f"{added} freie(r) Tag(e) hinzugefügt.", "success")
    else:
        flash("Alle Tage waren bereits eingetragen.", "info")


def _delete_custom_holiday() -> None:
    """Delete a single custom holiday by ID."""
    hid = request.form.get("holiday_id")
    if not hid:
        return
    holiday = db.session.get(CustomHoliday, int(hid))
    if holiday:
        db.session.delete(holiday)
        db.session.commit()
        flash(
            f"Freier Tag ({holiday.date.strftime('%d.%m.%Y')}) entfernt.",
            "success",
        )
```

- [ ] **Step 7: Tests erneut ausfuehren — muessen bestehen**

Run: `cd ticketsystem && python -m pytest tests/test_report_schedule.py::TestReportSettingsAdmin -v`

Expected: 3 passed

- [ ] **Step 8: Alle Tests pruefen**

Run: `cd ticketsystem && python -m pytest tests/ -v`

Expected: Alle Tests bestehen.

- [ ] **Step 9: Commit**

```bash
git add routes/admin.py tests/test_report_schedule.py
git commit -m "feat: add report schedule and custom holiday admin actions"
```

---

### Task 7: Settings-Template erweitern

**Files:**
- Modify: `ticketsystem/templates/settings.html`

- [ ] **Step 1: Neuen Abschnitt "Berichtsversand" einfuegen**

In `ticketsystem/templates/settings.html` nach dem Emergency-Access-Block (nach Zeile 217, vor `{% endblock %}`) einfuegen:

```html
<!-- Report Schedule Configuration -->
<div class="row g-4 mt-0" id="report-schedule">
  <div class="col-lg-7">
    <div class="card card-std">
      <div class="card-header card-header-std">
        <h2 class="h5 fw-bold mb-0"><i class="bi bi-calendar-check text-primary me-2"></i>Berichtsversand</h2>
      </div>
      <div class="card-body px-4 pb-4">
        <p class="text-secondary small mb-3">
          Steuert, wann der SLA-Eskalationsbericht verschickt wird. An nicht-aktiven Tagen pausiert der gesamte Job.
        </p>
        <form method="post" autocomplete="off" novalidate>
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
          <input type="hidden" name="action" value="save_report_schedule">

          <div class="row g-3 mb-3">
            <div class="col-sm-4">
              <label for="report_send_time" class="form-label fw-semibold small">Versandzeit</label>
              <input type="time" class="form-control" id="report_send_time"
                     name="report_send_time" value="{{ report_cfg.send_time }}">
              <div class="form-text">Europe/Berlin (MEZ/MESZ)</div>
            </div>
            <div class="col-sm-8">
              <label class="form-label fw-semibold small">Bundesland (Feiertage)</label>
              <select class="form-select" name="report_federal_state" id="report_federal_state">
                <option value="">— Kein Feiertagsfilter —</option>
                {% for code, name in federal_states.items() %}
                <option value="{{ code }}" {{ 'selected' if report_cfg.federal_state == code else '' }}>{{ name }}</option>
                {% endfor %}
              </select>
            </div>
          </div>

          <div class="mb-3">
            <label class="form-label fw-semibold small">Aktive Wochentage</label>
            <div class="d-flex flex-wrap gap-3">
              {% set active_days = report_cfg.weekdays.split(',') %}
              {% set day_names = [('1','Mo'), ('2','Di'), ('3','Mi'), ('4','Do'), ('5','Fr'), ('6','Sa'), ('7','So')] %}
              {% for val, label in day_names %}
              <div class="form-check">
                <input class="form-check-input" type="checkbox" name="report_weekdays"
                       value="{{ val }}" id="wd_{{ val }}"
                       {{ 'checked' if val in active_days else '' }}>
                <label class="form-check-label small" for="wd_{{ val }}">{{ label }}</label>
              </div>
              {% endfor %}
            </div>
          </div>

          <div id="holiday-preview" class="mb-3" style="display:none;">
            <label class="form-label fw-semibold small">Nächste Feiertage</label>
            <ul class="list-unstyled small text-muted mb-0" id="holiday-list"></ul>
          </div>

          <button type="submit" class="btn btn-primary">
            <i class="bi bi-floppy me-1"></i>Berichtsversand speichern
          </button>
        </form>
      </div>
    </div>
  </div>

  <!-- Custom Holidays -->
  <div class="col-lg-5">
    <div class="card card-std">
      <div class="card-header card-header-std">
        <h2 class="h5 fw-bold mb-0"><i class="bi bi-calendar-x text-warning me-2"></i>Zusätzliche freie Tage</h2>
      </div>
      <div class="card-body px-4 pb-4">
        <form method="post" autocomplete="off" novalidate class="mb-3">
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
          <input type="hidden" name="action" value="add_custom_holiday">
          <div class="row g-2 mb-2">
            <div class="col-6">
              <label for="holiday_start" class="form-label fw-semibold small">Von</label>
              <input type="date" class="form-control form-control-sm" id="holiday_start"
                     name="holiday_start" required>
            </div>
            <div class="col-6">
              <label for="holiday_end" class="form-label fw-semibold small">Bis (optional)</label>
              <input type="date" class="form-control form-control-sm" id="holiday_end"
                     name="holiday_end">
            </div>
          </div>
          <div class="mb-2">
            <label for="holiday_label" class="form-label fw-semibold small">Bezeichnung</label>
            <input type="text" class="form-control form-control-sm" id="holiday_label"
                   name="holiday_label" placeholder="z. B. Betriebsferien" required>
          </div>
          <button type="submit" class="btn btn-sm btn-outline-primary">
            <i class="bi bi-plus-circle me-1"></i>Hinzufügen
          </button>
        </form>

        {% if custom_holidays %}
        <table class="table table-sm small mb-0">
          <thead>
            <tr>
              <th>Datum</th>
              <th>Bezeichnung</th>
              <th class="text-end">Aktion</th>
            </tr>
          </thead>
          <tbody>
            {% for h in custom_holidays %}
            <tr>
              <td>{{ h.date.strftime('%d.%m.%Y') }}</td>
              <td>{{ h.label }}</td>
              <td class="text-end">
                <form method="post" class="d-inline">
                  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                  <input type="hidden" name="action" value="delete_custom_holiday">
                  <input type="hidden" name="holiday_id" value="{{ h.id }}">
                  <button type="submit" class="btn btn-sm btn-outline-danger p-0 px-1"
                          title="Entfernen">
                    <i class="bi bi-trash"></i>
                  </button>
                </form>
              </td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
        {% else %}
        <p class="text-muted small mb-0">Keine zusätzlichen freien Tage eingetragen.</p>
        {% endif %}
      </div>
    </div>
  </div>
</div>
```

- [ ] **Step 2: Feiertags-Vorschau JavaScript hinzufuegen**

Im `{% block scripts %}`-Block (Zeile 220) den bestehenden JS-Code erweitern — nach dem Password-Toggle-Script:

```html
  // Holiday preview
  const stateSelect = document.getElementById('report_federal_state');
  const previewDiv = document.getElementById('holiday-preview');
  const holidayList = document.getElementById('holiday-list');
  if (stateSelect && previewDiv) {
    stateSelect.addEventListener('change', () => {
      const state = stateSelect.value;
      if (!state) { previewDiv.style.display = 'none'; return; }
      fetch('{{ ingress_path }}{{ url_for("admin.holiday_preview") }}?state=' + encodeURIComponent(state))
        .then(r => r.json())
        .then(data => {
          holidayList.innerHTML = '';
          data.holidays.forEach(h => {
            const li = document.createElement('li');
            li.textContent = h.date + ' — ' + h.name;
            holidayList.appendChild(li);
          });
          previewDiv.style.display = '';
        })
        .catch(() => { previewDiv.style.display = 'none'; });
    });
    // Trigger on load if state is selected
    if (stateSelect.value) stateSelect.dispatchEvent(new Event('change'));
  }
```

- [ ] **Step 3: Holiday-Preview API-Endpunkt in admin.py**

In `ticketsystem/routes/admin.py` nach den Custom-Holiday-Handlern einfuegen:

```python
@admin_bp.route("/holiday-preview")
@admin_required
def holiday_preview() -> WerkzeugResponse:
    """Return the next 5 federal holidays as JSON for the preview widget."""
    import holidays as holidays_lib
    from datetime import date
    from flask import jsonify

    state = request.args.get("state", "")
    if not state:
        return jsonify(holidays=[])

    today = date.today()
    de = holidays_lib.Germany(state=state, years=[today.year, today.year + 1])
    upcoming = sorted(
        [(d, name) for d, name in de.items() if d >= today],
        key=lambda x: x[0],
    )[:5]

    return jsonify(holidays=[
        {"date": d.strftime("%d.%m.%Y"), "name": name}
        for d, name in upcoming
    ])
```

- [ ] **Step 4: Manuell im Browser testen**

Dev-Server starten und `/admin/settings` aufrufen:
1. Neuer Abschnitt "Berichtsversand" ist sichtbar
2. Uhrzeit, Wochentage und Bundesland koennen gespeichert werden
3. Bundesland-Auswahl zeigt Feiertags-Vorschau
4. Zusaetzliche freie Tage: Hinzufuegen (einzeln und Bereich), Loeschen funktioniert

- [ ] **Step 5: Alle Tests pruefen**

Run: `cd ticketsystem && python -m pytest tests/ -v`

Expected: Alle Tests bestehen.

- [ ] **Step 6: Commit**

```bash
git add templates/settings.html routes/admin.py
git commit -m "feat: add report schedule configuration UI with holiday preview"
```

---

### Task 8: Integrations-Test und Flake8

**Files:**
- Modify: `ticketsystem/tests/test_report_schedule.py`

- [ ] **Step 1: Integrations-Test schreiben**

In `ticketsystem/tests/test_report_schedule.py` anfuegen:

```python
class TestSlaJobGuardIntegration:
    """Integration test: SLA job respects report-day settings."""

    def test_sla_job_skips_on_weekend(self, app, db_session):
        """SLA job does nothing when today is a non-report day."""
        from models import SystemSettings
        from services.scheduler_service import process_sla_escalations
        SystemSettings.set_setting("report_weekdays", "1,2,3,4,5")

        # Mock today as Saturday
        with patch("services.scheduler_service.datetime") as mock_dt:
            saturday = datetime(2026, 4, 25, 8, 0, tzinfo=ZoneInfo("Europe/Berlin"))
            mock_dt.now.return_value = saturday
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            process_sla_escalations(app)

        # No tickets should have been escalated (job returned early)
        # Verify by checking no new comments were created
        from models import Comment
        system_comments = Comment.query.filter_by(
            event_type="SLA_ESCALATION"
        ).all()
        assert len(system_comments) == 0
```

- [ ] **Step 2: Tests ausfuehren**

Run: `cd ticketsystem && python -m pytest tests/test_report_schedule.py -v`

Expected: Alle Tests in der Datei bestehen.

- [ ] **Step 3: Flake8 pruefen**

Run: `cd ticketsystem && python -m flake8 --max-line-length=120 models.py services/scheduler_service.py routes/admin.py`

Expected: Keine Fehler. Falls welche auftreten, beheben.

- [ ] **Step 4: Vollstaendige Test-Suite pruefen**

Run: `cd ticketsystem && python -m pytest tests/ -v`

Expected: Alle Tests bestehen. Baseline darf sich nicht verschlechtern.

- [ ] **Step 5: Commit**

```bash
git add tests/test_report_schedule.py
git commit -m "test: add integration test for SLA job weekend skip"
```

---

## Zusammenfassung der Aenderungen

| Datei | Aenderung |
|-------|-----------|
| `requirements.txt` | `holidays>=0.65,<1.0` |
| `models.py` | `CustomHoliday` Model |
| `migrations/versions/a1b2c3d4e5f6_...py` | Neue Tabelle `custom_holiday` |
| `services/scheduler_service.py` | Guard-Check, Zeitzonen-Helper, Rescheduling, Bundesland-Dict, Hilfsjob |
| `app.py` | `schedule_timezone_adjustment_job` registrieren |
| `routes/admin.py` | Report-Schedule + Custom-Holiday Handlers, Holiday-Preview-Endpunkt |
| `templates/settings.html` | Berichtsversand-Abschnitt mit Feiertags-Vorschau |
| `tests/test_report_schedule.py` | 12+ Tests fuer Model, Guard, Timezone, Admin-UI, Integration |
