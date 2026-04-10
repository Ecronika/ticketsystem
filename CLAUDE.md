# CLAUDE.md — Projekt-Richtlinien für KI-gestützte Entwicklung

## Projekt

Flask-basiertes Ticketsystem mit SQLite, SQLAlchemy ORM, Alembic-Migrationen.
Läuft als Home Assistant Add-on hinter NGINX Reverse Proxy.

## Entwicklungsregeln

### Build & Test

```bash
cd ticketsystem
python -c "from app import app"                    # Import-Check
python -m pytest tests/ -v                          # 7 pass, 8 pre-existing failures
python -m flake8 --max-line-length=120 *.py routes/ services/
```

Baseline: **7 passed, 8 failed** (Failures sind bekannte, nicht verwandte Probleme).
Jede Änderung muss diese Baseline halten — keine neuen Failures einführen.

### Git

- Branch: Immer auf dem zugewiesenen Feature-Branch arbeiten
- Commits: Deutsch oder Englisch, Conventional-Commit-Stil (`fix:`, `refactor:`, `feat:`)
- Nie auf `main` direkt pushen

---

## Vermeidbare Code-Fehler (Anti-Patterns aus bisherigen Audits)

Die folgenden Muster wurden in diesem Projekt wiederholt gefunden und behoben.
**Bei jeder Code-Änderung aktiv gegen diese Muster prüfen.**

### 1. Linter-Warnungen unterdrücken statt beheben

**Verboten:** `# noqa`-Kommentare verwenden, um Linter-Fehler zu kaschieren.

```python
# FALSCH — kaschiert den Fehler
Ticket.is_deleted == False  # noqa: E712

# RICHTIG — behebt den Fehler
Ticket.is_deleted.is_(False)
```

Wenn ein Linter warnt, den Code fixen. Wenn der Linter falsch liegt, den
konkreten Grund als Kommentar dokumentieren, nicht pauschal unterdrücken.

### 2. Fassaden-Refactoring (Datenbank ändern, API vergessen)

**Verboten:** Datenbank-Schema normalisieren, aber die Service-/API-Schicht mit
den alten flachen Parametern belassen.

```python
# FALSCH — 22 Einzelparameter, davon 6 die logisch zusammengehören
def create_ticket(title, ..., contact_name, contact_phone, contact_email,
                  contact_channel, callback_requested, callback_due): ...

# RICHTIG — zusammengehörige Felder als DTO bündeln
@dataclass
class ContactInfo:
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    ...

def create_ticket(title, ..., contact: Optional[ContactInfo] = None): ...
```

**Regel:** Wenn Spalten in eine Satelliten-Tabelle extrahiert werden, MUSS die
Service-API diese Gruppierung widerspiegeln. Nie flache Parameter 1:1
durchreichen und intern auf neue Objekte mappen.

### 3. Verstreute Lazy-Initialization statt zentraler Accessor

**Verboten:** An jeder Stelle im Code manuell `if not ticket.X: ticket.X = X()`
schreiben.

```python
# FALSCH — identisches Muster an 6 Stellen verstreut
if not ticket.approval:
    ticket.approval = TicketApproval()
ticket.approval.status = "pending"

# RICHTIG — ein Accessor auf dem Model, alle Stellen nutzen ihn
# In models.py:
def ensure_approval(self) -> "TicketApproval":
    if not self.approval:
        self.approval = TicketApproval()
    return self.approval

# Im Service:
ticket.ensure_approval().status = "pending"
```

**Regel:** Für `uselist=False`-Beziehungen einen `ensure_*()` Accessor auf dem
Model definieren. Nirgendwo sonst direkt instanziieren.

**Achtung:** `ensure_*()` Accessors **nur in Write-Kontexten** aufrufen (Erstellung,
Update). In Read-Kontexten stattdessen `ticket.contact` direkt prüfen (`if ticket.contact:`),
um keine leeren Datensätze versehentlich zu erzeugen.

