# Performance Optimierungen — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fehlende DB-Indizes, N+1-Queries, unbegrenzte Scans und wiederholte DB-Aufrufe beheben, um die Anwendung fit für den Produktionseinsatz mit wachsenden Daten zu machen.

**Architecture:** Bottom-up in 5 Schichten: (1) DB-Indizes per Alembic-Migration, (2) Eager-Loading-Fixes in Hot-Path-Queries, (3) SQL-Aggregations-Rewrites für teure Python-Schleifen, (4) Request-Level-Caching via `flask.g` für Worker/Team-Listen, (5) Short-TTL-Caching mit `cachetools` für teure Aggregationen.

**Tech Stack:** SQLAlchemy 2.x (session.query-Style), Alembic, Flask.g, cachetools

---

## File Map

| Aktion | Datei | Verantwortung |
|--------|-------|---------------|
| Create | `migrations/versions/a0b1c2d3e4f5_performance_indexes.py` | DB-Indizes |
| Modify | `services/dashboard_service.py` | Eager Loading, Projekts-Rewrite, LIMIT, TTL-Cache |
| Modify | `services/scheduler_service.py` | Eager Loading für Eskalations-Loop |
| Modify | `services/ticket_core_service.py` | Eager Loading für duplicate_ticket |
| Modify | `routes/_helpers.py` | g-Cache-Helper für Workers und Teams |
| Modify | `routes/ticket_views.py` | Alle Worker.query/Team.query auf Helper umstellen |
| Modify | `routes/dashboard.py` | _compute_summary_counts: doppelte Session-Reads fixen + TTL-Cache |
| Modify | `requirements.txt` | cachetools ergänzen |

---

## Schicht 1: DB-Indizes

### Task 1: Alembic-Migration mit Performance-Indizes

**Files:**
- Create: `ticketsystem/migrations/versions/a0b1c2d3e4f5_performance_indexes.py`

- [ ] **Step 1.1: Migration-Datei erstellen**

Erstelle `ticketsystem/migrations/versions/a0b1c2d3e4f5_performance_indexes.py`:

```python
"""performance indexes

Revision ID: a0b1c2d3e4f5
Revises: e6f7a8b9c0d1
Create Date: 2026-04-12

"""
from alembic import op

revision = 'a0b1c2d3e4f5'
down_revision = 'e6f7a8b9c0d1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ticket: häufigste Filter-Spalten
    op.create_index('ix_ticket_status', 'ticket', ['status'])
    op.create_index('ix_ticket_is_deleted', 'ticket', ['is_deleted'])
    # Komposit-Index für den häufigsten kombinierten Filter (is_deleted + status)
    op.create_index('ix_ticket_is_deleted_status', 'ticket', ['is_deleted', 'status'])
    op.create_index('ix_ticket_assigned_to_id', 'ticket', ['assigned_to_id'])
    op.create_index('ix_ticket_assigned_team_id', 'ticket', ['assigned_team_id'])
    op.create_index('ix_ticket_due_date', 'ticket', ['due_date'])
    op.create_index('ix_ticket_created_at', 'ticket', ['created_at'])
    # Comment: ticket_id-Subqueries in Suche und Vertraulichkeits-Filter
    op.create_index('ix_comment_ticket_id', 'comment', ['ticket_id'])
    # Notification: User-spezifische Abfragen
    op.create_index('ix_notification_user_id', 'notification', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_notification_user_id', table_name='notification')
    op.drop_index('ix_comment_ticket_id', table_name='comment')
    op.drop_index('ix_ticket_created_at', table_name='ticket')
    op.drop_index('ix_ticket_due_date', table_name='ticket')
    op.drop_index('ix_ticket_assigned_team_id', table_name='ticket')
    op.drop_index('ix_ticket_assigned_to_id', table_name='ticket')
    op.drop_index('ix_ticket_is_deleted_status', table_name='ticket')
    op.drop_index('ix_ticket_is_deleted', table_name='ticket')
    op.drop_index('ix_ticket_status', table_name='ticket')
```

- [ ] **Step 1.2: Migration ausführen**

```bash
cd ticketsystem
python -m flask db upgrade
```

Erwartetes Ergebnis: Migration läuft ohne Fehler durch, endet mit `Running upgrade e6f7a8b9c0d1 -> a0b1c2d3e4f5`.

- [ ] **Step 1.3: Indizes verifizieren**

```bash
cd ticketsystem
python -c "
from app import app
from extensions import db
with app.app_context():
    for tbl in ('ticket', 'comment', 'notification'):
        rows = db.session.execute(db.text(f\"PRAGMA index_list('{tbl}')\")).fetchall()
        print(f'--- {tbl} ---')
        for r in rows: print(r)
"
```

