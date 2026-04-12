# Public REST API (HalloPetra-Webhook) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integration eines öffentlichen Webhook-Endpunkts für das externe KI-Telefonsystem HalloPetra, mit API-Key-Auth, IP-Allowlist, Admin-UI, Audit-Log und DSGVO-konformer Transkript-Speicherung.

**Architecture:** Neuer, vom `main_bp` isolierter `api_bp` Blueprint mit eigener Decorator-Kette. Cloudflare Tunnel als alleiniger öffentlicher Eingang; NGINX exponiert ausschließlich `/api/v1/*`. Vier neue Tabellen (`api_key`, `api_key_ip_range`, `api_audit_log`, `ticket_transcript`) und zwei Spalten auf `ticket` (`external_call_id`, `external_metadata`). Synchrone Ticket-Erzeugung mit `external_call_id` als Idempotenz-Schlüssel.

**Tech Stack:** Flask, SQLAlchemy, Alembic, pydantic v2 (neu), flask-limiter (bestehend), cloudflared, NGINX, SQLite, pytest.

**Spec:** [docs/superpowers/specs/2026-04-12-public-api-hallopetra-design.md](../specs/2026-04-12-public-api-hallopetra-design.md)

---

## File Structure

### Neue Dateien

| Pfad | Verantwortung |
|---|---|
| `ticketsystem/routes/api/__init__.py` | `api_bp` Blueprint, `register_routes(app)` |
| `ticketsystem/routes/api/_decorators.py` | `@api_key_required`, `@require_scope`, `@api_rate_limit`, `@api_endpoint_json` |
| `ticketsystem/routes/api/_errors.py` | JSON-Error-Handler für DomainError, ValidationError, HTTPException |
| `ticketsystem/routes/api/_schemas.py` | Pydantic-Schemas (`HalloPetraWebhookPayload` etc.) |
| `ticketsystem/routes/api/webhook_routes.py` | `POST /api/v1/webhook/calls` |
| `ticketsystem/routes/api/ticket_routes.py` | Platzhalter für Phase b/c (leer mit Kommentar) |
| `ticketsystem/routes/api/health_routes.py` | `GET /api/v1/health` |
| `ticketsystem/routes/admin_api_keys.py` | Admin-UI-Routen für Key-Verwaltung + Audit-Viewer |
| `ticketsystem/services/api_key_service.py` | Create/Revoke/Lookup/Hash/IP-Check/Audit |
| `ticketsystem/services/api_ticket_factory.py` | Payload → Ticket-Mapping (separat vom `TicketCoreService` testbar) |
| `ticketsystem/services/api_retention_service.py` | Retention-Jobs für `api_audit_log` + `ticket_transcript` |
| `ticketsystem/templates/admin/api_keys_list.html` | Liste der API-Schlüssel |
| `ticketsystem/templates/admin/api_key_form.html` | Erstellen/Bearbeiten |
| `ticketsystem/templates/admin/api_key_created.html` | Einmalige Klartext-Anzeige |
| `ticketsystem/templates/admin/api_audit_log.html` | Audit-Log-Viewer |
| `ticketsystem/templates/admin/api_docs.html` | Statische API-Dokumentation |
| `ticketsystem/migrations/versions/<hash>_public_api_phase_a.py` | Alembic-Migration für alle neuen Strukturen |
| `ticketsystem/tests/test_api_auth.py` | Decorator-Kette |
| `ticketsystem/tests/test_api_webhook.py` | End-to-End-Payload |
| `ticketsystem/tests/test_api_idempotency.py` | Idempotenz (sync + parallel) |
| `ticketsystem/tests/test_api_rate_limit.py` | Rate-Limit pro Key |
| `ticketsystem/tests/test_api_ip_allowlist.py` | CIDR-Matching |
| `ticketsystem/tests/test_api_audit_log.py` | Outcomes + Retention |
| `ticketsystem/tests/test_api_key_service.py` | Service-Isolation |
| `ticketsystem/tests/test_api_ticket_factory.py` | Payload-Mapping |
| `ticketsystem/tests/test_admin_api_keys_ui.py` | UI-Routen, Berechtigung, Einmal-Anzeige |
| `docs/operations/public-api-handbook.md` | Betriebshandbuch |
| `docs/operations/api-prelaunch-checklist.md` | Pre-Launch-Checkliste |
| `docs/operations/webadmin-dns-instructions.md` | DNS-Anleitung für Webadmin |
| `ticketsystem/cloudflared/config.yml.example` | Tunnel-Ingress-Regeln (Beispiel-Template) |

### Zu ändernde Dateien

| Pfad | Änderung |
|---|---|
| `ticketsystem/models.py` | 4 neue Modelle + 2 Spalten auf `Ticket` |
| `ticketsystem/app.py` | `api_bp` registrieren, `MAX_CONTENT_LENGTH`, `after_request` für API-Audit |
| `ticketsystem/routes/__init__.py` | Unverändert (api_bp lebt außerhalb) |
| `ticketsystem/services/scheduler_service.py` | Retention-Jobs registrieren |
| `ticketsystem/exceptions.py` | Neue `ApiKeyError`-Hierarchie |
| `ticketsystem/requirements.txt` | `pydantic>=2.0` ergänzen |
| `ticketsystem/Dockerfile` | **Nichts** — alle neuen Dateien liegen in Unterverzeichnissen |
| `ticketsystem/templates/admin/base_admin.html` (oder äquivalent) | Neuer Menü-Eintrag „API-Zugriff" |
| NGINX-Config (HA-Add-on) | Location-Block `/api/v1/`, Security-Header |

---

## Phase 0 — Vor-Schritte (eigenständig, vor allem anderen)

Diese Tasks sind **operational** und laufen **vor** der Code-Implementierung. Sie werden nicht von einem Entwicklungs-Agenten ausgeführt, sondern vom Betreiber durchgeführt. Der Vollständigkeit halber hier dokumentiert, damit sie nicht vergessen werden.

### Task 0.1: SECRET_KEY rotieren

- [ ] **Step 1:** 64-Byte Random-Secret generieren:
  ```bash
  python -c "import secrets; print(secrets.token_hex(64))"
  ```
- [ ] **Step 2:** HA-Add-on-Secret `flask_secret_key` auf neuen Wert setzen (über HA-UI bzw. `secrets.yaml`).
- [ ] **Step 3:** Add-on neu starten. Alle 4 aktiven Worker informieren, dass sie sich neu anmelden müssen.
- [ ] **Step 4:** Verifikation: Login mit einem Worker funktioniert, Dashboard lädt.

### Task 0.2: SQLite-Backup-Cron einrichten

- [ ] **Step 1:** Backup-Script `scripts/backup_sqlite.sh` schreiben:
  ```bash
  #!/bin/bash
  set -e
  TS=$(date +%Y%m%d_%H%M%S)
  SRC=/data/ticketsystem.db
  DEST=/backup/ticketsystem_${TS}.db
  sqlite3 "$SRC" ".backup '$DEST'"
  find /backup -name 'ticketsystem_*.db' -mtime +14 -delete
  ```
- [ ] **Step 2:** Cron-Eintrag (HA-spezifisch, z. B. via automation oder cron-Add-on): täglich 03:00.
- [ ] **Step 3:** Manuelle Ausführung testen. Verifikation: Datei in `/backup` vorhanden, Integrität via `sqlite3 backup.db "PRAGMA integrity_check;"` → `ok`.
- [ ] **Step 4:** 14-Tage-Retention verifizieren (via `touch -d '15 days ago' /backup/test.db`, dann Script laufen lassen, Test-Datei weg).

### Task 0.3: Dependency-Audit

- [ ] **Step 1:** `pip-audit` oder `safety check` im `ticketsystem/`-Verzeichnis ausführen.
- [ ] **Step 2:** Alle Findings mit Schweregrad HIGH oder CRITICAL adressieren (Paket-Update).
- [ ] **Step 3:** Pytest-Baseline danach prüfen: `python -m pytest tests/ -v` → 7 passed, 8 known failures.
- [ ] **Step 4:** Findings-Report nach `docs/operations/dependency-audit-YYYY-MM-DD.md` committen.

---

## Phase 1 — Datenmodell & Migration

### Task 1.1: Domain-Exceptions definieren

**Files:**
- Modify: `ticketsystem/exceptions.py`

- [ ] **Step 1: Bestehende exceptions.py lesen**

Run: `head -60 ticketsystem/exceptions.py`
Ziel: `DomainError`-Basisklasse + Vererbungs-Pattern verstehen.

- [ ] **Step 2: Neue Exceptions ergänzen (am Ende der Datei)**

```python
class ApiKeyError(DomainError):
    """Base class for API-key related errors."""
    status_code = 401


class InvalidApiKey(ApiKeyError):
    """Generic invalid or missing API key."""
    def __init__(self):
        super().__init__("unauthorized")


class IpNotAllowed(ApiKeyError):
    """Source IP is not in the key's allowlist."""
    status_code = 403
    def __init__(self):
        super().__init__("forbidden")


class ScopeDenied(ApiKeyError):
    """Key does not have the required scope."""
    status_code = 403
    def __init__(self, scope: str):
        self.scope = scope
        super().__init__("forbidden")
```

- [ ] **Step 3: Commit**

```bash
git add ticketsystem/exceptions.py
git commit -m "feat: ApiKeyError-Exception-Hierarchie für Public API"
```

### Task 1.2: Modelle — Ticket-Erweiterungen

**Files:**
- Modify: `ticketsystem/models.py` (im `Ticket`-Klassenblock)

- [ ] **Step 1: Zwei neue Spalten zur `Ticket`-Klasse hinzufügen**

An passende Stelle im `Ticket`-Model (nach den bestehenden Spalten, vor den Relationships):

```python
    external_call_id = db.Column(db.String(64), nullable=True, unique=True, index=True)
    external_metadata = db.Column(db.Text, nullable=True)  # JSON-serialisiert
```

- [ ] **Step 2: Helper-Methoden auf `Ticket` ergänzen**

```python
    def get_external_metadata(self) -> dict:
        """Parse external_metadata JSON, return empty dict on None/invalid."""
        if not self.external_metadata:
            return {}
        try:
            import json
            return json.loads(self.external_metadata)
        except (ValueError, TypeError):
            return {}

    def set_external_metadata(self, data: dict) -> None:
        """Serialize *data* as JSON into external_metadata."""
        import json
        self.external_metadata = json.dumps(data, ensure_ascii=False) if data else None
```

- [ ] **Step 3: Import-Check**

Run: `cd ticketsystem && python -c "from app import app; from models import Ticket; print(Ticket.__table__.columns.keys())"`
Expected: Liste enthält `external_call_id` und `external_metadata`.

- [ ] **Step 4: Commit**

```bash
git add ticketsystem/models.py
git commit -m "feat: Ticket.external_call_id + external_metadata für API-Integration"
```

### Task 1.3: Modell — ApiKey

**Files:**
- Modify: `ticketsystem/models.py` (neuer Block)

- [ ] **Step 1: ApiKey-Modell am Ende von models.py anfügen**

```python
# ---------------------------------------------------------------------------
# API Keys (Public REST API)
# ---------------------------------------------------------------------------

class ApiKey(db.Model):
    """API key for the public REST API (Phase a: write:tickets)."""

    __tablename__ = "api_key"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    key_prefix = db.Column(db.String(12), nullable=False, index=True)
    key_hash = db.Column(db.String(128), nullable=False, unique=True)
    scopes = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    rate_limit_per_minute = db.Column(db.Integer, nullable=False, default=60)
    expected_webhook_id = db.Column(db.String(128), nullable=True)
    default_assignee_worker_id = db.Column(
        db.Integer, db.ForeignKey("worker.id"), nullable=True
    )
    create_confidential_tickets = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=get_utc_now)
    created_by_worker_id = db.Column(
        db.Integer, db.ForeignKey("worker.id"), nullable=False
    )
    last_used_at = db.Column(db.DateTime, nullable=True)
    last_used_ip = db.Column(db.String(45), nullable=True)
    revoked_at = db.Column(db.DateTime, nullable=True)
    revoked_by_worker_id = db.Column(
        db.Integer, db.ForeignKey("worker.id"), nullable=True
    )
    expires_at = db.Column(db.DateTime, nullable=True)

    default_assignee = db.relationship(
        "Worker", foreign_keys=[default_assignee_worker_id]
    )
    ip_ranges = db.relationship(
        "ApiKeyIpRange",
        back_populates="api_key",
        cascade="all, delete-orphan",
        order_by="ApiKeyIpRange.created_at",
    )

    def scope_list(self) -> List[str]:
        """Return scopes as a list."""
        return [s.strip() for s in (self.scopes or "").split(",") if s.strip()]

    def has_scope(self, scope: str) -> bool:
        return scope in self.scope_list()

    def is_usable(self) -> bool:
        """True if key is active, not revoked, not expired."""
        if not self.is_active or self.revoked_at is not None:
            return False
        if self.expires_at is not None and self.expires_at <= get_utc_now():
            return False
        return True
```

- [ ] **Step 2: Commit**

```bash
git add ticketsystem/models.py
git commit -m "feat: ApiKey-Modell für öffentliche API-Authentifizierung"
```

### Task 1.4: Modell — ApiKeyIpRange

**Files:**
- Modify: `ticketsystem/models.py`

- [ ] **Step 1: ApiKeyIpRange direkt nach ApiKey anfügen**

```python
class ApiKeyIpRange(db.Model):
    """CIDR allowlist entry for an API key."""

    __tablename__ = "api_key_ip_range"

    id = db.Column(db.Integer, primary_key=True)
    api_key_id = db.Column(
        db.Integer,
        db.ForeignKey("api_key.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cidr = db.Column(db.String(43), nullable=False)
    note = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=get_utc_now)
    created_by_worker_id = db.Column(
        db.Integer, db.ForeignKey("worker.id"), nullable=False
    )

    api_key = db.relationship("ApiKey", back_populates="ip_ranges")
```

- [ ] **Step 2: Commit**

```bash
git add ticketsystem/models.py
git commit -m "feat: ApiKeyIpRange-Modell für IP-Allowlist"
```

### Task 1.5: Modell — ApiAuditLog

**Files:**
- Modify: `ticketsystem/models.py`

- [ ] **Step 1: ApiAuditLog nach ApiKeyIpRange anfügen**

```python
class ApiAuditLog(db.Model):
    """Audit log entry for every API request (auth attempts + successes)."""

    __tablename__ = "api_audit_log"

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=get_utc_now, index=True)
    api_key_id = db.Column(
        db.Integer, db.ForeignKey("api_key.id"), nullable=True
    )
    key_prefix = db.Column(db.String(12), nullable=True)
    source_ip = db.Column(db.String(45), nullable=False)
    method = db.Column(db.String(8), nullable=False)
    path = db.Column(db.String(255), nullable=False)
    status_code = db.Column(db.Integer, nullable=False)
    latency_ms = db.Column(db.Integer, nullable=False)
    outcome = db.Column(db.String(32), nullable=False)
    external_ref = db.Column(db.String(64), nullable=True, index=True)
    assignment_method = db.Column(db.String(24), nullable=True)
    request_id = db.Column(db.String(36), nullable=False)
    error_detail = db.Column(db.Text, nullable=True)

    api_key = db.relationship("ApiKey")
```

- [ ] **Step 2: Commit**

```bash
git add ticketsystem/models.py
git commit -m "feat: ApiAuditLog-Modell für forensische Nachvollziehbarkeit"
```

### Task 1.6: Modell — TicketTranscript

**Files:**
- Modify: `ticketsystem/models.py`

- [ ] **Step 1: TicketTranscript anfügen**

```python
class TicketTranscript(db.Model):
    """Conversation transcript entry belonging to a ticket.

    Separate table so retention (90d) can differ from ticket retention.
    """

    __tablename__ = "ticket_transcript"

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(
        db.Integer,
        db.ForeignKey("ticket.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position = db.Column(db.Integer, nullable=False)
    role = db.Column(db.String(16), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=get_utc_now)
```

- [ ] **Step 2: Relationship in `Ticket`-Klasse ergänzen**

Im `Ticket`-Block (nahe bestehender Relationships wie `contact`, `approval`):