### 4. Sicherheits-Decorator punktuell statt systematisch prüfen

**Verboten:** Einen fehlenden Decorator nur an der bemängelten Stelle fixen,
ohne alle ähnlichen Stellen zu prüfen.

**Regel:** Bei Decorator-Fixes (`@worker_required`, `@write_required` etc.)
IMMER alle Endpunkte systematisch durchsuchen und verifizieren:

```bash
# Jeder @write_required MUSS einen @worker_required darüber haben
grep -B2 '@write_required' routes/*.py
```

### 5. Lineare Code-Übersetzung ohne fachliches Verständnis

**Verboten:** Bestehenden Code mechanisch auf neue Strukturen übersetzen, ohne
die fachliche Logik zu hinterfragen.

```python
# FALSCH — nur contact.name wird durchsucht, E-Mail/Telefon ignoriert
Ticket.contact.has(TicketContact.name.ilike(pattern))

# RICHTIG — Volltextsuche durchsucht alle relevanten Kontaktfelder
Ticket.contact.has(TicketContact.name.ilike(pattern))
| Ticket.contact.has(TicketContact.email.ilike(pattern))
| Ticket.contact.has(TicketContact.phone.ilike(pattern))
```

**Regel:** Bei jeder Code-Migration fragen: "Was war der fachliche Zweck
dieser Funktion?" — nicht nur "Wie übersetze ich die Syntax?"

### 6. SQLite-Migrationen: PRAGMA und Transaktionen

**Bekannte Falle:** SQLite-spezifische Probleme bei Alembic-Migrationen:

- `PRAGMA foreign_keys=OFF` ist per-Connection und **muss vor der Transaktion**
  gesetzt werden — `op.execute()` innerhalb einer Migration reicht NICHT
- Alembic nimmt "non-transactional DDL" für SQLite an und überspringt COMMIT —
  aber SQLite DDL IST transaktional. Ohne explizites `connection.commit()` in
  `env.py` werden alle Änderungen bei Connection-Close verworfen
- `batch_alter_table` (DROP + RECREATE) schlägt fehl, wenn andere Tabellen
  FK-Referenzen halten — FK-Enforcement muss auf Connection-Ebene deaktiviert sein

**Lösung ist in `migrations/env.py` implementiert — nicht in Einzel-Migrationen
mit PRAGMA-Calls überschreiben.**

### 7. Typ-Änderungen in SQLite (DateTime → Date)

**Bekannte Falle:** SQLite speichert alles als Text. Wenn ein Model-Column von
`DateTime` auf `Date` geändert wird, parst SQLAlchemy's Result-Processor die
bestehenden Strings (`'2026-04-06 00:00:00.000000'`) falsch.

**Regel:** Bei Typ-Änderungen IMMER eine Daten-Migration mitliefern:

```sql
UPDATE ticket SET due_date = substr(due_date, 1, 10)
WHERE due_date IS NOT NULL AND length(due_date) > 10
```

Und alle Tabellen prüfen, die denselben Column-Typ verwenden (z.B. auch
`checklist_item.due_date`).

### 8. Boilerplate-Code statt Decorator/Abstraktion

**Verboten:** Identisches Error-Handling-Pattern an 30+ Stellen kopieren.

```python
# FALSCH — identisches try/except in jeder Methode
try:
    ...
    db.session.commit()
except SQLAlchemyError as exc:
    db.session.rollback()
    current_app.logger.error("Error: %s", exc)
    raise

# RICHTIG — Decorator in services/_helpers.py
@db_transaction
def create_ticket(...): ...

@api_endpoint
def _update_status_api(...): ...
```

### 9. Docstrings die lügen

**Verboten:** Docstrings schreiben die nicht zur Implementierung passen.