Erwartetes Ergebnis: Für `ticket` erscheinen `ix_ticket_status`, `ix_ticket_is_deleted`, `ix_ticket_is_deleted_status`, `ix_ticket_assigned_to_id`, `ix_ticket_assigned_team_id`, `ix_ticket_due_date`, `ix_ticket_created_at`. Für `comment`: `ix_comment_ticket_id`. Für `notification`: `ix_notification_user_id`.

- [ ] **Step 1.4: Tests ausführen**

```bash
cd ticketsystem && python -m pytest tests/ -v
```

Erwartetes Ergebnis: 7 passed, 8 failed (Baseline unverändert).

- [ ] **Step 1.5: Commit**

```bash
git add ticketsystem/migrations/versions/a0b1c2d3e4f5_performance_indexes.py
git commit -m "perf: DB-Indizes für Ticket, Comment und Notification hinzufügen"
```

---

## Schicht 2: Eager Loading

### Task 2: Eager Loading im Workload-Overview

**Files:**
- Modify: `ticketsystem/services/dashboard_service.py:375-385`

Die Methode `get_workload_overview()` ruft `_group_tickets_by_worker()` auf, welche `ticket.assigned_team.members` iteriert. Ohne Eager Loading triggert das pro Ticket eine separate DB-Query.

- [ ] **Step 2.1: Failing-Test schreiben**

Füge in `ticketsystem/tests/test_tickets.py` nach dem letzten Test ein:

```python
def test_workload_overview_does_not_raise(client, auth):
    """Workload overview must return without DB errors even with teams assigned."""
    from services.dashboard_service import DashboardService
    with client.application.app_context():
        absent, present = DashboardService.get_workload_overview()
        # Rückgabe ist immer möglich, auch wenn keine Tickets vorhanden sind
        assert isinstance(absent, list)
        assert isinstance(present, list)
```

- [ ] **Step 2.2: Test ausführen und sehen dass er läuft (keine Regression)**

```bash
cd ticketsystem && python -m pytest tests/test_tickets.py::test_workload_overview_does_not_raise -v
```

Erwartetes Ergebnis: PASSED (kein Fehler, leere Listen bei leerem DB-State).

- [ ] **Step 2.3: Eager Loading ergänzen**

In `ticketsystem/services/dashboard_service.py`, ersetze die `get_workload_overview()`-Query (Zeilen 375–385):

```python
# ALT:
tickets = (
    Ticket.query.filter(
        Ticket.is_deleted.is_(False),
        Ticket.status.in_(_OPEN_STATUSES),
        db.or_(
            Ticket.assigned_to_id.isnot(None),
            Ticket.assigned_team_id.isnot(None),
        ),
    )
    .all()
)
```

Ersetzen durch:

```python
tickets = (
    Ticket.query.filter(
        Ticket.is_deleted.is_(False),
        Ticket.status.in_(_OPEN_STATUSES),
        db.or_(
            Ticket.assigned_to_id.isnot(None),
            Ticket.assigned_team_id.isnot(None),
        ),
    )
    .options(
        joinedload(Ticket.assigned_to),
        selectinload(Ticket.assigned_team).selectinload(Team.members),
        selectinload(Ticket.checklists),
    )
    .all()
)
```

Ergänze den `Team`-Import in `dashboard_service.py` — füge in Zeile 16 `Team` hinzu:

```python
from models import ChecklistItem, Comment, Team, Ticket, TicketContact, Worker
```

Und ergänze in den Importen von sqlalchemy.orm am Anfang:
```python
from sqlalchemy.orm import joinedload, selectinload
```
(dieser Import existiert bereits — keine Änderung nötig).

- [ ] **Step 2.4: Tests ausführen**

```bash
cd ticketsystem && python -m pytest tests/ -v
```

Erwartetes Ergebnis: 7 passed, 8 failed.

- [ ] **Step 2.5: Commit**

```bash
git add ticketsystem/services/dashboard_service.py
git commit -m "perf: Eager Loading für Workload-Overview (N+1 Team-Members eliminiert)"
```

---

### Task 3: Eager Loading im Scheduler

**Files:**
- Modify: `ticketsystem/services/scheduler_service.py:154-164`

In `_escalate_tickets()` (Zeile 201–205) wird `ticket.assigned_to.name` aufgerufen. Ohne Eager Loading in `_fetch_overdue_tickets()` triggert das pro Ticket eine eigene DB-Query.

- [ ] **Step 3.1: Eager Loading ergänzen**

In `ticketsystem/services/scheduler_service.py`, ersetze `_fetch_overdue_tickets()`:

```python
# ALT:
def _fetch_overdue_tickets(now: object) -> List[Ticket]:
    """Return all non-deleted open tickets that are past their due date."""
    return Ticket.query.filter(
        Ticket.is_deleted.is_(False),
        Ticket.status.in_(_OPEN_STATUSES),
        Ticket.due_date.isnot(None),
        Ticket.due_date < now.date(),
    ).all()
```

Ersetzen durch:

```python
def _fetch_overdue_tickets(now: object) -> List[Ticket]:
    """Return all non-deleted open tickets that are past their due date."""
    from sqlalchemy.orm import joinedload
    return Ticket.query.filter(
        Ticket.is_deleted.is_(False),
        Ticket.status.in_(_OPEN_STATUSES),
        Ticket.due_date.isnot(None),
        Ticket.due_date < now.date(),
    ).options(
        joinedload(Ticket.assigned_to),
    ).all()
```

- [ ] **Step 3.2: Import-Check**

```bash
cd ticketsystem && python -c "from app import app"
```

Erwartetes Ergebnis: Kein Fehler.

- [ ] **Step 3.3: Tests ausführen**

```bash
cd ticketsystem && python -m pytest tests/ -v
```

Erwartetes Ergebnis: 7 passed, 8 failed.

- [ ] **Step 3.4: Commit**

```bash
git add ticketsystem/services/scheduler_service.py
git commit -m "perf: Eager Loading für Eskalations-Scheduler (assigned_to N+1 eliminiert)"
```

---

### Task 4: Eager Loading in duplicate_ticket

**Files:**
- Modify: `ticketsystem/services/ticket_core_service.py:756-819`

`duplicate_ticket()` lädt das Quell-Ticket via `_get_ticket_or_raise(ticket_id)` (→ `db.session.get`), dann iteriert es `source.tags`, `source.checklists`, `source.contact` und `source.recurrence` — alles Lazy Loads.

- [ ] **Step 4.1: Eager Loading ergänzen**

In `ticketsystem/services/ticket_core_service.py`, ersetze in `duplicate_ticket()` Zeile 766:

```python
# ALT:
source = _get_ticket_or_raise(ticket_id)
```

Ersetzen durch:

```python
from sqlalchemy.orm import joinedload, selectinload
source = (
    Ticket.query.filter_by(id=ticket_id)
    .options(
        joinedload(Ticket.contact),
        joinedload(Ticket.recurrence),
        selectinload(Ticket.tags),
        selectinload(Ticket.checklists),
    )
    .first()
)
if not source or source.is_deleted:
    raise DomainError("Ticket nicht gefunden.")
```

- [ ] **Step 4.2: Import-Check**

```bash
cd ticketsystem && python -c "from app import app"
```

Erwartetes Ergebnis: Kein Fehler.

- [ ] **Step 4.3: Tests ausführen**

```bash
cd ticketsystem && python -m pytest tests/ -v
```

Erwartetes Ergebnis: 7 passed, 8 failed.

- [ ] **Step 4.4: Commit**

```bash
git add ticketsystem/services/ticket_core_service.py
git commit -m "perf: Eager Loading für duplicate_ticket (tags, checklists, contact, recurrence)"
```

---

## Schicht 3: Query-Rewrites

### Task 5: get_projects_summary — SQL-Aggregation statt Python-Schleife

**Files:**
- Modify: `ticketsystem/services/dashboard_service.py:344-365`

Aktuell werden alle Projekt-Tickets als ORM-Objekte geladen (inkl. aller Felder) + alle Checklist-Items via `selectinload`. Danach folgt eine Python-Schleife zur Aggregation. Die neue Implementierung führt eine SQL-Aggregation mit `GROUP BY (order_reference, status)` durch und verwendet eine Subquery für die Checklisten-Fortschrittswerte.

- [ ] **Step 5.1: Failing-Test schreiben**

Füge in `ticketsystem/tests/test_tickets.py` ein (nutzt die bereits vorhandenen Fixtures):

```python
def test_projects_summary_structure(client, auth):
    """get_projects_summary muss die erwarteten Schlüssel zurückgeben."""
    from services.dashboard_service import DashboardService
    with client.application.app_context():
        result = DashboardService.get_projects_summary()
        assert isinstance(result, list)
        for p in result:
            assert "order_reference" in p
            assert "total_tickets" in p
            assert "completed_tickets" in p
            assert "progress" in p
            assert "status_counts" in p
            assert isinstance(p["status_counts"], dict)
            assert 0 <= p["progress"] <= 100
```

- [ ] **Step 5.2: Test ausführen (soll mit aktuellem Code bereits passen)**

```bash
cd ticketsystem && python -m pytest tests/test_tickets.py::test_projects_summary_structure -v
```

Erwartetes Ergebnis: PASSED. Dieser Test dient als Regressions-Guard für den Rewrite.

- [ ] **Step 5.3: get_projects_summary() umschreiben**

Ersetze in `ticketsystem/services/dashboard_service.py` die gesamte `get_projects_summary()`-Methode (Zeilen 344–365):