```python
    transcripts = db.relationship(
        "TicketTranscript",
        backref="ticket",
        cascade="all, delete-orphan",
        order_by="TicketTranscript.position",
    )
```

- [ ] **Step 3: Import-Check**

Run: `cd ticketsystem && python -c "from app import app; from models import ApiKey, ApiKeyIpRange, ApiAuditLog, TicketTranscript; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add ticketsystem/models.py
git commit -m "feat: TicketTranscript-Modell mit cascade-delete und 1:n Relationship"
```

### Task 1.7: Alembic-Migration erstellen

**Files:**
- Create: `ticketsystem/migrations/versions/<hash>_public_api_phase_a.py`

- [ ] **Step 1: Migration generieren**

Run: `cd ticketsystem && alembic revision --autogenerate -m "public_api_phase_a"`

Dies erzeugt eine Datei in `migrations/versions/`. Hash aus Ausgabe notieren.

- [ ] **Step 2: Autogenerierte Migration prüfen und korrigieren**

Die Migration sollte enthalten:
- `op.create_table('api_key', ...)` mit allen Spalten aus Task 1.3
- `op.create_table('api_key_ip_range', ...)` mit FK + CASCADE
- `op.create_table('api_audit_log', ...)` mit Indexes
- `op.create_table('ticket_transcript', ...)` mit FK + CASCADE
- `op.add_column('ticket', sa.Column('external_call_id', ...))` + Unique-Index
- `op.add_column('ticket', sa.Column('external_metadata', sa.Text(), ...))`

**Häufige Korrekturen:**
- `nullable=False`-Spalten auf bestehender `ticket`-Tabelle brauchen `server_default` oder eine Daten-Migration. Die neuen Spalten sind `nullable=True` (kein Problem).
- Indexes explizit mit `op.create_index(...)` ergänzen falls Autogenerate sie übersehen hat.
- CASCADE-Option auf FKs prüfen:
  ```python
  sa.ForeignKeyConstraint(['ticket_id'], ['ticket.id'], ondelete='CASCADE')
  ```

- [ ] **Step 3: Migration auf Kopie der Prod-DB testen**

```bash
cp /data/ticketsystem.db /tmp/test.db
DATABASE_URL=sqlite:////tmp/test.db alembic upgrade head
sqlite3 /tmp/test.db ".schema api_key"
sqlite3 /tmp/test.db ".schema ticket_transcript"
```

Expected: Tabellen sauber erstellt, Indexes vorhanden.

- [ ] **Step 4: Downgrade testen**

```bash
DATABASE_URL=sqlite:////tmp/test.db alembic downgrade -1
sqlite3 /tmp/test.db ".tables" | grep -E 'api_key|transcript'
```

Expected: Keine Ausgabe (alle neuen Tabellen weg).

- [ ] **Step 5: Commit**

```bash
git add ticketsystem/migrations/versions/
git commit -m "feat: Alembic-Migration für Public-API-Phase-a Strukturen"
```

### Task 1.8: Baseline-Tests laufen lassen

- [ ] **Step 1:**

Run: `cd ticketsystem && python -m pytest tests/ -v 2>&1 | tail -20`
Expected: **7 passed, 8 failed** (Baseline aus CLAUDE.md).

Falls neue Failures auftauchen: Migration debuggen, nicht weitermachen.

- [ ] **Step 2: Flake-Check**

Run: `cd ticketsystem && python -m flake8 --max-line-length=120 models.py exceptions.py`
Expected: Keine Ausgabe oder nur pre-existing Warnings.

---

## Phase 2 — ApiKeyService

### Task 2.1: Test-Datei anlegen

**Files:**
- Create: `ticketsystem/tests/test_api_key_service.py`

- [ ] **Step 1: Datei mit Test-Gerüst schreiben**

```python
"""Tests for services/api_key_service.py."""

import hashlib

import pytest

from models import ApiKey, ApiKeyIpRange, Worker
from services.api_key_service import ApiKeyService
from exceptions import InvalidApiKey, IpNotAllowed


@pytest.fixture
def admin_worker(app, db_session):
    """Create an admin worker for key-creation audit trail."""
    w = Worker(name="TestAdmin", is_admin=True, is_active=True, role="ADMIN")
    w.set_pin("7391")  # adjust to bestehende API
    db_session.add(w)
    db_session.commit()
    return w


@pytest.fixture
def default_assignee(app, db_session):
    w = Worker(name="Rezeption", is_active=True, role="WORKER")
    w.set_pin("8264")
    db_session.add(w)
    db_session.commit()
    return w
```

Die Fixtures `app` und `db_session` stammen aus `conftest.py` (bestehend). Die `set_pin`-API an bestehendem Worker-Modell anpassen (falls anders benannt).

- [ ] **Step 2: Commit**

```bash
git add ticketsystem/tests/test_api_key_service.py
git commit -m "test: Gerüst für ApiKeyService-Tests"
```

### Task 2.2: Test — Key erstellen gibt Klartext-Token einmalig zurück

- [ ] **Step 1: Test schreiben**

```python
def test_create_returns_plaintext_token_once(app, db_session, admin_worker, default_assignee):
    key, plaintext = ApiKeyService.create_key(
        name="HalloPetra Prod",
        scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60,
        created_by_worker_id=admin_worker.id,
    )
    assert plaintext.startswith("tsk_")
    assert len(plaintext) == 52  # "tsk_" + 48 chars
    assert key.key_prefix == plaintext[:12]
    # Hash stimmt
    expected_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    assert key.key_hash == expected_hash
    # Klartext wird NICHT gespeichert
    assert plaintext not in str(key.__dict__.values())
```

- [ ] **Step 2: Run, verify FAIL**

Run: `cd ticketsystem && python -m pytest tests/test_api_key_service.py::test_create_returns_plaintext_token_once -v`
Expected: `ImportError: cannot import name 'ApiKeyService'`

### Task 2.3: ApiKeyService — minimale Implementierung

**Files:**
- Create: `ticketsystem/services/api_key_service.py`

- [ ] **Step 1: Service-Datei schreiben**

```python
"""Service for API-key management (public REST API)."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from flask import current_app
from sqlalchemy import and_

from exceptions import InvalidApiKey, IpNotAllowed
from extensions import db
from models import ApiKey, ApiKeyIpRange, ApiAuditLog
from services._helpers import db_transaction
from utils import get_utc_now


TOKEN_PREFIX = "tsk_"
TOKEN_RANDOM_LENGTH = 48  # characters (not bytes)
_ALPHABET = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
)
_KEY_PREFIX_LENGTH = 12  # len("tsk_") + 8


def _generate_token() -> str:
    body = "".join(secrets.choice(_ALPHABET) for _ in range(TOKEN_RANDOM_LENGTH))
    return f"{TOKEN_PREFIX}{body}"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _is_valid_format(token: str) -> bool:
    if not token.startswith(TOKEN_PREFIX):
        return False
    expected_len = len(TOKEN_PREFIX) + TOKEN_RANDOM_LENGTH
    if len(token) != expected_len:
        return False
    body = token[len(TOKEN_PREFIX):]
    return all(c in _ALPHABET for c in body)


class ApiKeyService:
    """Static-method service for API key lifecycle."""

    @staticmethod
    @db_transaction
    def create_key(
        name: str,
        scopes: List[str],
        default_assignee_id: Optional[int],
        rate_limit_per_minute: int,
        created_by_worker_id: int,
        expected_webhook_id: Optional[str] = None,
        create_confidential_tickets: bool = True,
        expires_at: Optional[datetime] = None,
    ) -> Tuple[ApiKey, str]:
        """Create a new API key. Returns (key, plaintext_token).

        The plaintext is returned ONCE and never stored.
        """
        if not name or not name.strip():
            raise ValueError("Name darf nicht leer sein.")
        if not scopes:
            raise ValueError("Mindestens ein Scope erforderlich.")
        if "write:tickets" in scopes and default_assignee_id is None:
            raise ValueError(
                "Für Scope 'write:tickets' ist ein Standard-Zuweisungs-Worker Pflicht."
            )
        if rate_limit_per_minute < 1:
            raise ValueError("Rate-Limit muss mindestens 1 sein.")

        token = _generate_token()
        key = ApiKey(
            name=name.strip(),
            key_prefix=token[:_KEY_PREFIX_LENGTH],
            key_hash=_hash_token(token),
            scopes=",".join(scopes),
            rate_limit_per_minute=rate_limit_per_minute,
            default_assignee_worker_id=default_assignee_id,
            expected_webhook_id=expected_webhook_id,
            create_confidential_tickets=create_confidential_tickets,
            created_by_worker_id=created_by_worker_id,
            expires_at=expires_at,
        )
        db.session.add(key)
        db.session.commit()
        return key, token
```

- [ ] **Step 2: Run, verify PASS**

Run: `cd ticketsystem && python -m pytest tests/test_api_key_service.py::test_create_returns_plaintext_token_once -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add ticketsystem/services/api_key_service.py ticketsystem/tests/test_api_key_service.py
git commit -m "feat: ApiKeyService.create_key mit einmaliger Klartext-Rückgabe"
```

### Task 2.4: Test — Key-Lookup via Token

- [ ] **Step 1: Test ergänzen**

```python
def test_lookup_by_token_returns_key(app, db_session, admin_worker, default_assignee):
    key, plaintext = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_worker.id,
    )
    result = ApiKeyService.authenticate(plaintext)
    assert result.id == key.id


def test_lookup_wrong_token_raises_invalid(app, db_session, admin_worker, default_assignee):
    ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_worker.id,
    )
    with pytest.raises(InvalidApiKey):
        ApiKeyService.authenticate("tsk_" + "x" * 48)


def test_lookup_invalid_format_raises_invalid(app, db_session):
    with pytest.raises(InvalidApiKey):
        ApiKeyService.authenticate("not_a_token")
    with pytest.raises(InvalidApiKey):
        ApiKeyService.authenticate("")
    with pytest.raises(InvalidApiKey):
        ApiKeyService.authenticate(None)


def test_lookup_revoked_key_raises_invalid(app, db_session, admin_worker, default_assignee):
    key, plaintext = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_worker.id,
    )
    ApiKeyService.revoke_key(key.id, revoked_by_worker_id=admin_worker.id)
    with pytest.raises(InvalidApiKey):
        ApiKeyService.authenticate(plaintext)
```

- [ ] **Step 2: Run, verify FAIL**

Expected: `AttributeError: ApiKeyService has no 'authenticate'`.

- [ ] **Step 3: `authenticate` + `revoke_key` implementieren**

Im `ApiKeyService` ergänzen:

```python
    @staticmethod
    def authenticate(token: Optional[str]) -> ApiKey:
        """Look up and validate an API key by its plaintext token.

        Raises InvalidApiKey for any authentication failure (generic).
        """
        if not token or not isinstance(token, str):
            raise InvalidApiKey()
        if not _is_valid_format(token):
            raise InvalidApiKey()
        prefix = token[:_KEY_PREFIX_LENGTH]
        candidates = ApiKey.query.filter_by(key_prefix=prefix).all()
        expected_hash = _hash_token(token)
        for candidate in candidates:
            if hmac.compare_digest(candidate.key_hash, expected_hash):
                if not candidate.is_usable():
                    raise InvalidApiKey()
                return candidate
        raise InvalidApiKey()

    @staticmethod
    @db_transaction
    def revoke_key(key_id: int, revoked_by_worker_id: int) -> None:
        key = db.session.get(ApiKey, key_id)
        if not key:
            raise ValueError(f"API-Key {key_id} nicht gefunden.")
        if key.revoked_at is not None:
            return  # idempotent
        key.revoked_at = get_utc_now()
        key.revoked_by_worker_id = revoked_by_worker_id
        key.is_active = False
        db.session.commit()
```

- [ ] **Step 4: Run, verify PASS**

Run: `cd ticketsystem && python -m pytest tests/test_api_key_service.py -v`
Expected: Alle 4 neuen Tests PASS.

- [ ] **Step 5: Commit**

```bash
git add ticketsystem/services/api_key_service.py ticketsystem/tests/test_api_key_service.py
git commit -m "feat: ApiKeyService.authenticate + revoke_key mit generischem 401"
```

### Task 2.5: Test — IP-Allowlist

- [ ] **Step 1: Tests ergänzen**

```python
def test_ip_check_empty_allowlist_allows_all(app, db_session, admin_worker, default_assignee):
    key, _ = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_worker.id,
    )
    # Keine Ranges vorhanden → alles OK
    ApiKeyService.check_ip(key, "203.0.113.1")
    ApiKeyService.check_ip(key, "198.51.100.99")
    ApiKeyService.check_ip(key, "::1")


def test_ip_check_with_allowlist_enforces(app, db_session, admin_worker, default_assignee):
    key, _ = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_worker.id,
    )
    ApiKeyService.add_ip_range(
        key.id, "203.0.113.0/24",
        note="test", created_by_worker_id=admin_worker.id,
    )
    ApiKeyService.check_ip(key, "203.0.113.5")      # okay
    with pytest.raises(IpNotAllowed):
        ApiKeyService.check_ip(key, "198.51.100.1")  # draußen


def test_ip_check_invalid_source_raises(app, db_session, admin_worker, default_assignee):
    key, _ = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_worker.id,
    )
    ApiKeyService.add_ip_range(
        key.id, "203.0.113.0/24",
        note="t", created_by_worker_id=admin_worker.id,
    )
    with pytest.raises(IpNotAllowed):
        ApiKeyService.check_ip(key, "not-an-ip")
```

- [ ] **Step 2: Run, verify FAIL (methods missing)**

- [ ] **Step 3: `check_ip` + `add_ip_range` implementieren**

```python
    @staticmethod
    def check_ip(key: ApiKey, source_ip: str) -> None:
        """Validate source_ip against key's allowlist. No-op if list empty."""
        if not key.ip_ranges:
            return
        try:
            ip = ipaddress.ip_address(source_ip)
        except (ValueError, TypeError):
            raise IpNotAllowed()
        for entry in key.ip_ranges:
            try:
                if ip in ipaddress.ip_network(entry.cidr, strict=False):
                    return
            except ValueError:
                continue  # skip malformed CIDR
        raise IpNotAllowed()

    @staticmethod
    @db_transaction
    def add_ip_range(
        key_id: int,
        cidr: str,
        note: Optional[str],
        created_by_worker_id: int,
    ) -> ApiKeyIpRange:
        # Validate CIDR syntax
        try:
            ipaddress.ip_network(cidr, strict=False)
        except ValueError as exc:
            raise ValueError(f"Ungültiger CIDR-Ausdruck: {cidr}") from exc
        entry = ApiKeyIpRange(
            api_key_id=key_id,
            cidr=cidr,
            note=note,
            created_by_worker_id=created_by_worker_id,
        )
        db.session.add(entry)
        db.session.commit()
        return entry

    @staticmethod
    @db_transaction
    def remove_ip_range(range_id: int) -> None:
        entry = db.session.get(ApiKeyIpRange, range_id)
        if entry:
            db.session.delete(entry)
            db.session.commit()
```

- [ ] **Step 4: Run, verify PASS, commit**

```bash
python -m pytest tests/test_api_key_service.py -v
git add ticketsystem/services/api_key_service.py ticketsystem/tests/test_api_key_service.py
git commit -m "feat: ApiKeyService.check_ip + IP-Range-Verwaltung mit CIDR-Validierung"
```

### Task 2.6: Test — Scope-Check + usage-Update

- [ ] **Step 1: Tests ergänzen**

```python
def test_has_scope(app, db_session, admin_worker, default_assignee):
    key, _ = ApiKeyService.create_key(
        name="K", scopes=["write:tickets", "read:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_worker.id,
    )
    assert key.has_scope("write:tickets")
    assert key.has_scope("read:tickets")
    assert not key.has_scope("admin:tickets")


def test_mark_used_updates_within_60s_throttled(app, db_session, admin_worker, default_assignee):
    key, _ = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_worker.id,
    )
    ApiKeyService.mark_used(key, "203.0.113.1")
    first = key.last_used_at
    ApiKeyService.mark_used(key, "203.0.113.2")  # innerhalb 60s
    # last_used_at sollte nicht aktualisiert worden sein
    assert key.last_used_at == first
    # last_used_ip KANN aktualisiert sein oder nicht — konservativ: auch throttled
    assert key.last_used_ip == "203.0.113.1"
```