```python
# FALSCH — behauptet "midnight", gibt aber ein date-Objekt zurück
def _parse_date(raw):
    """Parse a date string, setting time to midnight."""
    return datetime.strptime(clean, fmt).date()

# RICHTIG — beschreibt was tatsächlich passiert
def _parse_date(raw):
    """Parse a date string; return a date object or None."""
```

### 10. Dead Code und Pseudo-Entfernung

**Verboten:**
- Auskommentierter Code stehen lassen (`# old_function()`)
- Variablen mit Underscore-Prefix umbenennen statt löschen (`_unused_var = ...`)
- Leere Fallback-Funktionen die nie aufgerufen werden
- Re-Exports von Dingen die nirgends importiert werden

**Regel:** Ungenutzten Code vollständig entfernen. Git ist die History.

### 11. Fassaden mit `staticmethod`-Zuweisungen

**Verboten:** Fassaden-Klassen die nur `staticmethod`-Zuweisungen enthalten:

```python
# FALSCH — bricht IDE Type-Hinting, Go-To-Definition, Autocomplete
class TicketService:
    create_ticket = staticmethod(TicketCoreService.create_ticket)
    assign_ticket = staticmethod(TicketAssignmentService.assign_ticket)
```

```python
# RICHTIG — fokussierte Services direkt importieren
from services.ticket_core_service import TicketCoreService
from services.ticket_assignment_service import TicketAssignmentService
```

**Regel:** Keine Fassaden-Klassen als Backward-Compatibility-Shim. Aufrufer
importieren die fokussierten Service-Module direkt. Wenn Utilities
(`ContactInfo`, `TicketFilterSpec`) in mehreren Modulen gebraucht werden,
werden sie aus ihrem Definitionsort (`_ticket_helpers.py`) importiert, nicht
über Re-Exports.

### 12. Duplizierte Query-Logik

**Verboten:** Identische Datenbankabfragen in mehreren Dateien kopieren.

```python
# FALSCH — gleiche Volltext-Suchlogik in dashboard_service.py UND ticket_export.py
for token in tokens:
    query = query.filter(
        Ticket.title.ilike(pattern) | Ticket.contact.has(...)
    )

# RICHTIG — eine zentrale Funktion in _ticket_helpers.py
from services._ticket_helpers import apply_search_filter
query = apply_search_filter(query, search_term)
```

**Regel:** Query-Logik die an mehr als einer Stelle gebraucht wird gehört in
`services/_ticket_helpers.py` als benannte Funktion.

### 13. Unvollständige Objekt-Kopien (Satelliten-Tabellen)

**Verboten:** Beim Duplizieren/Klonen von Tickets nur einen Teil der
Satelliten-Tabellen kopieren.

**Regel:** Wenn Ticket-Duplikation implementiert wird, ALLE relevanten
1-to-1-Beziehungen prüfen und explizit kopieren:
- `TicketContact` — Kontaktdaten
- `TicketRecurrence` — Serien-Regeln
- Tags (many-to-many)
- Checklists (1-to-many, nur offene Items)
- `due_date`, `reminder_date` — Scalar-Felder

`TicketApproval` wird bewusst NICHT kopiert (neues Ticket = kein Freigabe-Status).

### 14. Exception-Handling: Alle Schichten abdecken

**Verboten:** Error-Handling nur für API-Endpunkte (`@api_endpoint`) implementieren,
aber View-Routen (HTML) ungeschützt lassen.

**Regel:** `DomainError`-Exceptions müssen in ALLEN Schichten gefangen werden:
- API-Endpunkte: `@api_endpoint` Decorator → JSON-Fehlerantwort
- View-Routen: Flask `@app.errorhandler(DomainError)` → HTML-Fehlerseite oder
  JSON-Antwort je nach Content-Negotiation (AJAX vs. Browser-Request)

---

## Architektur-Übersicht

### Satelliten-Tabellen (1-to-1 auf Ticket)