```python
@staticmethod
def get_projects_summary() -> List[Dict[str, Any]]:
    """Fetch projects grouped by order_reference with progress.

    Uses a single SQL query with GROUP BY instead of loading full ORM
    objects, avoiding N+1 on checklists.
    """
    from sqlalchemy import Float, case, cast

    # Checklist done/total per ticket as subquery
    ci = (
        db.session.query(
            ChecklistItem.ticket_id.label("tid"),
            func.count(ChecklistItem.id).label("total"),
            func.sum(
                case((ChecklistItem.is_completed.is_(True), 1), else_=0)
            ).label("done"),
        )
        .group_by(ChecklistItem.ticket_id)
        .subquery()
    )

    rows = (
        db.session.query(
            Ticket.order_reference,
            Ticket.status,
            func.count(Ticket.id).label("cnt"),
            func.max(
                func.coalesce(Ticket.updated_at, Ticket.created_at)
            ).label("last_upd"),
            func.sum(
                case(
                    (
                        ci.c.total > 0,
                        cast(ci.c.done, Float) / cast(ci.c.total, Float),
                    ),
                    (Ticket.status == TicketStatus.ERLEDIGT.value, 1.0),
                    else_=0.0,
                )
            ).label("progress_sum"),
        )
        .outerjoin(ci, Ticket.id == ci.c.tid)
        .filter(
            Ticket.is_deleted.is_(False),
            Ticket.order_reference.isnot(None),
            Ticket.order_reference != "",
        )
        .group_by(Ticket.order_reference, Ticket.status)
        .all()
    )

    projects: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        ref = row.order_reference.strip()
        if not ref:
            continue
        if ref not in projects:
            projects[ref] = {
                "order_reference": ref,
                "total_tickets": 0,
                "completed_tickets": 0,
                "last_updated": None,
                "ticket_progress_sum": 0.0,
                "status_counts": {s.value: 0 for s in TicketStatus},
            }
        p = projects[ref]
        p["total_tickets"] += row.cnt
        p["status_counts"][row.status] = (
            p["status_counts"].get(row.status, 0) + row.cnt
        )
        if row.status == TicketStatus.ERLEDIGT.value:
            p["completed_tickets"] += row.cnt
        p["ticket_progress_sum"] += row.progress_sum or 0.0
        if row.last_upd and (
            not p["last_updated"] or row.last_upd > p["last_updated"]
        ):
            p["last_updated"] = row.last_upd

    return _finalize_projects(projects)
```

Entferne die jetzt ungenutzten Hilfsfunktionen `_new_project_entry()` und `_accumulate_ticket()` aus `dashboard_service.py` — sie werden nur noch von der neuen Implementierung nicht mehr aufgerufen. **Prüfe zuerst per grep, dass sie nirgendwo sonst importiert werden:**

```bash
grep -rn "_new_project_entry\|_accumulate_ticket" ticketsystem/
```

Nur wenn die grep-Ausgabe ausschließlich Zeilen in `dashboard_service.py` selbst zeigt: Beide Funktionen entfernen.

- [ ] **Step 5.4: Regressions-Test ausführen**

```bash
cd ticketsystem && python -m pytest tests/test_tickets.py::test_projects_summary_structure -v
```

Erwartetes Ergebnis: PASSED.

- [ ] **Step 5.5: Vollständige Tests ausführen**

```bash
cd ticketsystem && python -m pytest tests/ -v
```

Erwartetes Ergebnis: 7 passed, 8 failed.

- [ ] **Step 5.6: Commit**

```bash
git add ticketsystem/services/dashboard_service.py
git commit -m "perf: get_projects_summary auf SQL GROUP BY umgeschrieben (kein ORM-Fullscan)"
```

---

### Task 6: get_workload_overview — LIMIT 1000

**Files:**
- Modify: `ticketsystem/services/dashboard_service.py:375-385`

- [ ] **Step 6.1: LIMIT ergänzen**

In der Workload-Query in `get_workload_overview()` (nach dem Ergebnis von Task 2), füge `.limit(1000)` vor `.all()` ein:

```python
tickets = (
    Ticket.query.filter(
        Ticket.is_deleted.is_(False),
        Ticket.status.in_(_OPEN_STATUSES),
        db.or_(
            Ticket.assigned_to_id.isnot(None),
            Ticket.assigned_team_id.isnot(None),
        ),
    )
    .options(
        joinedload(Ticket.assigned_to),
        selectinload(Ticket.assigned_team).selectinload(Team.members),
        selectinload(Ticket.checklists),
    )
    .limit(1000)
    .all()
)
```

- [ ] **Step 6.2: Tests ausführen**

```bash
cd ticketsystem && python -m pytest tests/ -v
```

Erwartetes Ergebnis: 7 passed, 8 failed.

- [ ] **Step 6.3: Commit**

```bash
git add ticketsystem/services/dashboard_service.py
git commit -m "perf: Workload-Overview-Query auf LIMIT 1000 begrenzt"
```

---

## Schicht 4: Request-Level-Caching

### Task 7: g-Cache-Helper in routes/_helpers.py

**Files:**
- Modify: `ticketsystem/routes/_helpers.py`