- [ ] **Step 2: `mark_used` implementieren**

```python
    @staticmethod
    def mark_used(key: ApiKey, source_ip: str) -> None:
        """Update last_used_at/last_used_ip, throttled to once per 60s."""
        now = get_utc_now()
        if key.last_used_at is not None:
            if (now - key.last_used_at) < timedelta(seconds=60):
                return
        key.last_used_at = now
        key.last_used_ip = source_ip
        db.session.commit()
```

- [ ] **Step 3: Run, verify PASS, commit**

```bash
python -m pytest tests/test_api_key_service.py -v
git add -u
git commit -m "feat: ApiKeyService.mark_used mit 60s-Throttle"
```

### Task 2.7: Test + Impl — Audit-Log-Eintrag

- [ ] **Step 1: Test ergänzen**

```python
def test_log_audit_success(app, db_session, admin_worker, default_assignee):
    key, _ = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_worker.id,
    )
    ApiKeyService.log_audit(
        api_key=key, key_prefix=key.key_prefix,
        source_ip="203.0.113.1", method="POST", path="/api/v1/webhook/calls",
        status_code=201, latency_ms=42, outcome="success",
        external_ref="call_abc", assignment_method="default",
        request_id="abc-123",
    )
    from models import ApiAuditLog
    entry = ApiAuditLog.query.filter_by(request_id="abc-123").one()
    assert entry.outcome == "success"
    assert entry.api_key_id == key.id


def test_log_audit_failed_auth_without_key(app, db_session):
    ApiKeyService.log_audit(
        api_key=None, key_prefix=None,
        source_ip="45.131.112.9", method="POST", path="/api/v1/webhook/calls",
        status_code=401, latency_ms=2, outcome="auth_failed",
        request_id="xyz-789",
    )
    from models import ApiAuditLog
    entry = ApiAuditLog.query.filter_by(request_id="xyz-789").one()
    assert entry.api_key_id is None
    assert entry.outcome == "auth_failed"
```

- [ ] **Step 2: `log_audit` implementieren**

```python
    @staticmethod
    @db_transaction
    def log_audit(
        *,
        api_key: Optional[ApiKey],
        key_prefix: Optional[str],
        source_ip: str,
        method: str,
        path: str,
        status_code: int,
        latency_ms: int,
        outcome: str,
        request_id: str,
        external_ref: Optional[str] = None,
        assignment_method: Optional[str] = None,
        error_detail: Optional[str] = None,
    ) -> None:
        entry = ApiAuditLog(
            api_key_id=api_key.id if api_key else None,
            key_prefix=key_prefix,
            source_ip=source_ip[:45],
            method=method,
            path=path[:255],
            status_code=status_code,
            latency_ms=latency_ms,
            outcome=outcome,
            external_ref=external_ref,
            assignment_method=assignment_method,
            request_id=request_id,
            error_detail=(error_detail or None),
        )
        db.session.add(entry)
        db.session.commit()
```

- [ ] **Step 3: Run + Commit**

```bash
python -m pytest tests/test_api_key_service.py -v
git add -u
git commit -m "feat: ApiKeyService.log_audit für strukturiertes Audit-Log"
```

### Task 2.8: Timing-Attack-Resistenz-Smoke-Test

- [ ] **Step 1: Test ergänzen**

```python
def test_authenticate_timing_similar_for_wrong_prefix_and_wrong_hash(
    app, db_session, admin_worker, default_assignee,
):
    """Timing stability — crude but catches blatant non-constant compares."""
    import time, statistics
    key, plaintext = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=default_assignee.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_worker.id,
    )
    wrong_prefix = "tsk_" + "z" * 48
    wrong_hash_same_prefix = key.key_prefix + "a" * (52 - len(key.key_prefix))

    def measure(token, n=50):
        times = []
        for _ in range(n):
            t0 = time.perf_counter()
            try:
                ApiKeyService.authenticate(token)
            except InvalidApiKey:
                pass
            times.append(time.perf_counter() - t0)
        return statistics.median(times)

    t1 = measure(wrong_prefix)
    t2 = measure(wrong_hash_same_prefix)
    ratio = max(t1, t2) / min(t1, t2)
    # Nicht mehr als Faktor 5 Unterschied — sehr lax, aber fängt O(n)-Compare
    assert ratio < 5.0, f"Timing ratio {ratio:.2f} verdächtig"
```

- [ ] **Step 2: Run + Commit**

```bash
python -m pytest tests/test_api_key_service.py::test_authenticate_timing_similar_for_wrong_prefix_and_wrong_hash -v
git add -u
git commit -m "test: Timing-Attack-Resistenz-Smoke-Test für authenticate"
```

---

## Phase 3 — api_bp Blueprint + Decorators

### Task 3.1: Blueprint-Gerüst + Registration

**Files:**
- Create: `ticketsystem/routes/api/__init__.py`
- Modify: `ticketsystem/app.py`

- [ ] **Step 1: Blueprint-Datei schreiben**

```python
"""Public REST API Blueprint.

Strictly isolated from main_bp:
- No session cookies (cleared in before_request)
- JSON-only error responses
- Own decorator chain (@api_key_required, not @worker_required)
"""

from __future__ import annotations

import uuid

from flask import Blueprint, Flask, g, request, session

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")


@api_bp.before_request
def _isolate_session():
    """Clear any session state — API is stateless."""
    session.clear()
    g.pop("current_worker", None)
    g.api_request_id = str(uuid.uuid4())
    g.api_request_start = None  # set by auth decorator for latency


def register_api(app: Flask) -> None:
    """Register the api_bp on *app* with all sub-modules loaded."""
    from .health_routes import register_routes as register_health
    from .webhook_routes import register_routes as register_webhook
    # Phase b/c: from .ticket_routes import register_routes as register_tickets
    from ._errors import register_error_handlers

    register_health(api_bp)
    register_webhook(api_bp)
    register_error_handlers(api_bp)

    app.register_blueprint(api_bp)
```

- [ ] **Step 2: `ticketsystem/app.py` anpassen**

In `app.py` nach der Registrierung von `main_bp`:

```python
# Public REST API (isolated blueprint)
from routes.api import register_api
register_api(app)
```

Zusätzlich:

```python
app.config["MAX_CONTENT_LENGTH"] = 128 * 1024  # 128 KB global; API Route braucht es zwingend
```

- [ ] **Step 3: Placeholder-Module für Sub-Routen erzeugen**

Minimale Platzhalter, damit der Import nicht scheitert:

`ticketsystem/routes/api/health_routes.py`:
```python
from flask import Blueprint, jsonify


def register_routes(bp: Blueprint) -> None:
    @bp.route("/health", methods=["GET"])
    def _health():
        return jsonify({"status": "ok"}), 200
```

`ticketsystem/routes/api/webhook_routes.py`:
```python
from flask import Blueprint


def register_routes(bp: Blueprint) -> None:
    pass  # wird in Phase 4 befüllt
```

`ticketsystem/routes/api/_errors.py`:
```python
from flask import Blueprint


def register_error_handlers(bp: Blueprint) -> None:
    pass  # wird in Task 3.3 befüllt
```

- [ ] **Step 4: Import-Check**

Run: `cd ticketsystem && python -c "from app import app; print([str(r) for r in app.url_map.iter_rules() if '/api/v1' in str(r)])"`
Expected: Liste enthält `/api/v1/health`.

- [ ] **Step 5: Commit**

```bash
git add ticketsystem/routes/api/ ticketsystem/app.py
git commit -m "feat: api_bp Blueprint-Gerüst mit Session-Isolation"
```

### Task 3.2: Decorator — @api_key_required

**Files:**
- Create: `ticketsystem/routes/api/_decorators.py`
- Create: `ticketsystem/tests/test_api_auth.py`

- [ ] **Step 1: Tests schreiben**

```python
"""Tests for API authentication decorators."""

from flask import Blueprint, jsonify

from models import Worker
from services.api_key_service import ApiKeyService


def _make_test_route(app):
    """Register a throwaway route protected by @api_key_required."""
    from routes.api._decorators import api_key_required
    from flask import g

    test_bp = Blueprint("test_api_auth", __name__, url_prefix="/test_api_v1")

    @test_bp.route("/protected", methods=["GET"])
    @api_key_required
    def _protected():
        return jsonify({"key_id": g.api_key.id}), 200

    app.register_blueprint(test_bp)


def test_missing_header_returns_401(app, client, db_session):
    _make_test_route(app)
    r = client.get("/test_api_v1/protected")
    assert r.status_code == 401
    assert r.get_json() == {"error": "unauthorized"}


def test_wrong_bearer_returns_401(app, client, db_session):
    _make_test_route(app)
    r = client.get(
        "/test_api_v1/protected",
        headers={"Authorization": "Bearer tsk_" + "x" * 48},
    )
    assert r.status_code == 401
    assert r.get_json() == {"error": "unauthorized"}


def test_wrong_scheme_returns_401(app, client, db_session, admin_fixture, worker_fixture):
    _make_test_route(app)
    key, plaintext = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=worker_fixture.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_fixture.id,
    )
    r = client.get(
        "/test_api_v1/protected",
        headers={"Authorization": f"Basic {plaintext}"},
    )
    assert r.status_code == 401


def test_valid_token_returns_200(app, client, db_session, admin_fixture, worker_fixture):
    _make_test_route(app)
    key, plaintext = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=worker_fixture.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_fixture.id,
    )
    r = client.get(
        "/test_api_v1/protected",
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert r.status_code == 200
    assert r.get_json()["key_id"] == key.id
```

Die `admin_fixture` / `worker_fixture` / `client` fixtures zur `conftest.py` hinzufügen bzw. die bestehenden Fixtures wiederverwenden. Namens-Konventionen prüfen.

- [ ] **Step 2: Run, verify FAIL**

Expected: `ImportError` oder `AttributeError`.

- [ ] **Step 3: Decorator implementieren**

`ticketsystem/routes/api/_decorators.py`:

```python
"""Decorators for the public REST API."""

from __future__ import annotations

import functools
import time
from typing import Callable, Iterable

from flask import current_app, g, jsonify, request

from exceptions import InvalidApiKey, IpNotAllowed, ScopeDenied
from services.api_key_service import ApiKeyService


_CF_IP_HEADER = "CF-Connecting-IP"
_REAL_IP_HEADER = "X-Real-IP"


def _client_ip() -> str:
    """Extract source IP, prefer Cloudflare header over X-Real-IP over remote_addr."""
    return (
        request.headers.get(_CF_IP_HEADER)
        or request.headers.get(_REAL_IP_HEADER)
        or request.remote_addr
        or ""
    )


def _extract_bearer_token() -> str | None:
    auth = request.headers.get("Authorization", "")
    if not auth:
        return None
    parts = auth.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def api_key_required(view: Callable) -> Callable:
    """Authenticate via Authorization: Bearer <token>.

    On success: g.api_key is set. On failure: 401/403 with generic body,
    outcome logged to api_audit_log (via @api_audit_log later; here we
    set g.api_outcome for deferred logging).
    """
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        g.api_request_start = time.perf_counter()
        g.api_outcome = "success"  # overwritten on failure

        token = _extract_bearer_token()
        try:
            key = ApiKeyService.authenticate(token)
        except InvalidApiKey:
            g.api_outcome = "auth_failed"
            g.api_key = None
            g.api_key_prefix = token[:12] if token else None
            return jsonify({"error": "unauthorized"}), 401

        try:
            ApiKeyService.check_ip(key, _client_ip())
        except IpNotAllowed:
            g.api_outcome = "ip_blocked"
            g.api_key = key
            g.api_key_prefix = key.key_prefix
            return jsonify({"error": "forbidden"}), 403

        g.api_key = key
        g.api_key_prefix = key.key_prefix
        ApiKeyService.mark_used(key, _client_ip())
        return view(*args, **kwargs)

    return wrapper
```

- [ ] **Step 4: Run + Commit**

```bash
python -m pytest tests/test_api_auth.py -v
git add ticketsystem/routes/api/_decorators.py ticketsystem/tests/test_api_auth.py
git commit -m "feat: @api_key_required mit generischem 401 + CF-Connecting-IP"
```

### Task 3.3: Decorator — @require_scope + JSON Error Handler

- [ ] **Step 1: Test ergänzen (in test_api_auth.py)**

```python
def test_scope_denied_returns_403(app, client, db_session, admin_fixture, worker_fixture):
    from routes.api._decorators import api_key_required, require_scope
    from flask import Blueprint, g, jsonify

    bp = Blueprint("test_scope", __name__, url_prefix="/test_scope_v1")

    @bp.route("/admin_only", methods=["GET"])
    @api_key_required
    @require_scope("admin:tickets")
    def _only():
        return jsonify({"ok": True}), 200

    app.register_blueprint(bp)
    _, plaintext = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],  # fehlt admin:tickets
        default_assignee_id=worker_fixture.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_fixture.id,
    )
    r = client.get(
        "/test_scope_v1/admin_only",
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert r.status_code == 403
    assert r.get_json() == {"error": "forbidden"}
```

- [ ] **Step 2: `require_scope` implementieren (in _decorators.py)**

```python
def require_scope(scope: str) -> Callable:
    def decorator(view: Callable) -> Callable:
        @functools.wraps(view)
        def wrapper(*args, **kwargs):
            key = getattr(g, "api_key", None)
            if key is None or not key.has_scope(scope):
                g.api_outcome = "scope_denied"
                return jsonify({"error": "forbidden"}), 403
            return view(*args, **kwargs)
        return wrapper
    return decorator
```

- [ ] **Step 3: JSON Error Handler registrieren**

In `ticketsystem/routes/api/_errors.py`:

```python
"""JSON-only error handlers for the public API blueprint."""

from __future__ import annotations

import uuid

from flask import Blueprint, current_app, g, jsonify
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException

from exceptions import DomainError


def register_error_handlers(bp: Blueprint) -> None:

    @bp.errorhandler(DomainError)
    def _handle_domain(exc):
        g.api_outcome = "validation_failed"
        return jsonify({"error": "validation_failed", "detail": str(exc)}), exc.status_code

    @bp.errorhandler(ValueError)
    def _handle_value(exc):
        g.api_outcome = "validation_failed"
        return jsonify({"error": "validation_failed", "detail": str(exc)}), 400

    @bp.errorhandler(SQLAlchemyError)
    def _handle_sql(exc):
        g.api_outcome = "server_error"
        current_app.logger.exception("API SQL error")
        return jsonify({
            "error": "internal_error",
            "request_id": getattr(g, "api_request_id", "unknown"),
        }), 500

    @bp.errorhandler(413)
    def _handle_413(exc):
        g.api_outcome = "payload_too_large"
        return jsonify({"error": "payload_too_large"}), 413

    @bp.errorhandler(415)
    def _handle_415(exc):
        g.api_outcome = "unsupported_media_type"
        return jsonify({"error": "unsupported_media_type"}), 415

    @bp.errorhandler(HTTPException)
    def _handle_http(exc):
        g.api_outcome = "server_error"
        return jsonify({
            "error": "internal_error",
            "request_id": getattr(g, "api_request_id", "unknown"),
        }), exc.code or 500
```

- [ ] **Step 4: Run + Commit**

```bash
python -m pytest tests/test_api_auth.py -v
git add -u
git commit -m "feat: @require_scope + JSON-Error-Handler für api_bp"
```

### Task 3.4: Decorator — @api_rate_limit (pro Key dynamisch)

- [ ] **Step 1: Test ergänzen**

```python
def test_rate_limit_per_key(app, client, db_session, admin_fixture, worker_fixture):
    from routes.api._decorators import api_key_required, api_rate_limit
    from flask import Blueprint, jsonify

    bp = Blueprint("test_rl", __name__, url_prefix="/test_rl_v1")

    @bp.route("/rl", methods=["GET"])
    @api_key_required
    @api_rate_limit
    def _rl():
        return jsonify({"ok": True}), 200

    app.register_blueprint(bp)
    _, plaintext = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=worker_fixture.id,
        rate_limit_per_minute=3,  # niedrig für Test
        created_by_worker_id=admin_fixture.id,
    )
    hdr = {"Authorization": f"Bearer {plaintext}"}
    assert client.get("/test_rl_v1/rl", headers=hdr).status_code == 200
    assert client.get("/test_rl_v1/rl", headers=hdr).status_code == 200
    assert client.get("/test_rl_v1/rl", headers=hdr).status_code == 200
    r = client.get("/test_rl_v1/rl", headers=hdr)
    assert r.status_code == 429
    body = r.get_json()
    assert body["error"] == "rate_limited"
```