| Tabelle | Accessor (nur Write) | Zweck |
|---------|---------------------|-------|
| `ticket_contact` | `ticket.ensure_contact()` | Kundenkontaktdaten |
| `ticket_approval` | `ticket.ensure_approval()` | Freigabe-Workflow |
| `ticket_recurrence` | `ticket.ensure_recurrence(rule, next_date)` | Wiederholungsregeln |

### Service-Architektur

Fokussierte Service-Module (kein Fassaden-Pattern):

| Modul | Klasse | Verantwortung |
|-------|--------|---------------|
| `ticket_core_service.py` | `TicketCoreService` | CRUD, Kommentare, Status, Duplikation |
| `ticket_assignment_service.py` | `TicketAssignmentService` | Zuweisung, OOO-Delegation |
| `ticket_approval_service.py` | `TicketApprovalService` | Freigabe-Workflow |
| `checklist_service.py` | `ChecklistService` | Checklisten-Operationen |
| `dashboard_service.py` | `DashboardService` | Dashboard-Queries, Projekte, Workload |

Aufrufer importieren die fokussierten Services direkt — keine Fassaden-Klasse.

### Service-DTOs und Shared Helpers (in `_ticket_helpers.py`)

| Export | Typ | Verwendet in |
|--------|-----|-------------|
| `TicketFilterSpec` | Dataclass | `DashboardService.get_dashboard_tickets()` |
| `ContactInfo` | Dataclass | `TicketCoreService.create_ticket()` |
| `apply_search_filter` | Funktion | `DashboardService`, `ticket_export.py` |
| `_confidential_filter` | Funktion | `dashboard.py`, `ticket_export.py` |
| `_urgency_score` | Funktion | `ticket_views.py`, `scheduler_service.py` |

### Decorator-Stack für API-Endpunkte

Reihenfolge auf der Funktionsdefinition (von oben nach unten):
```python
@worker_required      # Auth-Check: Benutzer eingeloggt?
@write_required       # Berechtigung: Darf schreiben?
@limiter.limit(...)   # Rate-Limiting (optional)
@api_endpoint         # Error-Handling: DomainError→status_code, ValueError→400, SQLAlchemyError→500
def _my_api(...):
```

Ausnahme: `_new_ticket_view` hat bewusst KEINEN `@worker_required` —
anonyme Ticket-Erstellung ist gewollt.

Zusätzlich: Flask-Error-Handler `@app.errorhandler(DomainError)` für
View-Routen (HTML) und AJAX-Requests.
# Project Rules

## Dockerfile Sync (Home Assistant Addon)

The file `ticketsystem/Dockerfile` explicitly copies each top-level `.py` file
(it does NOT use `COPY *.py .`). Directories (`routes/`, `services/`, etc.)
are copied whole.

**When creating a new top-level `.py` file:** Add a corresponding `COPY` line
to the Dockerfile.

**When deleting a top-level `.py` file:** Remove the corresponding `COPY` line
from the Dockerfile.

**When creating/deleting files inside `routes/` or `services/`:** No Dockerfile
change needed -- those directories are copied entirely.

## Testing

- Run tests from `ticketsystem/`: `cd ticketsystem && python -m pytest tests/ -v`
- Tests use in-memory SQLite; all 15 tests must pass after any change
- Worker PINs in tests must NOT be in the weak-PIN blocklist (`_WEAK_PINS` in
  `services/worker_service.py`). Use PINs like "7391", "8264", "9173".

## Architecture

- Services use `@staticmethod` + `@db_transaction` decorators
- Domain exceptions live in `exceptions.py` (not inline `ValueError`)
- Focused service modules imported directly (no facade class)
- Single `main_bp` Blueprint; each route sub-module exports `register_routes(bp)`
- Route registration in `routes/__init__.py` — flat structure, no coordinator files
- Shared query/filter helpers live in `services/_ticket_helpers.py`
- German-language UI text in all user-facing messages and audit comments
- `db.session.commit()` belongs in service methods with `@db_transaction`, not in routes