Active Workers und Teams werden auf manchen Seiten bis zu 5× pro Request geladen. Diese Helper cachen das Ergebnis im Flask-`g`-Objekt (lebt nur für die Dauer eines Requests — kein Stale-Data-Problem).

- [ ] **Step 7.1: Failing-Test schreiben**

Füge in `ticketsystem/tests/test_bugs.py` einen neuen Test ein:

```python
def test_get_active_workers_cached_in_g(client, auth):
    """get_active_workers() darf pro Request nur einmal die DB befragen."""
    from routes._helpers import get_active_workers
    with client.application.test_request_context("/"):
        from flask import g
        workers_1 = get_active_workers()
        workers_2 = get_active_workers()
        # Zweiter Aufruf muss dasselbe Objekt zurückgeben (aus g-Cache)
        assert workers_1 is workers_2
```

- [ ] **Step 7.2: Test ausführen (soll FEHLEN — Funktion existiert noch nicht)**

```bash
cd ticketsystem && python -m pytest tests/test_bugs.py::test_get_active_workers_cached_in_g -v
```

Erwartetes Ergebnis: ERROR — `ImportError: cannot import name 'get_active_workers'`.

- [ ] **Step 7.3: Helper-Funktionen implementieren**

Füge am Ende von `ticketsystem/routes/_helpers.py` hinzu (nach den bestehenden Funktionen):

```python
# ---------------------------------------------------------------------------
# Request-Level-Cache (flask.g) für häufig geladene Stammdaten
# ---------------------------------------------------------------------------

def get_active_workers():
    """Active Workers einmal pro Request laden und in g cachen."""
    from flask import g
    from models import Worker
    if not hasattr(g, "_active_workers"):
        g._active_workers = (
            Worker.query.filter_by(is_active=True).order_by(Worker.name).all()
        )
    return g._active_workers


def get_all_teams():
    """Alle Teams einmal pro Request laden und in g cachen."""
    from flask import g
    from models import Team
    if not hasattr(g, "_all_teams"):
        g._all_teams = Team.query.order_by(Team.name).all()
    return g._all_teams


def get_team_ids_for_worker(worker_id: int) -> list:
    """Team-IDs eines Workers einmal pro Request cachen."""
    from flask import g
    from models import Team
    if not hasattr(g, "_team_ids"):
        g._team_ids = {}
    if worker_id not in g._team_ids:
        g._team_ids[worker_id] = Team.team_ids_for_worker(worker_id)
    return g._team_ids[worker_id]
```

- [ ] **Step 7.4: Test ausführen**

```bash
cd ticketsystem && python -m pytest tests/test_bugs.py::test_get_active_workers_cached_in_g -v
```

Erwartetes Ergebnis: PASSED.

- [ ] **Step 7.5: Alle Tests ausführen**

```bash
cd ticketsystem && python -m pytest tests/ -v
```

Erwartetes Ergebnis: 7 passed, 8 failed.

- [ ] **Step 7.6: Commit**

```bash
git add ticketsystem/routes/_helpers.py
git commit -m "perf: g-Cache-Helper für Active Workers und Teams (einmal pro Request)"
```

---

### Task 8: g-Helper in ticket_views.py einsetzen

**Files:**
- Modify: `ticketsystem/routes/ticket_views.py`

Fünf Stellen in `ticket_views.py` laden Worker/Teams direkt. Alle werden auf die neuen Helper umgestellt.

- [ ] **Step 8.1: Import ergänzen**

Der bestehende Import-Block in `ticket_views.py` (Zeilen 32–38) lautet:
```python
from ._helpers import (
    _check_ticket_access,
    _parse_assignment_ids,
    _parse_callback_due,
    _parse_date,
    _safe_int,
)
```

Ergänze die zwei neuen Helper (nicht ersetzen!):
```python
from ._helpers import (
    _check_ticket_access,
    _parse_assignment_ids,
    _parse_callback_due,
    _parse_date,
    _safe_int,
    get_active_workers,
    get_all_teams,
)
```

- [ ] **Step 8.2: Stelle 1 — Dashboard-View (Zeile 98–99)**

```python
# ALT:
all_workers = Worker.query.filter_by(is_active=True).order_by(Worker.name).all()
all_teams = Team.query.order_by(Team.name).all()

# NEU:
all_workers = get_active_workers()
all_teams = get_all_teams()
```

- [ ] **Step 8.3: Stelle 2 — New-Ticket-View (Zeile 189–190)**

```python
# ALT:
all_workers = Worker.query.filter_by(is_active=True).all()
all_teams = Team.query.all()

# NEU:
all_workers = get_active_workers()
all_teams = get_all_teams()
```

- [ ] **Step 8.4: Stelle 3 — Ticket-Detail-View (Zeile 302–303)**

```python
# ALT:
all_workers = Worker.query.filter_by(is_active=True).all()
all_teams = Team.query.all()

# NEU:
all_workers = get_active_workers()
all_teams = get_all_teams()
```