- [ ] **Step 2: `api_rate_limit` implementieren (In-Memory, pro Key)**

Erweitere `_decorators.py`:

```python
from collections import defaultdict, deque
from threading import Lock

_rate_windows: dict[int, deque] = defaultdict(deque)
_rate_lock = Lock()


def api_rate_limit(view: Callable) -> Callable:
    """Token-bucket-ähnliches Sliding-Window pro api_key.id.

    Limit wird dynamisch aus g.api_key.rate_limit_per_minute gelesen.
    In-Memory; nur für Single-Worker-Deployment geeignet.
    """
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        key = g.api_key
        limit = key.rate_limit_per_minute
        now = time.time()
        window_start = now - 60.0

        with _rate_lock:
            q = _rate_windows[key.id]
            # Fenster bereinigen
            while q and q[0] < window_start:
                q.popleft()
            if len(q) >= limit:
                g.api_outcome = "rate_limited"
                retry_after = int(60 - (now - q[0])) + 1
                return jsonify({
                    "error": "rate_limited",
                    "retry_after": retry_after,
                }), 429
            q.append(now)

        return view(*args, **kwargs)

    return wrapper
```

- [ ] **Step 3: Run + Commit**

```bash
python -m pytest tests/test_api_auth.py::test_rate_limit_per_key -v
git add -u
git commit -m "feat: @api_rate_limit mit dynamischem Pro-Key-Limit (In-Memory)"
```

### Task 3.5: Deferred Audit-Logging via after_request

- [ ] **Step 1: `api_bp.after_request` ergänzen (in routes/api/__init__.py)**

```python
import time

from services.api_key_service import ApiKeyService


@api_bp.after_request
def _write_audit_log(response):
    """Write audit log entry for every API request (except /health)."""
    if request.path.endswith("/health"):
        return response
    start = getattr(g, "api_request_start", None)
    latency_ms = int((time.perf_counter() - start) * 1000) if start else 0
    try:
        ApiKeyService.log_audit(
            api_key=getattr(g, "api_key", None),
            key_prefix=getattr(g, "api_key_prefix", None),
            source_ip=(
                request.headers.get("CF-Connecting-IP")
                or request.headers.get("X-Real-IP")
                or request.remote_addr
                or ""
            ),
            method=request.method,
            path=request.path,
            status_code=response.status_code,
            latency_ms=latency_ms,
            outcome=getattr(g, "api_outcome", "success"),
            request_id=getattr(g, "api_request_id", "unknown"),
            external_ref=getattr(g, "api_external_ref", None),
            assignment_method=getattr(g, "api_assignment_method", None),
            error_detail=getattr(g, "api_error_detail", None),
        )
    except Exception:
        current_app.logger.exception("Audit log write failed")
    return response
```

**Wichtig:** Import von `request` und `current_app` in derselben Datei sicherstellen.

- [ ] **Step 2: Test — jeder Request erzeugt Audit-Eintrag**

```python
def test_audit_log_written_on_auth_failure(app, client, db_session):
    from models import ApiAuditLog
    count_before = ApiAuditLog.query.count()
    client.post("/api/v1/webhook/calls", json={"webhook_id": "x", "data": {}})  # no auth
    assert ApiAuditLog.query.count() == count_before + 1
    last = ApiAuditLog.query.order_by(ApiAuditLog.id.desc()).first()
    assert last.outcome == "auth_failed"
    assert last.status_code == 401
```

- [ ] **Step 3: Run + Commit**

```bash
python -m pytest tests/test_api_auth.py -v
git add -u
git commit -m "feat: after_request schreibt Audit-Log für jeden API-Request"
```

---

## Phase 4 — Webhook-Endpoint

### Task 4.1: pydantic hinzufügen

**Files:**
- Modify: `ticketsystem/requirements.txt`
- Modify: `ticketsystem/Dockerfile` (nur falls explizit gefragt — pydantic ist in requirements.txt)

- [ ] **Step 1:**

```
# In requirements.txt ergänzen:
pydantic>=2.0,<3.0
```

- [ ] **Step 2:** `pip install -r requirements.txt` lokal, Import-Check.

Run: `cd ticketsystem && python -c "import pydantic; print(pydantic.VERSION)"`
Expected: 2.x

- [ ] **Step 3: Commit**

```bash
git add ticketsystem/requirements.txt
git commit -m "feat: pydantic v2 als Dependency für API-Payload-Validation"
```

### Task 4.2: Pydantic-Schemas

**Files:**
- Create: `ticketsystem/routes/api/_schemas.py`

- [ ] **Step 1: Schema-Datei schreiben**

```python
"""Pydantic schemas for API payloads."""

from __future__ import annotations

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class HalloPetraMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["assistant", "user"]
    content: str = Field(max_length=10_000)


class HalloPetraContactData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: Optional[str] = None
    name: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=32)
    email: Optional[str] = Field(default=None, max_length=255)
    address: Optional[str] = Field(default=None, max_length=500)


class HalloPetraCallData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=64)
    duration: int = Field(ge=0, le=86400)
    phone: Optional[str] = Field(default=None, max_length=32)
    topic: Optional[str] = Field(default=None, max_length=255)
    summary: Optional[str] = Field(default=None, max_length=5_000)
    messages: List[HalloPetraMessage] = Field(default_factory=list, max_length=500)
    collected_data: dict[str, Any] = Field(default_factory=dict)
    contact_data: Optional[HalloPetraContactData] = None
    main_task_id: Optional[str] = None
    email_send_to: Optional[str] = Field(default=None, max_length=255)
    forwarded_to: Optional[str] = None
    previous_webhook_calls: List[Any] = Field(default_factory=list)


class HalloPetraWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    webhook_id: str = Field(min_length=1, max_length=128)
    data: HalloPetraCallData
```

- [ ] **Step 2: Commit**

```bash
git add ticketsystem/routes/api/_schemas.py
git commit -m "feat: Pydantic-Schemas für HalloPetra-Webhook-Payload"
```

### Task 4.3: Test — ApiTicketFactory (Payload → Ticket-Mapping)

**Files:**
- Create: `ticketsystem/tests/test_api_ticket_factory.py`

- [ ] **Step 1: Test schreiben**

```python
"""Tests for services/api_ticket_factory.py."""

import pytest

from models import Ticket, ApiKey, Worker
from services.api_key_service import ApiKeyService
from services.api_ticket_factory import ApiTicketFactory
from routes.api._schemas import HalloPetraWebhookPayload


@pytest.fixture
def petra_key(app, db_session, admin_fixture, worker_fixture):
    key, _ = ApiKeyService.create_key(
        name="HP", scopes=["write:tickets"],
        default_assignee_id=worker_fixture.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_fixture.id,
    )
    return key


def _sample_payload(call_id: str = "call_abc123") -> dict:
    return {
        "webhook_id": "wh_xyz",
        "data": {
            "id": call_id,
            "duration": 125,
            "phone": "+491234567890",
            "topic": "Heizungswartung anfragen",
            "summary": "Kunde möchte einen Termin.",
            "messages": [
                {"role": "assistant", "content": "Guten Tag"},
                {"role": "user", "content": "Ich möchte..."},
            ],
            "collected_data": {"wunschtermin": "Dienstag"},
            "contact_data": {
                "id": "c_xyz", "name": "Max Mustermann",
                "phone": "+491234567890", "email": "max@mustermann.de",
                "address": "Musterstraße 1",
            },
            "email_send_to": "info@beispiel.de",
            "forwarded_to": "+4930987654",
            "previous_webhook_calls": [],
        },
    }


def test_create_ticket_sets_basics(app, db_session, petra_key):
    payload = HalloPetraWebhookPayload(**_sample_payload())
    ticket, method = ApiTicketFactory.create_from_payload(petra_key, payload)
    assert ticket.external_call_id == "call_abc123"
    assert "Heizungswartung" in ticket.title
    assert ticket.contact.name == "Max Mustermann"
    assert ticket.contact.phone == "+491234567890"
    assert ticket.contact.email == "max@mustermann.de"
    assert ticket.contact.channel == "Telefon (KI-Agent)"
    assert "Dienstag" in ticket.description or "Kunde möchte" in ticket.description


def test_create_ticket_stores_transcripts(app, db_session, petra_key):
    payload = HalloPetraWebhookPayload(**_sample_payload())
    ticket, _ = ApiTicketFactory.create_from_payload(petra_key, payload)
    assert len(ticket.transcripts) == 2
    assert ticket.transcripts[0].role == "assistant"
    assert ticket.transcripts[0].position == 0
    assert ticket.transcripts[1].role == "user"
    assert ticket.transcripts[1].position == 1


def test_create_ticket_metadata_contains_address(app, db_session, petra_key):
    payload = HalloPetraWebhookPayload(**_sample_payload())
    ticket, _ = ApiTicketFactory.create_from_payload(petra_key, payload)
    meta = ticket.get_external_metadata()
    assert meta["contact_data"]["address"] == "Musterstraße 1"
    assert meta["duration"] == 125
    assert "forwarded_to" in meta


def test_assignment_email_match(app, db_session, admin_fixture):
    matched = Worker(name="InfoUser", is_active=True, role="WORKER",
                     email="info@beispiel.de")
    matched.set_pin("9173")
    db_session.add(matched)
    db_session.commit()
    key, _ = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=matched.id,  # auch default, aber Match soll greifen
        rate_limit_per_minute=60, created_by_worker_id=admin_fixture.id,
    )
    payload = HalloPetraWebhookPayload(**_sample_payload())
    ticket, method = ApiTicketFactory.create_from_payload(key, payload)
    assert ticket.assignee_id == matched.id
    assert method == "email_match"


def test_assignment_fallback_to_default(app, db_session, petra_key, worker_fixture):
    payload_dict = _sample_payload()
    payload_dict["data"]["email_send_to"] = "unbekannt@nirgendwo.xx"
    payload = HalloPetraWebhookPayload(**payload_dict)
    ticket, method = ApiTicketFactory.create_from_payload(petra_key, payload)
    assert ticket.assignee_id == worker_fixture.id
    assert method == "default"


def test_assignment_inactive_worker_fallback(app, db_session, admin_fixture, worker_fixture):
    inactive = Worker(name="Inactive", is_active=False, role="WORKER",
                      email="info@beispiel.de")
    inactive.set_pin("6482")
    db_session.add(inactive)
    db_session.commit()
    key, _ = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=worker_fixture.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_fixture.id,
    )
    payload = HalloPetraWebhookPayload(**_sample_payload())
    ticket, method = ApiTicketFactory.create_from_payload(key, payload)
    assert ticket.assignee_id == worker_fixture.id
    assert method == "inactive_worker_fallback"


def test_confidential_flag_applied(app, db_session, petra_key):
    payload = HalloPetraWebhookPayload(**_sample_payload())
    ticket, _ = ApiTicketFactory.create_from_payload(petra_key, payload)
    assert ticket.is_confidential is True  # Feld-Name dem Bestand anpassen
```

- [ ] **Step 2: Run, verify FAIL**

Expected: ImportError for `ApiTicketFactory`.

### Task 4.4: ApiTicketFactory implementieren

**Files:**
- Create: `ticketsystem/services/api_ticket_factory.py`

- [ ] **Step 1: Service schreiben**

```python
"""Create Ticket objects from validated HalloPetra payloads.

Kept separate from TicketCoreService because the mapping logic is
vendor-specific; TicketCoreService stays clean of API concerns.
"""

from __future__ import annotations

from typing import Tuple

from sqlalchemy import func

from extensions import db
from models import ApiKey, Ticket, TicketContact, TicketTranscript, Worker
from routes.api._schemas import HalloPetraWebhookPayload
from services._helpers import db_transaction
from utils import get_utc_now


_CONTACT_CHANNEL = "Telefon (KI-Agent)"


class ApiTicketFactory:
    """Factory for API-created tickets. Static methods only."""

    @staticmethod
    @db_transaction
    def create_from_payload(
        api_key: ApiKey,
        payload: HalloPetraWebhookPayload,
    ) -> Tuple[Ticket, str]:
        """Create a new ticket from the payload. Returns (ticket, assignment_method).

        Assumes caller has verified idempotency (no existing ticket with same
        external_call_id). Commits within db_transaction.
        """
        data = payload.data
        ticket = Ticket(
            title=_derive_title(data),
            description=_derive_description(data),
            external_call_id=data.id,
            is_confidential=api_key.create_confidential_tickets,
            created_at=get_utc_now(),
        )

        # Contact (via ensure_contact, respecting CLAUDE.md rule #3)
        contact = ticket.ensure_contact()
        contact.name = _pick_name(data)
        contact.phone = _pick_phone(data)
        contact.email = _pick_email(data)
        contact.channel = _CONTACT_CHANNEL

        # Assignment
        assignee_id, method = _resolve_assignee(api_key, data.email_send_to)
        ticket.assignee_id = assignee_id

        # External metadata (everything not mapped to dedicated fields)
        ticket.set_external_metadata({
            "duration": data.duration,
            "main_task_id": data.main_task_id,
            "collected_data": data.collected_data,
            "contact_data": (data.contact_data.model_dump() if data.contact_data else None),
            "forwarded_to": data.forwarded_to,
            "previous_webhook_calls": data.previous_webhook_calls,
            "webhook_id": payload.webhook_id,
        })

        db.session.add(ticket)
        db.session.flush()  # ticket.id available

        # Transcripts
        for idx, msg in enumerate(data.messages):
            entry = TicketTranscript(
                ticket_id=ticket.id,
                position=idx,
                role=msg.role,
                content=msg.content,
            )
            db.session.add(entry)

        db.session.commit()
        return ticket, method


def _derive_title(data) -> str:
    if data.topic:
        return data.topic[:255]
    if data.summary:
        return data.summary[:80]
    return f"Anruf {data.id}"


def _derive_description(data) -> str:
    parts = []
    if data.summary:
        parts.append(data.summary)
    if data.forwarded_to:
        parts.append(f"\nWeitergeleitet an: {data.forwarded_to}")
    return "\n".join(parts)


def _pick_name(data):
    if data.contact_data and data.contact_data.name:
        return data.contact_data.name
    return data.collected_data.get("contact_name")


def _pick_phone(data):
    if data.contact_data and data.contact_data.phone:
        return data.contact_data.phone
    return data.collected_data.get("contact_phone") or data.phone


def _pick_email(data):
    if data.contact_data and data.contact_data.email:
        return data.contact_data.email
    return data.collected_data.get("contact_email")


def _resolve_assignee(api_key: ApiKey, email_send_to: str | None) -> Tuple[int, str]:
    """Return (assignee_id, assignment_method)."""
    default_id = api_key.default_assignee_worker_id
    if not email_send_to:
        return default_id, "default"

    email_lower = email_send_to.strip().lower()
    matches = Worker.query.filter(
        func.lower(Worker.email) == email_lower
    ).all()

    if not matches:
        return default_id, "default"
    if len(matches) > 1:
        return default_id, "ambiguous_fallback"

    w = matches[0]
    if not w.is_active:
        return default_id, "inactive_worker_fallback"
    return w.id, "email_match"
```

- [ ] **Step 2: Run + Commit**

```bash
python -m pytest tests/test_api_ticket_factory.py -v
git add ticketsystem/services/api_ticket_factory.py ticketsystem/tests/test_api_ticket_factory.py
git commit -m "feat: ApiTicketFactory für Payload-zu-Ticket-Mapping"
```

### Task 4.5: Test — Webhook-Endpoint End-to-End

**Files:**
- Create: `ticketsystem/tests/test_api_webhook.py`

- [ ] **Step 1: Test schreiben**

