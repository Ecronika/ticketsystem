# Performance Optimierungen — Design Spec

**Datum:** 2026-04-12
**Branch:** claude/bug-fixes-audit-2026-04-12
**Kontext:** Flask-Ticketsystem kurz vor Produktiveinsatz. Anwendung fühlt sich an fast allen Stellen langsamer an als nötig. Mit mehr Daten und Nutzern wird das Problem zunehmen.

---

## Problemanalyse

Audit ergab 44 Performance-Probleme in 9 Kategorien. Alle Schichten sind betroffen:
- Fehlende DB-Indizes → Full-Table-Scans bei jedem Filter
- N+1-Query-Probleme in Dashboard und Scheduler
- Python-seitige Aggregation statt SQL GROUP BY
- Unbegrenzte Queries ohne LIMIT
- Mehrfaches Laden identischer Daten (Workers, Teams) pro Request
- Kein Caching für teure, selten ändernde Aggregationen

---

## Ansatz: Bottom-up (Option A)

Fünf Schichten von sicherster zu risikoreichster Änderung, jede unabhängig testbar.

---

## Schicht 1: Datenbank-Indizes

**Datei:** Neue Alembic-Migration `migrations/versions/`

**Neue Indizes:**

| Tabelle | Spalte(n) | Typ | Begründung |
|---------|-----------|-----|------------|
| `ticket` | `status` | Einzelindex | In fast jeder Query im WHERE |
| `ticket` | `is_deleted` | Einzelindex | Ubiquitärer Soft-Delete-Filter |
| `ticket` | `(is_deleted, status)` | Komposit-Index | Häufigste Filterkombination |
| `ticket` | `assigned_to_id` | Einzelindex | Dashboard-Filter, Workload-Übersicht |
| `ticket` | `assigned_team_id` | Einzelindex | Team-Dashboard, Delegation |
| `ticket` | `due_date` | Einzelindex | Scheduler, Eskalations-Queries |
| `ticket` | `created_at` | Einzelindex | Datumsfilter im Dashboard |
| `comment` | `ticket_id` | Einzelindex | Subquery-Join in Suche und Vertraulichkeits-Filter |
| `notification` | `user_id` | Einzelindex | Notification-Queries pro User |

**Zusätzlich:** `checklist_item.ticket_id` prüfen — bei fehlendem Index ergänzen.

**Risiko:** Null. Migration nur additive DDL-Änderungen. Rollback via `alembic downgrade`.

---

## Schicht 2: Eager Loading (N+1 eliminieren)

**Betroffene Dateien:** `services/dashboard_service.py`, `services/scheduler_service.py`, `services/ticket_core_service.py`

### 2.1 `dashboard_service.py` — `_group_tickets_by_worker()`
- Problem: `ticket.assigned_team.members` löst pro Ticket eine separate DB-Query aus
- Fix: `selectinload(Ticket.assigned_team).selectinload(Team.members)` in die Basis-Query

### 2.2 `dashboard_service.py` — alle Dashboard-Queries
- Problem: `ticket.tags` wird lazy geladen wenn das Template Tags rendert
- Fix: `selectinload(Ticket.tags)` in `_base_ticket_query()` aufnehmen

### 2.3 `scheduler_service.py` — `_fetch_overdue_tickets()`
- Problem: `ticket.assigned_to.name` im Eskalations-Loop → N DB-Queries für N Tickets
- Fix: `joinedload(Ticket.assigned_to)` beim Laden der überfälligen Tickets

### 2.4 `ticket_core_service.py` — `duplicate_ticket()`
- Problem: `source.checklists` + `source.tags` werden lazy geladen
- Fix: Quell-Ticket mit `joinedload(Ticket.checklists)` und `joinedload(Ticket.tags)` laden

**Risiko:** Niedrig. Kein fachliches Verhalten ändert sich — nur der Zeitpunkt des Ladens.

---

## Schicht 3: Query-Rewrites

**Betroffene Dateien:** `services/dashboard_service.py`, `services/_ticket_helpers.py`

### 3.1 `get_projects_summary()` → SQL GROUP BY
- Problem: Alle Projekt-Tickets mit Checklisten laden, dann in Python aggregieren
- Fix: SQL-Aggregation mit `GROUP BY ticket.order_reference` + `COUNT` / `SUM(CASE WHEN ...)`
- Ergebnis: Einzelner DB-Roundtrip statt N+1