- [ ] **Step 8.5: Stelle 4 — Workload-View (Zeile 462–464)**

```python
# ALT:
active_workers = (
    Worker.query.filter_by(is_active=True).order_by(Worker.name).all()
)

# NEU:
active_workers = get_active_workers()
```

- [ ] **Step 8.6: Stelle 5 — Dashboard-Rows-API (Zeile 519–520)**

```python
# ALT:
all_workers = Worker.query.filter_by(is_active=True).order_by(Worker.name).all()
all_teams = Team.query.order_by(Team.name).all()

# NEU:
all_workers = get_active_workers()
all_teams = get_all_teams()
```

- [ ] **Step 8.7: Prüfen ob Worker/Team direkt noch importiert werden**

Wenn nach den Änderungen `Worker` oder `Team` in `ticket_views.py` nicht mehr direkt für Queries gebraucht werden, prüfe ob die Imports noch benötigt werden:

```bash
grep -n "Worker\.\|Team\." ticketsystem/routes/ticket_views.py
```

Entferne nur Importe, die tatsächlich nicht mehr vorkommen.

- [ ] **Step 8.8: Tests ausführen**

```bash
cd ticketsystem && python -m pytest tests/ -v
```

Erwartetes Ergebnis: 7 passed, 8 failed.

- [ ] **Step 8.9: Commit**

```bash
git add ticketsystem/routes/ticket_views.py
git commit -m "perf: Worker/Team-Queries in ticket_views.py auf g-Cache-Helper umgestellt"
```

---

## Schicht 5: Short-TTL-Caching

### Task 9: _compute_summary_counts doppelte Berechnung fixen

**Files:**
- Modify: `ticketsystem/routes/dashboard.py:127-170`

`_compute_summary_counts()` berechnet `worker_id`, `team_ids` und `_confidential_filter` zweimal (einmal für Status-Counts, einmal für `max(updated_at)`). Das wird auf einmalige Berechnung konsolidiert.

- [ ] **Step 9.1: Import ergänzen in dashboard.py**

Füge in `ticketsystem/routes/dashboard.py` nach der bestehenden Zeile `from routes.auth import worker_required` hinzu:

```python
from routes._helpers import get_team_ids_for_worker
```

- [ ] **Step 9.2: Funktion konsolidieren**

Ersetze die gesamte `_compute_summary_counts()`-Funktion in `ticketsystem/routes/dashboard.py`:

```python
def _compute_summary_counts() -> Tuple[Dict[str, int], str | None]:
    """Query ticket status counts and last-updated timestamp.

    Returns:
        A tuple of ``(counts_dict, last_updated_iso)``.
    """
    is_elevated = _is_elevated_role()
    worker_id = session.get("worker_id") if not is_elevated else None
    team_ids = get_team_ids_for_worker(worker_id) if worker_id else []
    confidential = (
        db.or_(*_confidential_filter(worker_id, team_ids))
        if not is_elevated and worker_id is not None
        else None
    )

    base_filter = [Ticket.is_deleted.is_(False)]
    if confidential is not None:
        base_filter.append(confidential)

    results = (
        db.session.query(Ticket.status, func.count(Ticket.id))
        .filter(*base_filter)
        .group_by(Ticket.status)
        .all()
    )
    count_map: Dict[str, int] = dict(results)

    last_updated = (
        db.session.query(func.max(Ticket.updated_at))
        .filter(*base_filter)
        .scalar()
    )
    last_iso: str | None = last_updated.isoformat() if last_updated else None

    counts: Dict[str, Any] = {
        TicketStatus.OFFEN.value: count_map.get(TicketStatus.OFFEN.value, 0),
        TicketStatus.IN_BEARBEITUNG.value: count_map.get(
            TicketStatus.IN_BEARBEITUNG.value, 0,
        ),
        TicketStatus.WARTET.value: count_map.get(TicketStatus.WARTET.value, 0),
        "summary": sum(
            cnt for status, cnt in count_map.items()
            if status != TicketStatus.ERLEDIGT.value
        ),
    }
    return counts, last_iso
```

- [ ] **Step 9.3: Tests ausführen**

```bash
cd ticketsystem && python -m pytest tests/ -v
```

Erwartetes Ergebnis: 7 passed, 8 failed.

- [ ] **Step 9.4: Commit**

```bash
git add ticketsystem/routes/dashboard.py
git commit -m "perf: _compute_summary_counts doppelte team_ids/confidential-Berechnung eliminiert"
```

---

### Task 10: cachetools — TTL-Caching für teure Aggregationen

**Files:**
- Modify: `ticketsystem/requirements.txt`
- Modify: `ticketsystem/services/dashboard_service.py`

`get_projects_summary()` und `get_workload_overview()` werden auf Modulebene mit `TTLCache` gecacht. Da sie keine benutzer-spezifischen Parameter haben, genügt ein globaler Cache pro Funktion.