```python
"""End-to-end tests for /api/v1/webhook/calls."""

import json
import pytest

from models import ApiAuditLog, Ticket
from services.api_key_service import ApiKeyService


def _payload(call_id="call_001"):
    return {
        "webhook_id": "wh_xxx",
        "data": {
            "id": call_id,
            "duration": 42,
            "topic": "Test-Anruf",
            "summary": "Summary",
            "messages": [{"role": "user", "content": "Hi"}],
            "contact_data": {
                "name": "Test Kunde",
                "email": "test@kunde.de",
                "phone": "+490000",
            },
            "email_send_to": "info@beispiel.de",
        },
    }


@pytest.fixture
def petra_token(app, db_session, admin_fixture, worker_fixture):
    _, plaintext = ApiKeyService.create_key(
        name="HP", scopes=["write:tickets"],
        default_assignee_id=worker_fixture.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_fixture.id,
    )
    return plaintext


def test_webhook_creates_ticket_201(client, db_session, petra_token):
    r = client.post(
        "/api/v1/webhook/calls",
        json=_payload(),
        headers={"Authorization": f"Bearer {petra_token}"},
    )
    assert r.status_code == 201
    body = r.get_json()
    assert body["status"] == "created"
    assert "ticket_id" in body
    t = db_session.get(Ticket, body["ticket_id"])
    assert t.external_call_id == "call_001"


def test_webhook_idempotent_returns_200(client, db_session, petra_token):
    r1 = client.post(
        "/api/v1/webhook/calls",
        json=_payload("call_002"),
        headers={"Authorization": f"Bearer {petra_token}"},
    )
    assert r1.status_code == 201
    first_id = r1.get_json()["ticket_id"]

    r2 = client.post(
        "/api/v1/webhook/calls",
        json=_payload("call_002"),
        headers={"Authorization": f"Bearer {petra_token}"},
    )
    assert r2.status_code == 200
    assert r2.get_json()["status"] == "duplicate"
    assert r2.get_json()["ticket_id"] == first_id

    assert Ticket.query.filter_by(external_call_id="call_002").count() == 1


def test_webhook_malformed_json_returns_400(client, petra_token):
    r = client.post(
        "/api/v1/webhook/calls",
        data="not-json",
        content_type="application/json",
        headers={"Authorization": f"Bearer {petra_token}"},
    )
    assert r.status_code == 400


def test_webhook_wrong_content_type_returns_415(client, petra_token):
    r = client.post(
        "/api/v1/webhook/calls",
        data=json.dumps(_payload()),
        content_type="text/plain",
        headers={"Authorization": f"Bearer {petra_token}"},
    )
    assert r.status_code == 415


def test_webhook_too_large_returns_413(client, petra_token):
    big = _payload("call_big")
    big["data"]["summary"] = "x" * 200_000
    r = client.post(
        "/api/v1/webhook/calls",
        json=big,
        headers={"Authorization": f"Bearer {petra_token}"},
    )
    assert r.status_code == 413


def test_webhook_missing_scope_returns_403(client, db_session, admin_fixture, worker_fixture):
    _, plaintext = ApiKeyService.create_key(
        name="K", scopes=["read:tickets"],  # fehlendes write:tickets
        default_assignee_id=worker_fixture.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_fixture.id,
    )
    r = client.post(
        "/api/v1/webhook/calls",
        json=_payload(),
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert r.status_code == 403


def test_webhook_expected_webhook_id_mismatch_rejects(
    client, db_session, admin_fixture, worker_fixture,
):
    _, plaintext = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=worker_fixture.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_fixture.id,
        expected_webhook_id="wh_expected",
    )
    r = client.post(
        "/api/v1/webhook/calls",
        json=_payload(),  # webhook_id="wh_xxx"
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert r.status_code == 400
    assert r.get_json()["error"] == "validation_failed"


def test_audit_log_external_ref_set(client, db_session, petra_token):
    client.post(
        "/api/v1/webhook/calls",
        json=_payload("call_audit"),
        headers={"Authorization": f"Bearer {petra_token}"},
    )
    entry = ApiAuditLog.query.order_by(ApiAuditLog.id.desc()).first()
    assert entry.external_ref == "call_audit"
    assert entry.outcome == "success"
    assert entry.assignment_method == "default"
```

- [ ] **Step 2: Run, verify FAIL (Endpunkt existiert noch nicht)**

### Task 4.6: Webhook-Endpoint implementieren

**Files:**
- Modify: `ticketsystem/routes/api/webhook_routes.py`

- [ ] **Step 1: Endpoint-Code schreiben**

```python
"""Public webhook endpoint for HalloPetra call events."""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request
from pydantic import ValidationError

from exceptions import DomainError
from extensions import db
from models import Ticket
from routes.api._decorators import api_key_required, api_rate_limit, require_scope
from routes.api._schemas import HalloPetraWebhookPayload
from services.api_ticket_factory import ApiTicketFactory


def register_routes(bp: Blueprint) -> None:

    @bp.route("/webhook/calls", methods=["POST"])
    @api_key_required
    @require_scope("write:tickets")
    @api_rate_limit
    def _webhook_calls():
        if not request.is_json:
            g.api_outcome = "unsupported_media_type"
            return jsonify({"error": "unsupported_media_type"}), 415

        try:
            raw = request.get_json(force=False, silent=False)
        except Exception:
            g.api_outcome = "validation_failed"
            return jsonify({"error": "validation_failed", "detail": "invalid JSON"}), 400

        try:
            payload = HalloPetraWebhookPayload(**raw)
        except (ValidationError, TypeError) as exc:
            g.api_outcome = "validation_failed"
            return jsonify({
                "error": "validation_failed",
                "detail": str(exc)[:500],
            }), 400

        # Optional webhook_id check
        if g.api_key.expected_webhook_id:
            if payload.webhook_id != g.api_key.expected_webhook_id:
                g.api_outcome = "validation_failed"
                return jsonify({
                    "error": "validation_failed",
                    "detail": "webhook_id mismatch",
                }), 400

        # Idempotency: explicit lookup first
        existing = Ticket.query.filter_by(external_call_id=payload.data.id).first()
        if existing is not None:
            g.api_outcome = "idempotent_replay"
            g.api_external_ref = payload.data.id
            return jsonify({
                "ticket_id": existing.id,
                "status": "duplicate",
            }), 200

        # Create
        ticket, method = ApiTicketFactory.create_from_payload(g.api_key, payload)
        g.api_external_ref = payload.data.id
        g.api_assignment_method = method

        return jsonify({
            "ticket_id": ticket.id,
            "status": "created",
        }), 201
```

- [ ] **Step 2: Run + Commit**

```bash
python -m pytest tests/test_api_webhook.py -v
git add ticketsystem/routes/api/webhook_routes.py ticketsystem/tests/test_api_webhook.py
git commit -m "feat: POST /api/v1/webhook/calls mit Idempotenz und Schema-Validation"
```

### Task 4.7: Test — Idempotenz bei parallelen Requests

**Files:**
- Create: `ticketsystem/tests/test_api_idempotency.py`

- [ ] **Step 1: Test schreiben**

```python
"""Idempotency tests including race-condition simulation."""

import threading

import pytest

from models import Ticket
from services.api_key_service import ApiKeyService


@pytest.fixture
def petra_token(app, db_session, admin_fixture, worker_fixture):
    _, plaintext = ApiKeyService.create_key(
        name="HP", scopes=["write:tickets"],
        default_assignee_id=worker_fixture.id,
        rate_limit_per_minute=1000, created_by_worker_id=admin_fixture.id,
    )
    return plaintext


def test_parallel_duplicate_creates_one_ticket(app, client, db_session, petra_token):
    """Two simultaneous requests with same external_call_id.

    Unique-constraint catches the race; second gets 200 (duplicate) or 409.
    """
    payload = {
        "webhook_id": "w", "data": {"id": "race_001", "duration": 1,
                                    "topic": "t", "summary": "s",
                                    "messages": []},
    }
    headers = {"Authorization": f"Bearer {petra_token}"}
    results = []

    def fire():
        with app.test_client() as c:
            r = c.post("/api/v1/webhook/calls", json=payload, headers=headers)
            results.append(r.status_code)

    t1 = threading.Thread(target=fire)
    t2 = threading.Thread(target=fire)
    t1.start(); t2.start()
    t1.join(); t2.join()

    # Genau ein Ticket darf existieren
    assert Ticket.query.filter_by(external_call_id="race_001").count() == 1
    # Beide Requests haben OK-Status (201 oder 200)
    assert all(s in (200, 201) for s in results)
```

- [ ] **Step 2: Falls Test fehlschlägt: IntegrityError-Fallback im Endpoint ergänzen**

In `webhook_routes.py`, den Create-Block mit Race-Fallback erweitern:

```python
        from sqlalchemy.exc import IntegrityError
        try:
            ticket, method = ApiTicketFactory.create_from_payload(g.api_key, payload)
        except IntegrityError:
            db.session.rollback()
            existing = Ticket.query.filter_by(external_call_id=payload.data.id).first()
            if existing:
                g.api_outcome = "idempotent_replay"
                g.api_external_ref = payload.data.id
                return jsonify({
                    "ticket_id": existing.id, "status": "duplicate",
                }), 200
            raise
```

- [ ] **Step 3: Run + Commit**

```bash
python -m pytest tests/test_api_idempotency.py -v
git add -u
git commit -m "feat: IntegrityError-Fallback für parallele Duplicate-Calls"
```

### Task 4.8: Tests für IP-Allowlist End-to-End

**Files:**
- Create: `ticketsystem/tests/test_api_ip_allowlist.py`

- [ ] **Step 1: Test schreiben**

```python
"""End-to-end IP allowlist enforcement."""

import pytest

from services.api_key_service import ApiKeyService


@pytest.fixture
def allowlisted(app, db_session, admin_fixture, worker_fixture):
    key, plaintext = ApiKeyService.create_key(
        name="HP", scopes=["write:tickets"],
        default_assignee_id=worker_fixture.id,
        rate_limit_per_minute=1000, created_by_worker_id=admin_fixture.id,
    )
    ApiKeyService.add_ip_range(
        key.id, "203.0.113.0/24", note="t",
        created_by_worker_id=admin_fixture.id,
    )
    return plaintext


def test_allowed_ip_passes(client, allowlisted):
    r = client.post(
        "/api/v1/webhook/calls",
        json={"webhook_id": "w", "data": {"id": "ip_ok", "duration": 1,
                                          "topic": "t", "summary": "s",
                                          "messages": []}},
        headers={
            "Authorization": f"Bearer {allowlisted}",
            "CF-Connecting-IP": "203.0.113.42",
        },
    )
    assert r.status_code == 201


def test_blocked_ip_returns_403(client, allowlisted):
    r = client.post(
        "/api/v1/webhook/calls",
        json={"webhook_id": "w", "data": {"id": "ip_no", "duration": 1}},
        headers={
            "Authorization": f"Bearer {allowlisted}",
            "CF-Connecting-IP": "198.51.100.9",
        },
    )
    assert r.status_code == 403
    assert r.get_json() == {"error": "forbidden"}
```

- [ ] **Step 2: Run + Commit**

```bash
python -m pytest tests/test_api_ip_allowlist.py -v
git add ticketsystem/tests/test_api_ip_allowlist.py
git commit -m "test: End-to-end IP-Allowlist-Enforcement"
```

---

## Phase 5 — Retention-Jobs

### Task 5.1: Retention-Service + Tests

**Files:**
- Create: `ticketsystem/services/api_retention_service.py`
- Create: `ticketsystem/tests/test_api_retention.py`

- [ ] **Step 1: Tests schreiben**

```python
"""Retention job tests."""

from datetime import timedelta

from models import ApiAuditLog, Ticket, TicketTranscript
from services.api_retention_service import ApiRetentionService
from utils import get_utc_now


def test_audit_log_retention_deletes_old_entries(app, db_session):
    old = ApiAuditLog(
        timestamp=get_utc_now() - timedelta(days=91),
        source_ip="1.2.3.4", method="POST", path="/api/v1/x",
        status_code=200, latency_ms=1, outcome="success", request_id="old",
    )
    new = ApiAuditLog(
        timestamp=get_utc_now() - timedelta(days=1),
        source_ip="1.2.3.4", method="POST", path="/api/v1/x",
        status_code=200, latency_ms=1, outcome="success", request_id="new",
    )
    db_session.add_all([old, new])
    db_session.commit()
    deleted = ApiRetentionService.prune_audit_log(retention_days=90)
    assert deleted == 1
    assert ApiAuditLog.query.filter_by(request_id="new").count() == 1
    assert ApiAuditLog.query.filter_by(request_id="old").count() == 0


def test_transcript_retention_deletes_old_but_keeps_ticket(app, db_session):
    from models import Ticket, TicketContact
    t = Ticket(title="T", created_at=get_utc_now() - timedelta(days=95))
    db_session.add(t)
    db_session.flush()
    old_tr = TicketTranscript(
        ticket_id=t.id, position=0, role="user", content="old",
        created_at=get_utc_now() - timedelta(days=95),
    )
    new_tr = TicketTranscript(
        ticket_id=t.id, position=1, role="user", content="new",
        created_at=get_utc_now() - timedelta(days=5),
    )
    db_session.add_all([old_tr, new_tr])
    db_session.commit()
    deleted = ApiRetentionService.prune_transcripts(retention_days=90)
    assert deleted == 1
    assert Ticket.query.get(t.id) is not None
    assert len(Ticket.query.get(t.id).transcripts) == 1
```

- [ ] **Step 2: Service implementieren**

```python
"""Retention jobs for API-related PII data."""

from __future__ import annotations

from datetime import timedelta

from extensions import db
from models import ApiAuditLog, TicketTranscript
from services._helpers import db_transaction
from utils import get_utc_now


class ApiRetentionService:

    @staticmethod
    @db_transaction
    def prune_audit_log(retention_days: int = 90) -> int:
        cutoff = get_utc_now() - timedelta(days=retention_days)
        count = ApiAuditLog.query.filter(ApiAuditLog.timestamp < cutoff).delete(
            synchronize_session=False
        )
        db.session.commit()
        return count

    @staticmethod
    @db_transaction
    def prune_transcripts(retention_days: int = 90) -> int:
        cutoff = get_utc_now() - timedelta(days=retention_days)
        count = TicketTranscript.query.filter(
            TicketTranscript.created_at < cutoff
        ).delete(synchronize_session=False)
        db.session.commit()
        return count
```

- [ ] **Step 3: Run + Commit**

```bash
python -m pytest tests/test_api_retention.py -v
git add ticketsystem/services/api_retention_service.py ticketsystem/tests/test_api_retention.py
git commit -m "feat: Retention-Jobs für api_audit_log und ticket_transcript (90 Tage)"
```

### Task 5.2: Scheduler-Registrierung

**Files:**
- Modify: `ticketsystem/services/scheduler_service.py`

- [ ] **Step 1: Bestehenden Scheduler prüfen**

Run: `grep -n 'scheduler\|BackgroundScheduler\|add_job' ticketsystem/services/scheduler_service.py | head -20`

- [ ] **Step 2: Retention-Jobs ergänzen**

Beispiel-Muster (an Bestand anpassen):

```python
from services.api_retention_service import ApiRetentionService

def _register_api_retention_jobs(scheduler):
    scheduler.add_job(
        func=lambda: ApiRetentionService.prune_audit_log(90),
        trigger="cron", hour=3, minute=15,
        id="api_audit_retention", replace_existing=True,
    )
    scheduler.add_job(
        func=lambda: ApiRetentionService.prune_transcripts(90),
        trigger="cron", hour=3, minute=30,
        id="api_transcript_retention", replace_existing=True,
    )
```

In der zentralen Init-Funktion (wo bestehende Jobs registriert werden) aufrufen.

- [ ] **Step 3: Commit**

```bash
git add -u
git commit -m "feat: Retention-Jobs im Scheduler registrieren (täglich 03:15/03:30)"
```

---

## Phase 6 — Admin-UI

### Task 6.1: Admin-Routen-Gerüst + Berechtigung

**Files:**
- Create: `ticketsystem/routes/admin_api_keys.py`
- Modify: `ticketsystem/routes/__init__.py` (Registrierung)

- [ ] **Step 1: Datei schreiben**