### 3.2 `get_workload_overview()` → LIMIT
- Problem: `.all()` auf alle offenen Tickets ohne Limit
- Fix: `LIMIT 1000` — schützt vor unbegrenzten Scans nach Go-Live
- Begründung: In der Praxis nie 1.000 gleichzeitig offene Tickets zu erwarten

### 3.3 `apply_search_filter()` → Einzelne Comment-Subquery
- Problem: Pro Suchtoken eine eigene Subquery auf `comment.body`
- Fix: Alle Token-Conditions in eine einzige Subquery (`AND`-verknüpft)

**Risiko:** Mittel. `get_projects_summary()` erfordert sorgfältiges Testen der Aggregationsergebnisse.

---

## Schicht 4: Request-Level-Caching via `flask.g`

**Betroffene Dateien:** `routes/_helpers.py`, `routes/ticket_views.py`, `routes/dashboard.py`

### Neue Helper-Funktionen in `routes/_helpers.py`

```python
def get_active_workers() -> list[Worker]:
    """Workers einmal pro Request laden und in g cachen."""
    if not hasattr(g, "_active_workers"):
        g._active_workers = Worker.query.filter_by(is_active=True).order_by(Worker.name).all()
    return g._active_workers

def get_all_teams() -> list[Team]:
    """Teams einmal pro Request laden und in g cachen."""
    if not hasattr(g, "_all_teams"):
        g._all_teams = Team.query.order_by(Team.name).all()
    return g._all_teams

def get_team_ids_for_worker(worker_id: int) -> list[int]:
    """Team-IDs eines Workers einmal pro Request cachen."""
    if not hasattr(g, "_team_ids"):
        g._team_ids = {}
    if worker_id not in g._team_ids:
        g._team_ids[worker_id] = Team.team_ids_for_worker(worker_id)
    return g._team_ids[worker_id]
```

Alle direkten `Worker.query...` und `Team.query...` Aufrufe in Routen werden auf diese Helper umgestellt.

**Risiko:** Niedrig. Daten leben nur für die Dauer eines Requests — kein Stale-Data-Problem.

---

## Schicht 5: Short-TTL-Caching für teure Aggregationen

**Betroffene Dateien:** `routes/dashboard.py`, `services/dashboard_service.py`
**Neue Abhängigkeit:** `cachetools` (In-Process, kein Redis/Memcached nötig)

| Funktion | TTL | Cache-Key |
|----------|-----|-----------|
| `_compute_summary_counts()` | 30 Sekunden | `worker_id` |
| `get_projects_summary()` | 2 Minuten | `(worker_id, filter_params)` |
| `get_workload_overview()` | 5 Minuten | `worker_id` |

**Cache-Invalidierung:** Bei Ticket-Änderungen (Create, Update, Status-Änderung) wird der betroffene Cache-Eintrag explizit geleert. Kein Stale-Data-Problem für die eigene Session.

**Implementierung:**
```python
from cachetools import TTLCache, cached
_summary_cache = TTLCache(maxsize=50, ttl=30)
```

**Abhängigkeit:** `cachetools` in `requirements.txt` prüfen und ggf. ergänzen.

**Risiko:** Mittel. Cache-Invalidierung muss an allen Mutationspunkten korrekt implementiert sein.

---

## Nicht in Scope

Die folgenden LOW-Severity-Issues werden **nicht** in dieser Runde adressiert:
- Template-seitige Lazy-Loads (`admin_teams.html`, `archive.html`)
- Author-Subquery-Caching in der Suche
- Mehrfache `db.session.get(Worker, ...)` in `ticket_assignment_service.py`
- Archiv-View Pagination-Optimierung

Diese sind messbar, aber vernachlässigbar gegenüber den obigen Fixes.

---

## Testplan

1. `python -m pytest tests/ -v` — Baseline 7 passed / 8 failed muss gehalten werden
2. `python -c "from app import app"` — Import-Check nach jeder Schicht
3. Manuelle Verifikation: Dashboard laden, Ticket erstellen, Suche nutzen, Workload-Seite aufrufen
4. `python -m flake8 --max-line-length=120 *.py routes/ services/` — Keine neuen Linter-Fehler

---

## Reihenfolge der Implementation

1. Schicht 1: Alembic-Migration (Indizes)
2. Schicht 2: Eager Loading
3. Schicht 3: Query-Rewrites
4. Schicht 4: Request-Level-Caching
5. Schicht 5: TTL-Caching + `cachetools`

Jede Schicht: Tests laufen lassen, committen, dann nächste Schicht.