- [ ] **Step 10.1: cachetools in requirements.txt ergänzen**

Füge in `ticketsystem/requirements.txt` als neue letzte Zeile hinzu:

```
cachetools==5.5.2
```

- [ ] **Step 10.2: cachetools installieren**

```bash
cd ticketsystem && pip install cachetools==5.5.2
```

Erwartetes Ergebnis: Successfully installed cachetools.

- [ ] **Step 10.3: TTL-Caches in dashboard_service.py einrichten**

Füge am Anfang von `ticketsystem/services/dashboard_service.py` nach den bestehenden Imports hinzu:

```python
from cachetools import TTLCache
```

Füge direkt darunter, nach dem `_logger = logging.getLogger(__name__)`, die Cache-Objekte hinzu:

```python
# Modul-level TTL-Caches für teure Aggregationen.
# Da beide Funktionen keine benutzer-spezifischen Parameter haben,
# genügt maxsize=1 (ein gecachter Wert pro Cache).
_projects_cache: TTLCache = TTLCache(maxsize=1, ttl=120)   # 2 Minuten
_workload_cache: TTLCache = TTLCache(maxsize=1, ttl=300)   # 5 Minuten
```

- [ ] **Step 10.4: get_projects_summary() mit Cache wrappen**

Ersetze die `get_projects_summary()`-Methode (die in Task 5 neugeschriebene): Füge vor der `from sqlalchemy`-Zeile ein Cache-Check/-Set ein:

```python
@staticmethod
def get_projects_summary() -> List[Dict[str, Any]]:
    """Fetch projects grouped by order_reference with progress.

    Result is cached for 2 minutes (TTL). No explicit invalidation —
    acceptable staleness for the projects overview.
    """
    cached = _projects_cache.get("v")
    if cached is not None:
        return cached

    from sqlalchemy import Float, case, cast

    # ... (der vollständige SQL-Query-Body aus Task 5 bleibt unverändert) ...
    # Am Ende der Methode, vor return:
    result = _finalize_projects(projects)
    _projects_cache["v"] = result
    return result
```

**Vollständige Methode nach der Änderung:**

```python
@staticmethod
def get_projects_summary() -> List[Dict[str, Any]]:
    """Fetch projects grouped by order_reference with progress.

    Result is cached for 2 minutes (TTL). No explicit invalidation —
    acceptable staleness for the projects overview.
    """
    cached = _projects_cache.get("v")
    if cached is not None:
        return cached

    from sqlalchemy import Float, case, cast

    ci = (
        db.session.query(
            ChecklistItem.ticket_id.label("tid"),
            func.count(ChecklistItem.id).label("total"),
            func.sum(
                case((ChecklistItem.is_completed.is_(True), 1), else_=0)
            ).label("done"),
        )
        .group_by(ChecklistItem.ticket_id)
        .subquery()
    )

    rows = (
        db.session.query(
            Ticket.order_reference,
            Ticket.status,
            func.count(Ticket.id).label("cnt"),
            func.max(
                func.coalesce(Ticket.updated_at, Ticket.created_at)
            ).label("last_upd"),
            func.sum(
                case(
                    (
                        ci.c.total > 0,
                        cast(ci.c.done, Float) / cast(ci.c.total, Float),
                    ),
                    (Ticket.status == TicketStatus.ERLEDIGT.value, 1.0),
                    else_=0.0,
                )
            ).label("progress_sum"),
        )
        .outerjoin(ci, Ticket.id == ci.c.tid)
        .filter(
            Ticket.is_deleted.is_(False),
            Ticket.order_reference.isnot(None),
            Ticket.order_reference != "",
        )
        .group_by(Ticket.order_reference, Ticket.status)
        .all()
    )

    projects: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        ref = row.order_reference.strip()
        if not ref:
            continue
        if ref not in projects:
            projects[ref] = {
                "order_reference": ref,
                "total_tickets": 0,
                "completed_tickets": 0,
                "last_updated": None,
                "ticket_progress_sum": 0.0,
                "status_counts": {s.value: 0 for s in TicketStatus},
            }
        p = projects[ref]
        p["total_tickets"] += row.cnt
        p["status_counts"][row.status] = (
            p["status_counts"].get(row.status, 0) + row.cnt
        )
        if row.status == TicketStatus.ERLEDIGT.value:
            p["completed_tickets"] += row.cnt
        p["ticket_progress_sum"] += row.progress_sum or 0.0
        if row.last_upd and (
            not p["last_updated"] or row.last_upd > p["last_updated"]
        ):
            p["last_updated"] = row.last_upd

    result = _finalize_projects(projects)
    _projects_cache["v"] = result
    return result
```

- [ ] **Step 10.5: get_workload_overview() mit Cache wrappen**