```python
"""Admin UI for API key management, IP allowlist, and audit log viewer."""

from __future__ import annotations

import functools
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for,
)

from models import ApiKey, ApiAuditLog, Worker
from services.api_key_service import ApiKeyService


def _admin_required(view):
    """Only admin workers can manage API keys."""
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        worker = g.get("current_worker") if hasattr(g, "get") else None
        # Fallback zur bestehenden Session-Konvention im Projekt:
        worker = worker or _current_worker_from_session()
        if not worker or not worker.is_admin:
            return ("forbidden", 403)
        return view(*args, **kwargs)
    return wrapper


def _current_worker_from_session():
    from extensions import db
    wid = session.get("worker_id")
    if not wid:
        return None
    return db.session.get(Worker, wid)


def register_routes(bp: Blueprint) -> None:

    @bp.route("/admin/api-keys", methods=["GET"])
    @_admin_required
    def _api_keys_list():
        keys = ApiKey.query.order_by(ApiKey.created_at.desc()).all()
        return render_template("admin/api_keys_list.html", keys=keys)

    @bp.route("/admin/api-keys/new", methods=["GET", "POST"])
    @_admin_required
    def _api_keys_new():
        workers = Worker.query.filter_by(is_active=True).order_by(Worker.name).all()
        if request.method == "POST":
            try:
                key, plaintext = ApiKeyService.create_key(
                    name=request.form["name"],
                    scopes=request.form.getlist("scopes"),
                    default_assignee_id=int(request.form["default_assignee_id"]),
                    rate_limit_per_minute=int(request.form["rate_limit_per_minute"]),
                    created_by_worker_id=_current_worker_from_session().id,
                    expected_webhook_id=(request.form.get("expected_webhook_id") or None),
                    create_confidential_tickets=bool(
                        request.form.get("create_confidential_tickets")
                    ),
                )
                session["_just_created_token"] = plaintext
                return redirect(url_for("main._api_keys_created", key_id=key.id))
            except ValueError as exc:
                flash(str(exc), "error")
        return render_template("admin/api_key_form.html", workers=workers, key=None)

    @bp.route("/admin/api-keys/<int:key_id>/created", methods=["GET"])
    @_admin_required
    def _api_keys_created(key_id):
        plaintext = session.pop("_just_created_token", None)
        if not plaintext:
            return redirect(url_for("main._api_keys_list"))
        key = ApiKey.query.get_or_404(key_id)
        return render_template("admin/api_key_created.html", key=key, plaintext=plaintext)

    @bp.route("/admin/api-keys/<int:key_id>/edit", methods=["GET", "POST"])
    @_admin_required
    def _api_keys_edit(key_id):
        key = ApiKey.query.get_or_404(key_id)
        workers = Worker.query.filter_by(is_active=True).order_by(Worker.name).all()
        if request.method == "POST":
            action = request.form.get("action", "save")
            if action == "revoke":
                ApiKeyService.revoke_key(
                    key.id, revoked_by_worker_id=_current_worker_from_session().id,
                )
                flash("Schlüssel widerrufen.", "success")
                return redirect(url_for("main._api_keys_list"))
            # Save edits (name, rate_limit, default_assignee, etc.)
            key.name = request.form["name"]
            key.rate_limit_per_minute = int(request.form["rate_limit_per_minute"])
            key.default_assignee_worker_id = int(request.form["default_assignee_id"])
            key.expected_webhook_id = request.form.get("expected_webhook_id") or None
            key.create_confidential_tickets = bool(
                request.form.get("create_confidential_tickets")
            )
            from extensions import db
            db.session.commit()
            flash("Änderungen gespeichert.", "success")
            return redirect(url_for("main._api_keys_edit", key_id=key.id))

        # Recent observed IPs from audit log
        recent_ips = (
            ApiAuditLog.query
            .filter_by(api_key_id=key.id)
            .with_entities(ApiAuditLog.source_ip, ApiAuditLog.timestamp)
            .order_by(ApiAuditLog.timestamp.desc())
            .limit(100)
            .all()
        )
        ip_summary = _summarise_ips(recent_ips)
        return render_template(
            "admin/api_key_form.html",
            key=key, workers=workers, recent_ips=ip_summary,
        )

    @bp.route("/admin/api-keys/<int:key_id>/ip-ranges", methods=["POST"])
    @_admin_required
    def _api_keys_add_ip(key_id):
        cidr = request.form["cidr"]
        note = request.form.get("note") or None
        try:
            ApiKeyService.add_ip_range(
                key_id=key_id, cidr=cidr, note=note,
                created_by_worker_id=_current_worker_from_session().id,
            )
            flash("IP-Range hinzugefügt.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("main._api_keys_edit", key_id=key_id))

    @bp.route("/admin/api-keys/ip-ranges/<int:range_id>/delete", methods=["POST"])
    @_admin_required
    def _api_keys_remove_ip(range_id):
        from models import ApiKeyIpRange
        entry = ApiKeyIpRange.query.get_or_404(range_id)
        key_id = entry.api_key_id
        ApiKeyService.remove_ip_range(range_id)
        flash("IP-Range entfernt.", "success")
        return redirect(url_for("main._api_keys_edit", key_id=key_id))

    @bp.route("/admin/api-audit-log", methods=["GET"])
    @_admin_required
    def _api_audit_log():
        outcome = request.args.get("outcome")
        key_id = request.args.get("key_id", type=int)
        q = ApiAuditLog.query.order_by(ApiAuditLog.timestamp.desc())
        if outcome:
            q = q.filter_by(outcome=outcome)
        if key_id:
            q = q.filter_by(api_key_id=key_id)
        page = request.args.get("page", 1, type=int)
        pagination = q.paginate(page=page, per_page=50)
        keys = ApiKey.query.order_by(ApiKey.name).all()
        return render_template("admin/api_audit_log.html",
                               pagination=pagination, keys=keys)

    @bp.route("/admin/api-docs", methods=["GET"])
    @_admin_required
    def _api_docs():
        # Static page, rendered via template
        from flask import current_app
        api_base = current_app.config.get("API_PUBLIC_BASE_URL", "https://<your-domain>")
        return render_template("admin/api_docs.html", api_base=api_base)


def _summarise_ips(rows):
    """Group source_ips, return list of {ip, count, last_seen}."""
    from collections import Counter
    counts = Counter(r.source_ip for r in rows)
    last_seen = {}
    for r in rows:
        if r.source_ip not in last_seen:
            last_seen[r.source_ip] = r.timestamp
    result = []
    for ip, count in counts.most_common(10):
        result.append({"ip": ip, "count": count, "last_seen": last_seen[ip]})
    return result
```

- [ ] **Step 2: In `routes/__init__.py` registrieren**

```python
# Import-Liste erweitern:
from .admin_api_keys import register_routes as register_admin_api_keys

# Im _register_all:
register_admin_api_keys(bp)
```

- [ ] **Step 3: Commit**

```bash
git add ticketsystem/routes/admin_api_keys.py ticketsystem/routes/__init__.py
git commit -m "feat: Admin-UI-Routen für API-Key-Verwaltung und Audit-Viewer"
```

### Task 6.2: Template — api_keys_list.html

**Files:**
- Create: `ticketsystem/templates/admin/api_keys_list.html`

- [ ] **Step 1: Template schreiben (baut auf bestehendem Admin-Base-Template auf)**

```html
{% extends "admin/base_admin.html" %}
{% block title %}API-Schlüssel{% endblock %}
{% block content %}
<h1>API-Schlüssel</h1>
<a href="{{ url_for('main._api_keys_new') }}" class="btn btn-primary">
  + Neuen Schlüssel erstellen
</a>
<table class="admin-table">
  <thead>
    <tr>
      <th>Name</th><th>Prefix</th><th>Scopes</th>
      <th>Zuletzt genutzt</th><th>Status</th><th></th>
    </tr>
  </thead>
  <tbody>
    {% for k in keys %}
    <tr>
      <td>{{ k.name }}</td>
      <td><code>{{ k.key_prefix }}…</code></td>
      <td>{{ k.scopes }}</td>
      <td>{{ k.last_used_at.strftime('%Y-%m-%d %H:%M') if k.last_used_at else '—' }}</td>
      <td>
        {% if k.revoked_at %}
          <span class="status status-revoked">widerrufen</span>
        {% elif k.is_active %}
          <span class="status status-active">aktiv</span>
        {% else %}
          <span class="status status-inactive">inaktiv</span>
        {% endif %}
      </td>
      <td><a href="{{ url_for('main._api_keys_edit', key_id=k.id) }}">Bearbeiten</a></td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

Bestehende CSS-Klassen aus dem Projekt übernehmen. Falls abweichende Base-Template existiert, entsprechend anpassen.

- [ ] **Step 2: Commit**

```bash
git add ticketsystem/templates/admin/api_keys_list.html
git commit -m "feat: Template für API-Schlüssel-Listen-Ansicht"
```

### Task 6.3: Template — api_key_form.html (Create + Edit)

**Files:**
- Create: `ticketsystem/templates/admin/api_key_form.html`

- [ ] **Step 1: Template schreiben**

```html
{% extends "admin/base_admin.html" %}
{% block title %}{{ 'API-Schlüssel bearbeiten' if key else 'Neuen API-Schlüssel erstellen' }}{% endblock %}
{% block content %}
<h1>{{ 'API-Schlüssel bearbeiten' if key else 'Neuen API-Schlüssel erstellen' }}</h1>

<form method="POST">
  <label>Name
    <input name="name" required value="{{ key.name if key else '' }}">
  </label>

  <fieldset>
    <legend>Scopes</legend>
    {% set scope_list = key.scope_list() if key else [] %}
    <label><input type="checkbox" name="scopes" value="write:tickets"
      {% if 'write:tickets' in scope_list or not key %}checked{% endif %}>
      write:tickets</label>
    <label><input type="checkbox" name="scopes" value="read:tickets" disabled>
      read:tickets (Phase b)</label>
    <label><input type="checkbox" name="scopes" value="admin:tickets" disabled>
      admin:tickets (Phase c)</label>
  </fieldset>

  <label>Standard-Zuweisung (Pflicht bei write:tickets)
    <select name="default_assignee_id" required>
      {% for w in workers %}
        <option value="{{ w.id }}"
          {% if key and key.default_assignee_worker_id == w.id %}selected{% endif %}>
          {{ w.name }}
        </option>
      {% endfor %}
    </select>
  </label>

  <label>Rate-Limit / Minute
    <input type="number" name="rate_limit_per_minute" min="1"
           value="{{ key.rate_limit_per_minute if key else 60 }}" required>
  </label>

  <label>Erwartete webhook_id (optional)
    <input name="expected_webhook_id" value="{{ key.expected_webhook_id or '' }}">
  </label>

  <label>
    <input type="checkbox" name="create_confidential_tickets"
      {% if not key or key.create_confidential_tickets %}checked{% endif %}>
    Erzeugte Tickets als „vertraulich" markieren
  </label>

  <button type="submit">{{ 'Speichern' if key else 'Erstellen' }}</button>
</form>

{% if key %}
  <h2>IP-Allowlist</h2>
  {% if not key.ip_ranges %}
    <p>Leer — alle IPs erlaubt (nur Token-Check).</p>
  {% else %}
    <ul>
      {% for r in key.ip_ranges %}
        <li>
          <code>{{ r.cidr }}</code> — {{ r.note or '' }}
          <form method="POST"
                action="{{ url_for('main._api_keys_remove_ip', range_id=r.id) }}"
                style="display:inline">
            <button type="submit" onclick="return confirm('Eintrag löschen?')">🗑</button>
          </form>
        </li>
      {% endfor %}
    </ul>
  {% endif %}
  <form method="POST"
        action="{{ url_for('main._api_keys_add_ip', key_id=key.id) }}">
    <input name="cidr" placeholder="203.0.113.0/24" required>
    <input name="note" placeholder="Notiz">
    <button type="submit">+ Hinzufügen</button>
  </form>

  {% if recent_ips %}
  <h3>Zuletzt beobachtete Quell-IPs</h3>
  <table>
    <thead><tr><th>IP</th><th>Anzahl</th><th>Letzte Nutzung</th><th></th></tr></thead>
    <tbody>
      {% for r in recent_ips %}
      <tr>
        <td>{{ r.ip }}</td>
        <td>{{ r.count }}</td>
        <td>{{ r.last_seen.strftime('%Y-%m-%d %H:%M') }}</td>
        <td>
          <form method="POST"
                action="{{ url_for('main._api_keys_add_ip', key_id=key.id) }}"
                style="display:inline">
            <input type="hidden" name="cidr" value="{{ r.ip }}/32">
            <input type="hidden" name="note" value="Beob. {{ r.last_seen.strftime('%Y-%m-%d') }}">
            <button type="submit">+ /32</button>
          </form>
          <form method="POST"
                action="{{ url_for('main._api_keys_add_ip', key_id=key.id) }}"
                style="display:inline">
            <input type="hidden" name="cidr"
                   value="{{ r.ip.rsplit('.', 1)[0] }}.0/24">
            <input type="hidden" name="note" value="Beob. {{ r.last_seen.strftime('%Y-%m-%d') }}">
            <button type="submit">+ /24</button>
          </form>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% endif %}

  <h2>Widerruf</h2>
  <form method="POST"
        onsubmit="return confirm('Schlüssel wirklich widerrufen?')">
    <input type="hidden" name="action" value="revoke">
    <button type="submit" style="background:red;color:white">Widerrufen</button>
  </form>
{% endif %}
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add ticketsystem/templates/admin/api_key_form.html
git commit -m "feat: Template für API-Schlüssel Erstellen/Bearbeiten mit IP-Allowlist-Editor"
```

### Task 6.4: Template — api_key_created.html

**Files:**
- Create: `ticketsystem/templates/admin/api_key_created.html`

- [ ] **Step 1: Template schreiben**

```html
{% extends "admin/base_admin.html" %}
{% block title %}API-Schlüssel erstellt{% endblock %}
{% block content %}
<div class="alert alert-warning">
  <h2>⚠ Dies ist die einzige Gelegenheit, den Schlüssel zu kopieren.</h2>
  <p>Er wird nie wieder im Klartext angezeigt.</p>
</div>

<p>Schlüssel <strong>{{ key.name }}</strong>:</p>
<pre id="token-plain" style="font-size:1.2em; padding:1em; background:#f4f4f4;">{{ plaintext }}</pre>

<button onclick="navigator.clipboard.writeText(document.getElementById('token-plain').innerText)">
  📋 In die Zwischenablage kopieren
</button>

<form action="{{ url_for('main._api_keys_list') }}" method="GET">
  <button type="submit">Ich habe den Schlüssel sicher hinterlegt</button>
</form>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add ticketsystem/templates/admin/api_key_created.html
git commit -m "feat: Einmal-Anzeige-Template für neu erstellte API-Schlüssel"
```

### Task 6.5: Template — api_audit_log.html

**Files:**
- Create: `ticketsystem/templates/admin/api_audit_log.html`

- [ ] **Step 1: Template schreiben**

```html
{% extends "admin/base_admin.html" %}
{% block title %}API Zugriffs-Log{% endblock %}
{% block content %}
<h1>API Zugriffs-Log</h1>

<form method="GET" class="filters">
  <select name="key_id">
    <option value="">Alle Keys</option>
    {% for k in keys %}
      <option value="{{ k.id }}"
        {% if request.args.get('key_id')|int == k.id %}selected{% endif %}>
        {{ k.name }}
      </option>
    {% endfor %}
  </select>
  <select name="outcome">
    <option value="">Alle Outcomes</option>
    {% for o in ['success','auth_failed','ip_blocked','rate_limited',
                 'validation_failed','idempotent_replay','scope_denied',
                 'server_error'] %}
      <option value="{{ o }}"
        {% if request.args.get('outcome') == o %}selected{% endif %}>
        {{ o }}
      </option>
    {% endfor %}
  </select>
  <button type="submit">Filtern</button>
</form>

<table class="admin-table">
  <thead>
    <tr>
      <th>Zeit</th><th>Key</th><th>IP</th><th>Pfad</th>
      <th>Status</th><th>Outcome</th><th>Latency</th><th>Request-ID</th>
    </tr>
  </thead>
  <tbody>
    {% for e in pagination.items %}
    <tr>
      <td>{{ e.timestamp.strftime('%Y-%m-%d %H:%M:%S') }}</td>
      <td>{{ e.api_key.name if e.api_key else '(ungültig)' }}</td>
      <td>{{ e.source_ip }}</td>
      <td><code>{{ e.method }} {{ e.path }}</code></td>
      <td>{{ e.status_code }}</td>
      <td>{{ e.outcome }}</td>
      <td>{{ e.latency_ms }}ms</td>
      <td><code>{{ e.request_id[:8] }}</code></td>
    </tr>
    {% endfor %}
  </tbody>