Füge am Anfang der `get_workload_overview()`-Methode ein Cache-Check/-Set ein:

```python
@staticmethod
def get_workload_overview() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return workload entries split into absent and present workers.

    Result is cached for 5 minutes (TTL).
    """
    cached = _workload_cache.get("v")
    if cached is not None:
        return cached

    now = get_utc_now()
    # ... (restlicher Body unverändert) ...
    # Am Ende der Methode, vor return:
    result = (absent, present)
    _workload_cache["v"] = result
    return result
```

**Vollständige Methode nach der Änderung:**

```python
@staticmethod
def get_workload_overview() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return workload entries split into absent and present workers.

    Result is cached for 5 minutes (TTL).
    """
    cached = _workload_cache.get("v")
    if cached is not None:
        return cached

    now = get_utc_now()
    today = now.date()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=4)

    tickets = (
        Ticket.query.filter(
            Ticket.is_deleted.is_(False),
            Ticket.status.in_(_OPEN_STATUSES),
            db.or_(
                Ticket.assigned_to_id.isnot(None),
                Ticket.assigned_team_id.isnot(None),
            ),
        )
        .options(
            joinedload(Ticket.assigned_to),
            selectinload(Ticket.assigned_team).selectinload(Team.members),
            selectinload(Ticket.checklists),
        )
        .limit(1000)
        .all()
    )

    tickets_by_worker = _group_tickets_by_worker(tickets)
    workers = Worker.query.filter_by(is_active=True).all()

    absent: List[Dict[str, Any]] = []
    present: List[Dict[str, Any]] = []

    for worker in workers:
        worker_tickets = list(tickets_by_worker.get(worker.id, []))
        if not worker_tickets:
            continue

        entry = _build_workload_entry(
            worker, worker_tickets, today, week_end
        )
        if worker.is_out_of_office:
            absent.append(entry)
        else:
            present.append(entry)

    absent.sort(
        key=lambda x: (-x["critical_count"], -x["open_count"])
    )
    present.sort(key=lambda x: -x["open_count"])

    result = (absent, present)
    _workload_cache["v"] = result
    return result
```

- [ ] **Step 10.6: Tests ausführen**

```bash
cd ticketsystem && python -m pytest tests/ -v
```

Erwartetes Ergebnis: 7 passed, 8 failed.

- [ ] **Step 10.7: Import-Check und Flake8**

```bash
cd ticketsystem && python -c "from app import app"
python -m flake8 --max-line-length=120 *.py routes/ services/
```

Erwartetes Ergebnis: Kein Fehler.

- [ ] **Step 10.8: Commit**

```bash
git add ticketsystem/requirements.txt ticketsystem/services/dashboard_service.py
git commit -m "perf: cachetools TTL-Cache für Projects-Summary (2 min) und Workload-Overview (5 min)"
```

---

## Abschluss

### Task 11: Finaler Verifikations-Lauf

- [ ] **Step 11.1: Vollständige Tests**

```bash
cd ticketsystem && python -m pytest tests/ -v
```

Erwartetes Ergebnis: **7 passed, 8 failed** (Baseline exakt gehalten).

- [ ] **Step 11.2: Import-Check**

```bash
cd ticketsystem && python -c "from app import app; print('OK')"
```

- [ ] **Step 11.3: Flake8**

```bash
cd ticketsystem && python -m flake8 --max-line-length=120 *.py routes/ services/
```

Erwartetes Ergebnis: Keine neuen Warnungen gegenüber der Baseline.

- [ ] **Step 11.4: Migrations-Status prüfen**

```bash
cd ticketsystem && python -m flask db current
```

Erwartetes Ergebnis: `a0b1c2d3e4f5 (head)`.

---

## Spec-Abdeckungs-Check

| Spec-Anforderung | Abgedeckt in |
|---|---|
| Indizes: status, is_deleted, Komposit, assigned_to_id, assigned_team_id, due_date, created_at | Task 1 |
| Indizes: comment.ticket_id, notification.user_id | Task 1 |
| Eager Loading: assigned_team.members in Workload | Task 2 |
| Eager Loading: Ticket.tags (bereits in _base_ticket_query vorhanden — kein Task nötig) | — |
| Eager Loading: scheduler assigned_to | Task 3 |
| Eager Loading: duplicate_ticket | Task 4 |
| Query-Rewrite: get_projects_summary → SQL GROUP BY | Task 5 |
| Query-Rewrite: get_workload_overview LIMIT 1000 | Task 6 |
| g-Cache-Helper: get_active_workers, get_all_teams, get_team_ids_for_worker | Task 7 |
| g-Cache einsetzen in ticket_views.py (5 Stellen) | Task 8 |
| Doppelte Berechnung in _compute_summary_counts fixen | Task 9 |
| cachetools TTL-Cache: get_projects_summary (2 min) | Task 10 |
| cachetools TTL-Cache: get_workload_overview (5 min) | Task 10 |