</table>

{# Pagination (bestehenden Style übernehmen) #}
{% if pagination.has_prev %}
  <a href="?page={{ pagination.prev_num }}">« zurück</a>
{% endif %}
{% if pagination.has_next %}
  <a href="?page={{ pagination.next_num }}">weiter »</a>
{% endif %}
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add ticketsystem/templates/admin/api_audit_log.html
git commit -m "feat: Audit-Log-Viewer-Template mit Filtern und Pagination"
```

### Task 6.6: Template — api_docs.html (statische Doku)

**Files:**
- Create: `ticketsystem/templates/admin/api_docs.html`

- [ ] **Step 1: Template schreiben**

```html
{% extends "admin/base_admin.html" %}
{% block title %}API-Dokumentation{% endblock %}
{% block content %}
<h1>Public REST API — Dokumentation</h1>

<h2>Endpoint</h2>
<p><code>POST {{ api_base }}/api/v1/webhook/calls</code></p>

<h2>Authentifizierung</h2>
<p>HTTP-Header: <code>Authorization: Bearer tsk_&lt;token&gt;</code></p>
<p>Token-Format: <code>tsk_</code> + 48 alphanumerische Zeichen.</p>
<p>Tokens werden ausschließlich einmal bei Erstellung angezeigt. In der
Datenbank wird nur der SHA-256-Hash gespeichert. Das Präfix (erste 12
Zeichen) bleibt sichtbar zur Identifikation und Leak-Detection.</p>

<h2>Request-Format</h2>
<pre><code>{
  "webhook_id": "wh_...",
  "data": {
    "id": "call_...",
    "duration": 125,
    "phone": "+49...",
    "topic": "...",
    "summary": "...",
    "messages": [
      {"role": "assistant", "content": "..."},
      {"role": "user", "content": "..."}
    ],
    "contact_data": {
      "name": "...", "phone": "...",
      "email": "...", "address": "..."
    },
    "email_send_to": "mitarbeiter@firma.de",
    "forwarded_to": "+49...",
    ...
  }
}</code></pre>

<h2>Response-Codes</h2>
<ul>
  <li><strong>201 Created</strong> — Neues Ticket erzeugt:
      <code>{"ticket_id": 123, "status": "created"}</code></li>
  <li><strong>200 OK</strong> — Duplicate (gleiche <code>data.id</code>):
      <code>{"ticket_id": 123, "status": "duplicate"}</code></li>
  <li><strong>400</strong> — Schema-/Validation-Fehler</li>
  <li><strong>401</strong> — Authentifizierungs-Fehler (generisch)</li>
  <li><strong>403</strong> — Scope oder IP abgelehnt (generisch)</li>
  <li><strong>413</strong> — Payload &gt; 128 KB</li>
  <li><strong>415</strong> — Kein JSON-Content-Type</li>
  <li><strong>429</strong> — Rate-Limit überschritten</li>
  <li><strong>500</strong> — Server-Fehler, <code>request_id</code> im Body</li>
</ul>

<h2>Idempotenz</h2>
<p>Die <code>data.id</code> im Payload wird als eindeutiger Schlüssel
verwendet. Zweite Requests mit identischer <code>data.id</code> liefern
200 mit der ursprünglichen <code>ticket_id</code> — es wird kein zweites
Ticket erzeugt.</p>

<h2>Rate-Limit</h2>
<p>Pro API-Schlüssel konfigurierbar (Sliding Window, 1 Minute).
Überschreitung → 429 mit <code>retry_after</code>-Sekunden.</p>

<h2>IP-Allowlist</h2>
<p>Optional pro Schlüssel. Leere Allowlist = alle IPs zulässig. Sobald
mindestens ein CIDR hinterlegt ist, werden nur Requests aus diesen Ranges
akzeptiert.</p>

<h2>Retention</h2>
<ul>
  <li><strong>Gesprächstranskripte</strong>: 90 Tage, danach automatisch gelöscht.
      Das Ticket selbst bleibt bestehen (mit Summary, ohne wörtliches Protokoll).</li>
  <li><strong>API-Audit-Log</strong>: 90 Tage.</li>
</ul>

<h2>DSGVO</h2>
<p>Diese API empfängt personenbezogene Daten (Telefonnummern, Namen,
Gesprächstranskripte). Der Betrieb setzt einen Auftragsverarbeitungs-
Vertrag mit dem Webhook-Absender voraus.</p>

<hr>

<h2>Anhang — Webadmin-Anleitung (DNS-Setup)</h2>
<p>Für die Einrichtung der API-Subdomain bitte an den Webadmin weiterleiten:</p>
<p>Siehe <a href="/static/docs/webadmin-dns-instructions.md">Webadmin-Anleitung</a>.</p>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add ticketsystem/templates/admin/api_docs.html
git commit -m "feat: Statische API-Doku-Seite mit allen Endpoint-Details"
```

### Task 6.7: Menü-Eintrag in Admin-Base-Template

**Files:**
- Modify: bestehendes Admin-Base-Template (z. B. `ticketsystem/templates/admin/base_admin.html`)

- [ ] **Step 1: Bestehendes Menü finden und neuen Eintrag ergänzen**

```html
<!-- Im Nav-Block, nach bestehenden Admin-Einträgen: -->
<li><a href="{{ url_for('main._api_keys_list') }}">API-Zugriff</a>
  <ul>
    <li><a href="{{ url_for('main._api_keys_list') }}">API-Schlüssel</a></li>
    <li><a href="{{ url_for('main._api_audit_log') }}">Zugriffs-Log</a></li>
    <li><a href="{{ url_for('main._api_docs') }}">Dokumentation</a></li>
  </ul>
</li>
```

- [ ] **Step 2: Commit**

```bash
git add -u
git commit -m "feat: Admin-Menüpunkt 'API-Zugriff' mit Submenu"
```

### Task 6.8: UI-Tests

**Files:**
- Create: `ticketsystem/tests/test_admin_api_keys_ui.py`

- [ ] **Step 1: Tests schreiben**

```python
"""UI route tests for admin API-key management."""

import pytest

from models import ApiKey


def _login_as_admin(client, admin_fixture):
    with client.session_transaction() as s:
        s["worker_id"] = admin_fixture.id


def _login_as_worker(client, worker_fixture):
    with client.session_transaction() as s:
        s["worker_id"] = worker_fixture.id


def test_list_requires_admin(client, worker_fixture):
    _login_as_worker(client, worker_fixture)
    r = client.get("/admin/api-keys")
    assert r.status_code == 403


def test_list_as_admin_returns_200(client, admin_fixture):
    _login_as_admin(client, admin_fixture)
    r = client.get("/admin/api-keys")
    assert r.status_code == 200


def test_create_flow_shows_token_once(client, admin_fixture, worker_fixture):
    _login_as_admin(client, admin_fixture)
    r = client.post("/admin/api-keys/new", data={
        "name": "Test", "scopes": ["write:tickets"],
        "default_assignee_id": str(worker_fixture.id),
        "rate_limit_per_minute": "60",
        "create_confidential_tickets": "on",
    }, follow_redirects=False)
    assert r.status_code == 302  # redirect to /created
    # Token in Response-HTML des created-Views
    r2 = client.get(r.headers["Location"])
    assert r2.status_code == 200
    assert b"tsk_" in r2.data
    # Reload derselben Seite zeigt Token NICHT mehr
    r3 = client.get(r.headers["Location"])
    assert b"tsk_" not in r3.data


def test_revoke_sets_status(client, admin_fixture, worker_fixture, db_session):
    _login_as_admin(client, admin_fixture)
    from services.api_key_service import ApiKeyService
    key, _ = ApiKeyService.create_key(
        name="K", scopes=["write:tickets"],
        default_assignee_id=worker_fixture.id,
        rate_limit_per_minute=60, created_by_worker_id=admin_fixture.id,
    )
    r = client.post(f"/admin/api-keys/{key.id}/edit", data={
        "action": "revoke",
    }, follow_redirects=False)
    assert r.status_code == 302
    db_session.refresh(key)
    assert key.revoked_at is not None
    assert key.is_active is False
```

- [ ] **Step 2: Run + Commit**

```bash
python -m pytest tests/test_admin_api_keys_ui.py -v
git add ticketsystem/tests/test_admin_api_keys_ui.py
git commit -m "test: UI-Tests für API-Key-Verwaltung (Admin-Zugriff, Einmal-Anzeige, Widerruf)"
```

---

## Phase 7 — Dokumentation (Handbuch, Checkliste, Webadmin)

### Task 7.1: Webadmin-DNS-Anleitung

**Files:**
- Create: `docs/operations/webadmin-dns-instructions.md`

- [ ] **Step 1: Datei schreiben**

```markdown
# DNS-Konfiguration für die API-Subdomain

## Ziel
Eine neue Subdomain `ticket-api.euredomain.de` soll auf den Cloudflare Tunnel
des Ticketsystems zeigen.

## Vorgehen

1. Im DNS-Management der Domain `euredomain.de` einen **CNAME-Eintrag** anlegen:
   - **Name:** `ticket-api`
   - **Ziel:** `<tunnel-id>.cfargotunnel.com` (konkreter Wert wird vom
     Betreiber nach Tunnel-Einrichtung mitgeteilt)
   - **TTL:** 300 (5 Minuten) zunächst, nach Validierung auf 3600 erhöhen

2. **KEIN A-Record**, **KEIN MX-Record**, **KEINE Port-Weiterleitung** nötig.
   Cloudflare terminiert TLS und stellt das Zertifikat automatisch aus.

3. Propagation prüfen:
   ```
   dig ticket-api.euredomain.de CNAME
   ```

## Sicherheit

Die Subdomain ist ausschließlich für die HalloPetra-Webhook-Integration.
Keine E-Mail-Einträge, keine weiteren Services. Bitte diese Subdomain nicht
für andere Zwecke verwenden.

## Bei Fragen
Rückfrage an den Betreiber (Ticketsystem-Admin).
```

- [ ] **Step 2: Commit**

```bash
git add docs/operations/webadmin-dns-instructions.md
git commit -m "docs: Webadmin-Anleitung für DNS-Konfiguration der API-Subdomain"
```

### Task 7.2: Pre-Launch-Checkliste

**Files:**
- Create: `docs/operations/api-prelaunch-checklist.md`

- [ ] **Step 1: Checkliste schreiben (aus Spec Abschnitt 7.8 ableiten)**

```markdown
# Public REST API — Pre-Launch-Checkliste

Vor Aktivierung des Cloudflare Tunnels alle Punkte abhaken.

## Netzwerk
- [ ] NGINX: `/api/v1/` ist die einzige öffentlich erreichbare Location
- [ ] Cloudflare Tunnel Ingress-Regel: nur `/api/v1/*`
- [ ] `curl https://<subdomain>/api/v1/health` → 200
- [ ] `curl -X POST https://<subdomain>/api/v1/webhook/calls` (ohne Token) → 401
- [ ] `curl https://<subdomain>/login` → 403 oder 404
- [ ] `curl https://<subdomain>/` → 403 oder 404
- [ ] `curl https://<subdomain>/admin/api-keys/` → 403 oder 404
- [ ] Security-Header via securityheaders.com getestet: Score ≥ A
- [ ] CSP ohne Browser-Console-Errors (UI durchklicken)

## Flask-Konfiguration
- [ ] `DEBUG = False` in Produktion
- [ ] `SECRET_KEY` auf 64-Byte Random rotiert
- [ ] `SESSION_COOKIE_SECURE = True`
- [ ] `SESSION_COOKIE_HTTPONLY = True`
- [ ] `SESSION_COOKIE_SAMESITE = 'Lax'`
- [ ] `MAX_CONTENT_LENGTH` explizit gesetzt (128 KB für API)

## Infrastruktur
- [ ] SQLite-Backup-Cronjob läuft, `/backup/` enthält tägliche Snapshots
- [ ] Dependency-Audit durchgelaufen, keine HIGH/CRITICAL offen
- [ ] Alle Secrets in HA-Add-on-Secrets (nicht in .env)
- [ ] `.env`-Datei nicht in Git (`git ls-files | grep env` leer)

## API-Integration
- [ ] Admin-UI: Admin-Rolle kann `/admin/api-keys` aufrufen, Nicht-Admin 403
- [ ] Staging-Key erstellt, Klartext notiert
- [ ] Staging-Webhook erfolgreich getestet (mind. 5 Szenarien)
- [ ] Audit-Log-Tabelle wächst bei Tests wie erwartet
- [ ] Produktions-Key erstellt (erst kurz vor Launch-Moment)

## Dokumentation
- [ ] Webadmin hat DNS-Anleitung erhalten und umgesetzt
- [ ] Betriebshandbuch vorhanden (`public-api-handbook.md`)
- [ ] API-Dokumentation online erreichbar (`/admin/api-docs`)

## Sign-Off
- [ ] Betreiber: _______________  Datum: _____________
```

- [ ] **Step 2: Commit**

```bash
git add docs/operations/api-prelaunch-checklist.md
git commit -m "docs: Pre-Launch-Checkliste als hakbares Markdown"
```

### Task 7.3: Betriebshandbuch

**Files:**
- Create: `docs/operations/public-api-handbook.md`

- [ ] **Step 1: Handbuch schreiben**

```markdown
# Public REST API — Betriebshandbuch

Dokumentation der Test-, Staging-, Rollout-, Monitoring- und Rollback-Prozesse
für die HalloPetra-Webhook-Integration.

## 1. Testing

### 1.1 Pytest-Ausführung

```bash
cd ticketsystem
python -m pytest tests/ -v
```

**Baseline:** 7 passed, 8 known failures (siehe CLAUDE.md). Neue API-Tests
müssen **zusätzlich** grün sein.

### 1.2 Flake-Check

```bash
python -m flake8 --max-line-length=120 routes/api/ services/api_*.py
```

### 1.3 Smoke-Test (manuell, lokal)

1. App starten, Admin-Login
2. `/admin/api-keys/new` → Key anlegen, Klartext kopieren
3. `curl -X POST http://localhost:5000/api/v1/webhook/calls \
   -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
   -d '{"webhook_id":"w","data":{"id":"smoke_1","duration":1,
   "topic":"Test","summary":"s","messages":[]}}'` → 201
4. Ticket im UI prüfen: Titel, Contact-Channel „Telefon (KI-Agent)", Assignee
5. Zweiter Call mit gleichem `id` → 200 + gleiche `ticket_id`
6. `/admin/api-audit-log` → Einträge vorhanden

## 2. Staging

### 2.1 Einrichtung

- Separate Flask-Instanz mit eigener SQLite-DB auf Staging-Host
- Eigener Cloudflare Tunnel und Subdomain `ticket-api-staging.euredomain.de`
- Im Admin-UI: Key „HalloPetra Staging" anlegen, IP-Allowlist **leer lassen**
- HalloPetra-Testnummer vom Anbieter anfordern, mit Staging-URL konfigurieren

### 2.2 Testszenarien (mindestens 5 Anrufe)

1. Einfacher Anruf mit Contact-Data
2. Anruf mit Weiterleitung (`forwarded_to` gesetzt)
3. Anruf mit `email_send_to` das auf existierenden Worker matcht
4. Anruf mit `email_send_to` das auf niemanden matcht (Fallback)
5. Abgebrochener Anruf (evtl. andere Payload-Struktur)

### 2.3 IP-Beobachtung

Nach 2 Wochen Staging in `/admin/api-keys/<id>/edit` die „Zuletzt beobachteten
Quell-IPs" prüfen. Muster dokumentieren: `/24`-Ranges oder Einzel-IPs?

## 3. Rollout (6-Schritte-Plan)

Siehe Pre-Launch-Checkliste + Schritt-Definitionen im Spec Abschnitt 9.4.

Je Schritt:
1. Schritt-Ziel benennen
2. Vor-Ausführung: Backup prüfen (`ls -lht /backup | head -3`)
3. Ausführen
4. Verifikations-Check
5. Bei Problem → Schritt-spezifischer Rollback (Abschnitt 5 dieses Handbuchs)
6. Bei Erfolg → nächster Schritt

## 4. Monitoring

### 4.1 Tägliche Routine (erste 2 Wochen nach Launch)

1. `/admin/api-audit-log?outcome=auth_failed` prüfen:
   - Erwartung: Null Einträge
   - > 10 pro Stunde → möglicher Brute-Force-Versuch → siehe 5.2
2. `/admin/api-audit-log?outcome=server_error` prüfen:
   - Erwartung: Null Einträge
   - Jeden Eintrag einzeln debuggen via `request_id` im App-Log
3. `/admin/api-audit-log?outcome=ip_blocked` prüfen:
   - Nach Allowlist-Aktivierung: Null
   - Vorher: erwartet (das ist gewollt)

### 4.2 Wöchentliche Routine

- SQLite-DB-Größe: `ls -la /data/ticketsystem.db`
- Wenn > 500 MB: Audit-Log-Retention auf 60 Tage verkürzen
- Backup-Retention verifizieren: `ls /backup | wc -l` → ~14

### 4.3 KPIs

- Anzahl erfolgreich erstellter Tickets/Tag via API
- Fehlerquote (non-success outcomes / total)
- Durchschnittliche Latency (aus `api_audit_log.latency_ms`)

## 5. Rollback

### 5.1 Schnell — API komplett offline

```bash
# Cloudflare Tunnel stoppen (HA Add-on UI: cloudflared deaktivieren)
# Oder via cloudflared Service-Command:
systemctl stop cloudflared  # je nach Setup
```
**Wirkung:** API ab sofort unerreichbar von außen. App läuft weiter.

### 5.2 Mittel — Einzelnen Key widerrufen

Im Admin-UI unter `/admin/api-keys/<id>/edit` → „Widerrufen".
HalloPetra bekommt ab sofort 401 bei jedem Call.

### 5.3 Notfall — DB-Backup einspielen

```bash
systemctl stop ticketsystem-addon  # App stoppen
cp /backup/ticketsystem_YYYYMMDD_HHMMSS.db /data/ticketsystem.db
systemctl start ticketsystem-addon
```

**Wichtig:** DB-Rollback verwirft alle Änderungen seit dem Backup-Zeitpunkt.
Nur im Notfall. Vorher immer aktuellen Stand extra sichern:
```bash
cp /data/ticketsystem.db /tmp/before_rollback.db
```

## 6. Incident-Response

### 6.1 `auth_failed`-Flood (> 10/h)

1. Audit-Log filtern nach `outcome=auth_failed`
2. Häufigste `source_ip` identifizieren
3. Entscheidung:
   - IP in Cloudflare blocken (Cloudflare Dashboard → Firewall)
   - Oder: Produktions-Key widerrufen + neu anlegen (falls Token geleakt)

### 6.2 Key-Leak (Token in öffentlichem Log/Commit entdeckt)

1. Key sofort widerrufen
2. Neuen Key anlegen, Klartext an HalloPetra-Konfiguration übergeben
3. Grep-Suche nach dem Prefix in öffentlichen Logs/Repos
4. Audit-Log der letzten Tage durchsehen, nach untypischen `source_ip`

### 6.3 HalloPetra-Timeout-Beschwerden

1. `api_audit_log` nach Latency filtern:
   ```sql
   SELECT * FROM api_audit_log
   WHERE latency_ms > 8000
   ORDER BY timestamp DESC LIMIT 50;
   ```
2. Wenn konsistent > 2s: SQLite-Performance-Check (größe, fragmentation)
3. Gegenmaßnahme: async Background-Job für Ticket-Erzeugung einführen
   (Phase c, siehe Spec Out-of-Scope)
```

- [ ] **Step 2: Commit**

```bash
git add docs/operations/public-api-handbook.md
git commit -m "docs: Betriebshandbuch für Testing/Staging/Rollout/Monitoring/Rollback"
```

---

## Phase 8 — Pre-Launch Härtung (Infrastruktur-Änderungen)

Diese Phase enthält **Infrastruktur-Tasks**, die vom Betreiber ausgeführt werden.
Code-Änderungen im Repo sind minimal.

### Task 8.1: Flask-Härtungs-Checks

**Files:**
- Modify: `ticketsystem/app.py`

- [ ] **Step 1: Sicherheits-Settings explizit setzen**

```python
# Nach bestehender Config-Initialisierung
app.config.update(
    MAX_CONTENT_LENGTH=128 * 1024,       # 128 KB
    SESSION_COOKIE_SECURE=not app.debug, # True in Prod
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PROPAGATE_EXCEPTIONS=False,
)
```

- [ ] **Step 2: Import-Check**

```bash
cd ticketsystem && python -c "from app import app; print(app.config['MAX_CONTENT_LENGTH'])"
```

Expected: `131072`

- [ ] **Step 3: Commit**

```bash
git add ticketsystem/app.py
git commit -m "feat: Flask-Sicherheits-Config explizit für Public-API-Launch"
```

### Task 8.2: NGINX-Konfigurations-Snippet (als Dokumentation)

**Files:**
- Create: `docs/operations/nginx-snippets.md`

- [ ] **Step 1: NGINX-Regeln dokumentieren**

```markdown
# NGINX-Konfiguration für Public REST API

In der HA-Add-on NGINX-Config folgende Änderungen vornehmen.

## Security-Header (global)

```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header Referrer-Policy "same-origin" always;
add_header Content-Security-Policy "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'" always;
server_tokens off;  # keine Version im Server-Header
```

## API-Location (Defense-in-Depth zusätzlich zu Cloudflare Ingress)

```nginx
location /api/v1/ {
    proxy_pass http://flask_upstream;
    client_max_body_size 128k;
    proxy_read_timeout 8s;
    proxy_connect_timeout 2s;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $http_cf_connecting_ip;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header Cookie "";  # keine Session-Cookies in die API
}
```

## Cloudflare-Tunnel Ingress-Regeln

In `cloudflared/config.yml`:

```yaml
tunnel: <tunnel-uuid>
credentials-file: /etc/cloudflared/<tunnel-uuid>.json

ingress:
  - hostname: ticket-api.euredomain.de
    path: ^/api/v1/.*$
    service: http://localhost:8099
  - hostname: ticket-api.euredomain.de
    service: http_status:404
  - service: http_status:404
```

Die zweite Regel fängt alle Pfade, die nicht `/api/v1/...` matchen, und liefert
404 direkt vom Tunnel. Kein Durchstecken auf die Flask-App.
```

- [ ] **Step 2: Commit**

```bash
git add docs/operations/nginx-snippets.md
git commit -m "docs: NGINX- und cloudflared-Konfigurationsbeispiele"
```

### Task 8.3: Cloudflared-Template

**Files:**
- Create: `ticketsystem/cloudflared/config.yml.example`

- [ ] **Step 1: Template schreiben**

```yaml
# Cloudflared Tunnel Ingress-Konfiguration für Public API (HalloPetra)
#
# Vor Verwendung:
# 1. Tunnel anlegen: `cloudflared tunnel create ticket-api`
# 2. Tunnel-UUID und credentials-file unten einsetzen
# 3. Diese Datei nach config.yml kopieren
# 4. Cloudflared starten: `cloudflared tunnel run ticket-api`

tunnel: TUNNEL_UUID_HERE
credentials-file: /etc/cloudflared/TUNNEL_UUID_HERE.json

ingress:
  # Nur /api/v1/* durchlassen
  - hostname: ticket-api.euredomain.de
    path: ^/api/v1/.*$
    service: http://localhost:8099
    originRequest:
      connectTimeout: 5s
      noTLSVerify: true  # LAN-intern, kein TLS

  # Alles andere auf derselben Subdomain: 404 direkt vom Tunnel
  - hostname: ticket-api.euredomain.de
    service: http_status:404

  # Fallback
  - service: http_status:404
```

- [ ] **Step 2: Commit**

```bash
git add ticketsystem/cloudflared/config.yml.example
git commit -m "feat: cloudflared Tunnel-Konfigurations-Template"
```

---

## Phase 9 — Finalisierung & Baseline-Check

### Task 9.1: Gesamt-Testlauf

- [ ] **Step 1: Alle Tests**

```bash
cd ticketsystem && python -m pytest tests/ -v 2>&1 | tail -30
```

**Erwartung:**
- Baseline: 7 passed, 8 known failures — UNVERÄNDERT
- Neue API-Tests: ALLE grün (19 kritische + ergänzende)
- Gesamt: ≥ 26 passed, 8 known failures

Bei neuen Failures: debuggen, nicht ignorieren.

- [ ] **Step 2: Flake-Check gesamt**

```bash
python -m flake8 --max-line-length=120 routes/ services/ *.py
```

Keine neuen Warnings.

### Task 9.2: Dockerfile-Check

- [ ] **Step 1: Manuell verifizieren**

```bash
grep -c "^COPY " ticketsystem/Dockerfile
```

Die neuen Top-Level-Python-Dateien in diesem Projekt sind: **keine**.
Alle neuen Dateien liegen in `routes/api/` (Directory) oder `services/`
(Directory). Laut `CLAUDE.md`-Projekt-Regel: keine Dockerfile-Änderung nötig.

**Verifikation:**
```bash
ls ticketsystem/*.py  # keine neuen Dateien auf Top-Level
```

### Task 9.3: Import-Check der Gesamt-App

- [ ] **Step 1:**

```bash
cd ticketsystem && python -c "from app import app; print(len(list(app.url_map.iter_rules())))"
```

Anzahl Routes sollte deutlich höher sein als vorher (neue Admin- und API-Routen).

- [ ] **Step 2: Route-Check**

```bash
cd ticketsystem && python -c "
from app import app
api_routes = [r.rule for r in app.url_map.iter_rules() if '/api/v1' in r.rule]
admin_routes = [r.rule for r in app.url_map.iter_rules() if '/admin/api-' in r.rule]
print('API:', api_routes)
print('Admin:', admin_routes)
"
```

Expected:
- API: `/api/v1/health`, `/api/v1/webhook/calls`
- Admin: mehrere `/admin/api-keys/*` und `/admin/api-audit-log`, `/admin/api-docs`

### Task 9.4: Final Commit + Branch-Status

- [ ] **Step 1: Git-Status**

```bash
git status
```

Expected: clean working tree.

- [ ] **Step 2: Log**

```bash
git log --oneline main..HEAD | wc -l
```

Erwartet: ~40 Commits (je nach Task-Granularität).

- [ ] **Step 3: Push**

```bash
git push -u origin claude/public-api-hallopetra-2026-04-12
```

---

## Phase 10 — Staging & Produktions-Rollout (Betrieb)

Diese Phase wird **nicht vom Entwicklungs-Agenten** ausgeführt, sondern vom
Betreiber. Als Referenz dokumentiert, damit der Übergang nahtlos ist.

### Task 10.1: Staging-Deployment

- [ ] Staging-Subdomain via Webadmin beantragen
- [ ] Cloudflare Tunnel für Staging einrichten (`ticket-api-staging.euredomain.de`)
- [ ] Separate Flask-Instanz mit eigener SQLite-DB starten
- [ ] Alembic-Migration auf Staging-DB ausführen
- [ ] Admin-Login, Key „HalloPetra Staging" anlegen, Klartext an HalloPetra

### Task 10.2: HalloPetra-Webhook konfigurieren (Staging)

- [ ] HalloPetra-Dashboard öffnen
- [ ] Webhook-URL auf `https://ticket-api-staging.euredomain.de/api/v1/webhook/calls`
- [ ] Custom Header: `Authorization: Bearer <staging-token>`
- [ ] Testnummer anfordern

### Task 10.3: Staging-Testanrufe (2 Wochen)

- [ ] 5 Anruf-Szenarien durchführen (siehe Handbuch 2.2)
- [ ] Jeden Anruf gegen erwartetes Ticket prüfen
- [ ] Täglich Audit-Log auf Anomalien sichten

### Task 10.4: IP-Beobachtung

- [ ] Nach 2 Wochen `/admin/api-keys/<id>/edit` → „Zuletzt beobachtete IPs"
- [ ] Muster dokumentieren (`/24`? einzelne IPs? geografische Herkunft?)

### Task 10.5: Produktions-Key anlegen

- [ ] Am Launch-Tag: `/admin/api-keys/new`
  - Name: „HalloPetra Produktion"
  - Scopes: write:tickets
  - Rate-Limit: 60/min
  - Default-Assignee: Rezeption
  - Confidential: ja
- [ ] Klartext in Passwort-Safe hinterlegen

### Task 10.6: Go-Live

- [ ] Pre-Launch-Checkliste (`api-prelaunch-checklist.md`) vollständig abhaken
- [ ] HalloPetra-Konfiguration: Staging-URL → Prod-URL umstellen
- [ ] Produktions-Key in HalloPetra-Header eintragen
- [ ] Nach erstem echten Anruf: Audit-Log + Ticket prüfen

### Task 10.7: Allowlist-Aktivierung (2–5 Tage nach Launch)

- [ ] In Admin-UI des Produktions-Keys die beobachteten Prod-IPs sammeln
- [ ] Als CIDR-Ranges eintragen (vorzugsweise `/24`)
- [ ] Nach Speicherung: nächsten echten Anruf beobachten (Audit-Log: `outcome=success`)
- [ ] Fremde IPs werden ab jetzt blockiert (404/403 bei Test mit fremder IP)

---

## Self-Review-Ergebnis

**Spec-Abdeckung** (Spec Abschnitte → Plan Tasks):

| Spec-Abschnitt | Plan-Task |
|---|---|
| 2.1 Netzwerk-Topologie | Task 8.3 (cloudflared-Template), Task 10.1 |
| 2.2 Blueprint-Isolation | Task 3.1 |
| 2.3 Routen-Layout | Task 3.1, Task 4.6 |
| 2.4 Dateistruktur | File-Structure-Sektion oben |
| 3.1 ApiKey | Task 1.3 |
| 3.2 ApiKeyIpRange | Task 1.4 |
| 3.3 ApiAuditLog | Task 1.5 |
| 3.4 TicketTranscript | Task 1.6 |
| 3.5 Ticket-Erweiterungen | Task 1.2 |
| 3.6 Indexes | Task 1.7 |
| 4.1 Pydantic-Schema | Task 4.1, 4.2 |
| 4.2 Ticket-Mapping | Task 4.4 |
| 4.3 Zuweisungs-Logik | Task 4.4 (`_resolve_assignee`) |
| 4.4 Idempotenz | Task 4.6, 4.7 |
| 4.5 Synchrone Verarbeitung | Task 4.6 |
| 4.6 Response-Codes | Task 4.6, 3.3 |
| 5 Auth-Pipeline | Task 3.2, 3.3, 3.4 |
| 6 Admin-UI | Task 6.1 – 6.8 |
| 7 Pre-Launch-Härtung | Task 8.1, 8.2 + Pre-Launch-Checkliste (Task 7.2) |
| 8 DSGVO / Transkripte | Task 1.6, 4.4, 5.1, 5.2 |
| 9 Testing & Rollout | Task 9.1, Task 10.* |
| 10 Betriebshandbuch | Task 7.3 |
| 11 Deliverables | vollständig abgedeckt |

Keine Gaps identifiziert.

**Type-Konsistenz geprüft:**
- `ApiKeyService.authenticate` raised `InvalidApiKey`: konsistent über Tasks 2.4, 3.2
- `ApiKeyService.check_ip` raised `IpNotAllowed`: konsistent Task 2.5, 3.2
- `ApiTicketFactory.create_from_payload` returned `Tuple[Ticket, str]`: Task 4.4, 4.6
- `ApiRetentionService` Methoden-Namen: `prune_audit_log`, `prune_transcripts` — konsistent Task 5.1, 5.2
- Decorator-Reihenfolge: `@api_key_required` → `@require_scope` → `@api_rate_limit` — konsistent Tasks 3.2, 3.3, 3.4, 4.6

**Keine Placeholders** (grep für „TBD", „TODO" in diesem Dokument liefert null
Code-Placeholders — die bewussten „Phase b/c" Verweise sind Scope-Markierungen).
