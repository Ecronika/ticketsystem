# Public REST API für HalloPetra-Webhook — Design-Dokument

**Datum:** 2026-04-12
**Branch:** `claude/bug-fixes-audit-2026-04-12` (Basis für folgenden Feature-Branch)
**Autor:** Brainstorming-Session mit Claude
**Ambitionsniveau:** Ansatz B (Mittelweg, Vorbereitung auf Phase b/c)

## 1. Kontext und Ziel

Das Ticketsystem ist derzeit ausschließlich im lokalen Netz erreichbar. Die
einzige Schnittstelle nach außen ist der SMTP-Versand. Zur
Produktivitätssteigerung soll ein externes KI-Telefonsystem (HalloPetra) über
einen Webhook Tickets automatisch anlegen können. Der Webhook-Anbieter
erwartet eine öffentlich erreichbare HTTPS-URL und sendet nach jedem Anruf
einen JSON-Payload.

Das System-Erreichbarkeitsprofil ändert sich dadurch grundlegend: aus einer
LAN-only-Anwendung wird eine internetfähige Anwendung. Dieses Spec
beschreibt die vorbereitenden Maßnahmen zur sicheren Integration in drei
Phasen:

- **Phase a (Umfang dieses Specs):** Write-only-API, ausschließlich
  Ticket-Erzeugung über HalloPetra-Webhook
- **Phase b (geplant, nicht Umfang):** Lesezugriff auf Tickets
- **Phase c (geplant, nicht Umfang):** Voller Workflow (Zuweisungen,
  Kommentare, Status)

Phase a wird so gebaut, dass Phase b/c ohne Re-Design ergänzbar sind —
insbesondere über das Scope-System der API-Schlüssel.

## 2. Architektur-Überblick

### 2.1 Netzwerk-Topologie

```
┌────────────────┐    HTTPS     ┌─────────────────┐   Tunnel    ┌─────────────────┐
│  HalloPetra    │ ──────────▶  │   Cloudflare    │ ──────────▶ │  cloudflared    │
│ (Webhook-Abs.) │              │  (TLS, WAF,     │             │  (in LAN)       │
└────────────────┘              │   Rate-Limit,   │             └────────┬────────┘
                                │   IP-Logs)      │                      │ HTTP (LAN)
                                └─────────────────┘                      ▼
                                                                ┌─────────────────┐
                                                                │  NGINX (HA-AO)  │
                                                                │  nur /api/v1/*  │
                                                                └────────┬────────┘
                                                                         ▼
                                                                ┌─────────────────┐
                                                                │  Flask api_bp   │
                                                                └─────────────────┘
```

**Entscheidung: Cloudflare Tunnel** als alleiniger öffentlicher Eingangspunkt.

Begründung:
- Kein offener Port im Router → reduziert Layer-3/4-Angriffsfläche auf null
- TLS, Zertifikats-Rotation, DDoS-Schutz, Bot-Fight-Mode ohne eigene Konfiguration
- Cloudflare-seitiges Rate-Limit als erste Schicht (Flask-Limiter als zweite)
- True-Client-IP kommt via `CF-Connecting-IP`-Header durch — Voraussetzung
  für die IP-Allowlist (Abschnitt 5.2)
- Kostenlos für das erwartete Volumen

**NGINX-Konfigurations-Änderungen:**
- Neuer Location-Block `/api/v1/` mit `client_max_body_size 128k`,
  `proxy_read_timeout 8s`, `proxy_set_header X-Real-IP $http_cf_connecting_ip`
- Cookie-Header wird für `/api/v1/`-Routen explizit geleert
  (`proxy_set_header Cookie "";`)
- **Harte Regel:** Der Cloudflare Tunnel darf ausschließlich `/api/v1/*`
  erreichen. UI-Routen bleiben LAN-only.

**Subdomain:** Eine neue Subdomain (z. B. `ticket-api.euredomain.de`) wird
vom Webadmin als CNAME auf `<tunnel-id>.cfargotunnel.com` eingerichtet. Kein
A-Record, keine Port-Weiterleitung. Separates Deliverable: Anleitung für
Webadmin (Abschnitt 11).

### 2.2 Blueprint-Isolation

**Neuer Blueprint `api_bp`, strikt getrennt vom `main_bp`.**

Dies ist eine bewusste Ausnahme von der CLAUDE.md-Regel „Single `main_bp`
Blueprint". Begründung:

- Eigene Decorator-Kette (`@api_key_required` statt `@worker_required`)
- Kein Session-Cookie, kein CSRF — stateless
- JSON-only Error-Handler (`main_bp` hat HTML/JSON-Content-Negotiation)
- Separate Logger-Kategorie (`logging.getLogger('api')`)

Die bestehenden fokussierten Services (`TicketCoreService` etc.) werden
ohne Änderung wiederverwendet. Kein Fassaden-Pattern, keine Duplizierung
(CLAUDE.md-Regel #11 bleibt gewahrt).

### 2.3 Routen-Layout

```
/api/v1/
├── POST  /webhook/calls           ← HalloPetra-Webhook (Phase a, write:tickets)
├── GET   /health                  ← Liveness, ohne Auth
├── GET   /tickets/{id}            ← Phase b (read:tickets)
└── POST  /tickets/{id}/comments   ← Phase c (write:tickets)
```

`/health` liefert ausschließlich `{"status":"ok"}`, keine Versionsinfo, kein
DB-Call — für Cloudflare Tunnel Health-Checks.

### 2.4 Dateistruktur

```
routes/
├── api/                           ← neu
│   ├── __init__.py                ← api_bp Definition, register_routes(app)
│   ├── _decorators.py             ← @api_key_required, @require_scope,
│   │                                @api_rate_limit, @api_endpoint
│   ├── _errors.py                 ← JSON-Error-Handler
│   ├── webhook_routes.py          ← /webhook/calls
│   ├── ticket_routes.py           ← Phase b/c
│   └── health_routes.py           ← /health
services/
└── api_key_service.py             ← neu: Erzeugung, Rotation, Revocation,
                                     Lookup, IP-Check, Audit-Logging
```

## 3. Datenmodell

Vier neue Tabellen und drei Spalten-Erweiterungen auf bestehenden Tabellen.
Alle Änderungen via Alembic-Migration mit Daten-Migration wo nötig
(CLAUDE.md-Regel #7).

### 3.1 `api_key`

| Spalte | Typ | Zweck |
|---|---|---|
| `id` | Integer PK | |
| `name` | String(120), NOT NULL | Menschenlesbar: „HalloPetra Produktion" |
| `key_prefix` | String(12), NOT NULL, indexed | Erste 12 Zeichen (`tsk_xxxxxxxx`), unverschlüsselt |
| `key_hash` | String(128), NOT NULL, unique | HMAC-SHA256-Keyed-Hash des vollen Tokens (server-seitiger `API_KEY_PEPPER`) |
| `scopes` | String(255), NOT NULL | Komma-separiert: `write:tickets`, `read:tickets`, `admin:tickets` |
| `is_active` | Boolean, NOT NULL, default True | Schnell-Deaktivierung |
| `rate_limit_per_minute` | Integer, NOT NULL, default 60 | Konfigurierbar ab Phase a |
| `expected_webhook_id` | String(128), nullable | Optional; zusätzlicher Filter |
| `default_assignee_worker_id` | FK → worker, nullable | Pflicht wenn `write:tickets` Scope |
| `create_confidential_tickets` | Boolean, NOT NULL, default True | Automatische Confidential-Markierung |
| `created_at` | DateTime, NOT NULL | |
| `created_by_worker_id` | FK → worker, NOT NULL | |
| `last_used_at` | DateTime, nullable | Update nur alle 60 s (Write-Load-Reduktion) |
| `last_used_ip` | String(45), nullable | |
| `revoked_at` | DateTime, nullable | Soft-Delete |
| `revoked_by_worker_id` | FK → worker, nullable | |
| `expires_at` | DateTime, nullable | Optional für rotierbare Keys |

**Token-Format:** `tsk_` + 48 Zeichen base62. Der Klartext wird **nur einmalig
bei Erstellung angezeigt** (GitHub/Stripe-Pattern). Danach lebt ausschließlich
der Hash in der DB. Der `tsk_`-Prefix ermöglicht Leak-Detection durch
Scanner (z. B. GitHub Secret Scanning).

### 3.2 `api_key_ip_range`

| Spalte | Typ | Zweck |
|---|---|---|
| `id` | Integer PK | |
| `api_key_id` | FK → api_key, NOT NULL, ondelete='CASCADE' | |
| `cidr` | String(43), NOT NULL | IPv4 oder IPv6 CIDR |
| `note` | String(255), nullable | z. B. „Beob. 2026-04-20 Staging-Test" |
| `created_at` | DateTime, NOT NULL | |
| `created_by_worker_id` | FK → worker, NOT NULL | |

**Semantik:** Leere Allowlist für einen Key = kein IP-Check (nur Token). Sobald
mindestens ein Eintrag existiert, wird strikt geprüft. Damit kann der Webhook
ohne IP-Check live gehen, Quell-IPs beobachtet und dann nachgezogen werden.

### 3.3 `api_audit_log`

| Spalte | Typ | Zweck |
|---|---|---|
| `id` | Integer PK | |
| `timestamp` | DateTime, NOT NULL, indexed | |
| `api_key_id` | FK → api_key, nullable | Null bei Auth-Fehlern vor Key-Lookup |
| `key_prefix` | String(12), nullable | Auch bei ungültigem Key für Forensik |
| `source_ip` | String(45), NOT NULL | IPv4/IPv6 |
| `method` | String(8), NOT NULL | |
| `path` | String(255), NOT NULL | |
| `status_code` | Integer, NOT NULL | |
| `latency_ms` | Integer, NOT NULL | |
| `outcome` | String(32), NOT NULL | siehe Enum unten |
| `external_ref` | String(64), nullable, indexed | `data.id` aus Payload |
| `assignment_method` | String(24), nullable | `email_match`, `default`, `ambiguous_fallback`, `inactive_worker_fallback` |
| `request_id` | String(36), NOT NULL | UUID, auch in 500-Responses zurückgegeben |
| `error_detail` | Text, nullable | Gekürzt, **keine Payload-Dumps mit PII** |

**`outcome`-Werte:** `success`, `auth_failed`, `ip_blocked`, `rate_limited`,
`validation_failed`, `idempotent_replay`, `scope_denied`, `payload_too_large`,
`unsupported_media_type`, `server_error`

**Retention:** 90 Tage via Scheduled Job. Bewusst kürzer als Ticket-Daten,
weil Audit-Logs selbst PII enthalten (Quell-IPs + Zuweisungs-Metadaten).

### 3.4 `ticket_transcript`

| Spalte | Typ | Zweck |
|---|---|---|
| `id` | Integer PK | |
| `ticket_id` | FK → ticket, NOT NULL, ondelete='CASCADE', indexed | |
| `position` | Integer, NOT NULL | Sortier-Index (0, 1, 2, ...) |
| `role` | String(16), NOT NULL | `assistant` oder `user` |
| `content` | Text, NOT NULL | |
| `created_at` | DateTime, NOT NULL | |

**Retention:** 90 Tage via Scheduled Job, unabhängig vom Ticket. Ticket
bleibt bestehen mit `summary`, nur das wörtliche Transkript wird nach 90
Tagen gelöscht. DSGVO-motiviert (Abschnitt 8).

**Cascade-Delete:** Wenn Ticket gelöscht wird, werden alle Transkript-Einträge
sofort mit gelöscht (nicht erst via Retention-Job).

### 3.5 Erweiterungen an `ticket`

| Spalte (neu) | Typ | Zweck |
|---|---|---|
| `external_call_id` | String(64), nullable, unique, indexed | Idempotenz-Schlüssel aus `data.id` |
| `external_metadata` | Text (JSON-serialisiert), nullable | Anbieter-spezifische Payload-Reste |

**Kein** neues `ticket.source`-Feld. Die Unterscheidung „API vs. UI" ist via
`external_call_id IS NOT NULL` ableitbar. YAGNI.

`contact.channel` bleibt unverändert bestehen; API-erzeugte Tickets setzen
es fest auf `"Telefon (KI-Agent)"`.

### 3.6 Index-Strategie

- `api_key.key_prefix` — indexed, O(log n) Lookup bei Auth
- `api_key.key_hash` — unique
- `api_audit_log.timestamp` — indexed, für Retention-Job und Log-Viewer
- `api_audit_log.external_ref` — indexed, für Idempotenz-Lookups und Forensik
- `ticket.external_call_id` — unique + indexed, Idempotenz-Check
- `ticket_transcript.ticket_id` — indexed, 1-to-many-Auflösung

## 4. Payload-Verarbeitung

### 4.1 Pydantic-Schema

```python
class HalloPetraMessage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['assistant', 'user']
    content: str = Field(max_length=10_000)

class HalloPetraContactData(BaseModel):
    model_config = ConfigDict(extra='ignore')  # toleriert Anbieter-Erweiterungen
    id: str | None = None
    name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=500)

class HalloPetraCallData(BaseModel):
    model_config = ConfigDict(extra='ignore')
    id: str = Field(min_length=1, max_length=64)
    duration: int = Field(ge=0, le=86400)
    phone: str | None = None
    topic: str | None = Field(default=None, max_length=255)
    summary: str | None = Field(default=None, max_length=5_000)
    messages: list[HalloPetraMessage] = Field(default_factory=list, max_length=500)
    collected_data: dict[str, Any] = Field(default_factory=dict)
    contact_data: HalloPetraContactData | None = None
    main_task_id: str | None = None
    email_send_to: str | None = Field(default=None, max_length=255)
    forwarded_to: str | None = None
    previous_webhook_calls: list[Any] = Field(default_factory=list)

class HalloPetraWebhookPayload(BaseModel):
    model_config = ConfigDict(extra='ignore')
    webhook_id: str
    data: HalloPetraCallData
```

**Unterschiedliche `extra`-Policies:** `forbid` für unsere innersten
Validierungen (`HalloPetraMessage`), `ignore` für Anbieter-Ebenen (damit
zukünftige HalloPetra-Felderweiterungen unsere API nicht brechen).

**Content-Länge:** `MAX_CONTENT_LENGTH = 128 KB` auf App-Ebene für
`/api/v1/*`-Routen. Strict Content-Type: `application/json` Pflicht, sonst 415.

### 4.2 Ticket-Mapping

Bei Konflikten gilt Priorität: `contact_data.*` > `collected_data.*` > `data.*`.

| HalloPetra-Feld | Ticket-Feld |
|---|---|
| `data.id` | `ticket.external_call_id` (unique) |
| `data.topic` ∥ `data.summary[:80]` | `ticket.title` |
| `data.summary` + formatierte `messages` | `ticket.description` (Markdown) |
| `contact_data.name` ∥ `collected_data.contact_name` | `ticket.contact.name` |
| `contact_data.phone` ∥ `collected_data.contact_phone` ∥ `data.phone` | `ticket.contact.phone` |
| `contact_data.email` ∥ `collected_data.contact_email` | `ticket.contact.email` |
| Konstante `"Telefon (KI-Agent)"` | `ticket.contact.channel` |
| `data.messages[]` | `ticket_transcript` (separate Tabelle, Confidential) |
| `data.email_send_to` → Worker-Match oder Default | `ticket.assignee_id` |
| alles übrige (`address`, `duration`, `main_task_id`, `collected_data`, `forwarded_to`, `contact_data.id`, `previous_webhook_calls`) | `ticket.external_metadata` (JSON) |

**Adresse bewusst in `external_metadata`:** Kein neues Feld auf `ticket_contact`.
Adress-Handling ist noch nicht Teil der Ticket-Domäne; wenn es fachlich gebraucht
wird, wird das eine saubere separate Erweiterung, nicht ein Nebeneffekt der
API-Integration (CLAUDE.md-Regel #2).

**`ticket.ensure_contact()`** wird für alle Kontakt-Schreiboperationen genutzt
(CLAUDE.md-Regel #3).

### 4.3 Zuweisungs-Logik

Zweistufig, in dieser Reihenfolge:

```
1. Wenn data.email_send_to gesetzt UND worker.email matcht (lower-cased exact):
   1a. Genau ein aktiver Match → assignee = dieser Worker
       assignment_method = 'email_match'
   1b. Mehrere Matches (sollte nicht vorkommen) → Fallback
       assignment_method = 'ambiguous_fallback'
   1c. Match auf inaktiven Worker → Fallback
       assignment_method = 'inactive_worker_fallback'
2. Fallback: assignee = api_key.default_assignee_worker_id
   assignment_method = 'default'
```

Die Entscheidung landet im `api_audit_log.assignment_method`. Kein Fuzzy-Matching,
keine Domain-Heuristik.

**`default_assignee_worker_id`** ist bei Keys mit `write:tickets`-Scope
Pflichtfeld — erzwungen in der Admin-UI und durch Form-Validierung.

### 4.4 Idempotenz-Flow

```
1. Auth + Schema-Validation ok
2. SELECT ticket WHERE external_call_id = data.id
   ├─ Treffer: 200 OK, return {"ticket_id": <id>, "status": "duplicate"}
   │          outcome = 'idempotent_replay'
   │          KEINE weitere Mutation
   └─ Kein Treffer: Ticket anlegen (Transaction)
       201 Created, return {"ticket_id": <id>, "status": "created"}
```

Expliziter SELECT vor INSERT (nicht `try/except IntegrityError`), weil wir
die bestehende `ticket_id` zurückgeben wollen. Unique-Constraint auf
`ticket.external_call_id` bleibt als Race-Schutz.

### 4.5 Synchrone Verarbeitung

**Entscheidung gegen 202 Accepted + Background-Job.** Ticket-INSERT mit
Satelliten-Tabellen läuft < 50 ms auf SQLite; HalloPetra-Timeouts von 10 s
(während/nach Anruf) sind großzügig. Background-Komplexität würde ohne
Mehrwert Fehlerquellen einführen (YAGNI).

NGINX-Timeout für `/api/v1/*` auf 8 s: lieber 504 an Cloudflare als
HalloPetra-Timeout, weil Retries mit Idempotenz sauber abfangbar sind.

### 4.6 Response-Codes

| Status | Wann | Body |
|---|---|---|
| 200 | Idempotent Replay | `{"ticket_id":123,"status":"duplicate"}` |
| 201 | Neu erzeugt | `{"ticket_id":124,"status":"created"}` |
| 400 | Schema-Fehler | `{"error":"validation_failed","request_id":"<uuid>"}` (Detail nur im Audit-Log, via `request_id` korrelierbar — kein Leak von Exception-Text nach außen) |
| 401 | Auth-Fehler (alle Varianten) | `{"error":"unauthorized"}` |
| 403 | Scope/IP-Fehler | `{"error":"forbidden"}` |
| 413 | Payload > 128 KB | `{"error":"payload_too_large"}` |
| 415 | Kein JSON | `{"error":"unsupported_media_type"}` |
| 429 | Rate-Limit | `{"error":"rate_limited","retry_after":30}` |
| 500 | Serverfehler | `{"error":"internal_error","request_id":"<uuid>"}` |

Die `request_id` wird pro Request generiert und auch im `api_audit_log`
gespeichert — für Incident-Mapping vom Fehler-Report zurück zum DB-Eintrag.

## 5. Auth-Pipeline

### 5.1 Decorator-Kette

```python
@api_bp.route('/webhook/calls', methods=['POST'])
@api_key_required                      # 1. Token prüfen, IP prüfen
@require_scope('write:tickets')        # 2. Scope-Check
@api_rate_limit                        # 3. Pro-Key Rate-Limit (dynamisch)
@api_endpoint                          # 4. JSON-Error-Handling
def _webhook_calls(api_key):
    ...
```

**Reihenfolge-Grund:** Unauthentifizierte Requests werden so früh wie möglich
abgelehnt. Rate-Limit läuft erst *nach* Auth, damit es nicht selbst zum
DoS-Vektor wird.

### 5.2 `@api_key_required` im Detail

1. **Header extrahieren:** `Authorization: Bearer tsk_<...>` (RFC 6750).
   Alternative Headers werden nicht akzeptiert.
2. **Format-Check:** Präfix `tsk_`, exakte Länge, base62-Zeichen. Ungültiges
   Format → 401 ohne DB-Lookup (verhindert Format-Enumeration).
3. **Prefix extrahieren:** Erste 12 Zeichen für indexed Lookup.
4. **Hash vergleichen:** `hmac.compare_digest(sha256(token), stored_hash)` —
   timing-safe.
5. **Status prüfen:** `is_active=True`, `revoked_at IS NULL`,
   `expires_at IS NULL OR expires_at > now()`.
6. **IP-Check:** Quell-IP aus `CF-Connecting-IP` → `X-Real-IP` → `remote_addr`.
   Wenn Allowlist für Key nicht leer: CIDR-Match via `ipaddress.ip_address in
   ipaddress.ip_network`. Kein Match → 403.
7. **`last_used_at`/`last_used_ip` aktualisieren** — nur wenn letzte Aktualisierung
   > 60 s zurückliegt.
8. **Key-Objekt in `g.api_key` ablegen.**
9. **Audit-Log-Eintrag vormerken** (wird nach Response-Abschluss geschrieben
   via `@app.after_request` im api_bp).

**Alle Auth-Fehler in Schritten 1–6 antworten mit generischem 401
`{"error":"unauthorized"}`** (gleicher Body, keine Enumeration). Der echte
Grund landet nur im Audit-Log (`outcome`).

**Ausnahme:** IP-Block loggt als `outcome='ip_blocked'`, weil das operativ
wichtig ist.

### 5.3 Rate-Limit

- Werkzeug: bestehendes `flask-limiter`
- `key_func = lambda: g.api_key.id` — limitiert *nach* Auth, pro Key
- Limit aus `g.api_key.rate_limit_per_minute` (konfigurierbar in Admin-UI)
- Storage: In-Memory (ausreichend für Single-Worker-Deployment)

### 5.4 Session-Isolation

`api_bp.before_request`:

```python
session.clear()           # Falls NGINX doch ein Cookie durchrutscht
g.pop('current_worker', None)
```

Damit kann kein UI-Auth-Mechanismus versehentlich greifen.

## 6. Admin-UI

### 6.1 Menü-Struktur

```
Administration
├── (bestehende Einträge)
└── API-Zugriff                           ← neu
    ├── API-Schlüssel                     ← Liste + Erstellen + Edit
    ├── Zugriffs-Log                      ← Audit-Log-Viewer
    └── Dokumentation                     ← Statische Markdown-Seite
```

Alle `/admin/api-keys/*`-Routen erfordern Admin-Berechtigung aus dem
bestehenden Worker-Modell (konkrete Flag/Rolle wird beim Implementieren
gegen den Bestand geprüft; vermutlich `is_admin`).

### 6.2 Schlüsselverwaltung — Liste

Spalten: Name, Prefix, Scopes, Zuletzt genutzt, Status (aktiv/widerrufen).
Klick auf Zeile → Detail/Edit.

### 6.3 Schlüsselverwaltung — Erstellen

Form-Felder:
- Name (Pflicht)
- Scopes (Checkboxen; Phase a zeigt nur `write:tickets`, andere sind
  visuell vorbereitet und gräulich markiert)
- Standard-Zuweisung (Select, Pflicht bei `write:tickets`)
- Rate-Limit / Minute (Integer, Default 60)
- Erwartete `webhook_id` (optional)
- Confidential-Tickets-Flag (Checkbox, Default an)
- Ablaufdatum (optional)

Nach Erstellung: Einmalige Klartext-Anzeige mit Copy-Button, Warnhinweis,
und Bestätigungs-Button „Ich habe den Schlüssel sicher hinterlegt". Route
zeigt Token nur **dieses eine Mal** — Reload der Seite zeigt ihn nicht mehr.

### 6.4 Schlüsselverwaltung — Bearbeiten

Alles editierbar außer Token und Prefix. Zusätzliche Sektionen:
- **IP-Allowlist:** Tabelle mit CIDR-Einträgen, Add/Remove
- **Zuletzt beobachtete Quell-IPs:** Modal mit den letzten 10 unique IPs aus
  `api_audit_log` für diesen Key. Pro IP: Anzahl Requests, letzte Nutzung,
  Button „Als /32 hinzufügen" und Button „Als /24 hinzufügen". Zusätzlich
  Sammel-Button „Alle als /24 hinzufügen".
- **Letzte Nutzung:** `last_used_at`, `last_used_ip`, 24h-Request-Zähler

Buttons unten: **Widerrufen** (rot, mit Bestätigungsdialog), **Speichern**.

**Widerruf-Nebeneffekt:** Eintrag im bestehenden Worker-Audit-Log
(welcher Admin wann welchen Key widerrufen hat).

### 6.5 Audit-Log-Viewer

Tabelle mit Filtern (Key, Outcome, Zeitraum). Pagination. Klick auf Zeile →
Detail-Panel mit `error_detail`, `latency_ms`, `external_ref`,
`assignment_method`. Kein Payload-Inhalt (PII-Vermeidung).

### 6.6 Dokumentations-Seite

Statische Markdown-Seite, im App-Bundle (nicht extern), mit:
- Endpoint-URL (dynamisch mit konfigurierter Subdomain)
- Auth-Header-Format
- JSON-Payload-Schema
- Response-Codes
- Rate-Limit-Verhalten
- Idempotenz-Garantien
- Token-Format und Einmal-Anzeige-Hinweis
- Retention-Policies (Audit-Log 90 Tage, Transkript 90 Tage)
- IP-Allowlist-Verhalten
- Separater Abschnitt: **Anleitung für Webadmin** (DNS-Setup), damit der Link
  nur an den Webadmin geschickt werden kann

## 7. Pre-Launch-Härtung

Das gesamte bestehende System wurde mit LAN-only-Annahmen gebaut. Vor der
Tunnel-Aktivierung müssen die folgenden Punkte systematisch adressiert werden.

### 7.1 NGINX-Konfiguration

Kritische Regel: **Nur `/api/v1/*` ist über den Cloudflare Tunnel erreichbar.**
Durchgesetzt auf zwei Ebenen (Defense-in-Depth):

1. Cloudflare Tunnel Ingress-Regel: explizites Pfad-Match
2. NGINX: separater server-Block oder deny-Regeln für alle anderen Pfade

**Curl-Test-Matrix (Teil der Pre-Launch-Checkliste):**

| URL | Erwartete Antwort |
|---|---|
| `https://ticket-api.euredomain.de/api/v1/health` | 200 |
| `https://ticket-api.euredomain.de/api/v1/webhook/calls` (ohne Token) | 401 |
| `https://ticket-api.euredomain.de/login` | 403 oder 404 |
| `https://ticket-api.euredomain.de/` | 403 oder 404 |
| `https://ticket-api.euredomain.de/admin/api-keys/` | 403 oder 404 |

### 7.2 Audit bestehender Endpunkte

```bash
grep -rn '@main_bp.route' routes/ | grep -v 'methods='
grep -rLn 'worker_required' routes/*.py
grep -rn 'TODO\|FIXME\|XXX\|HACK' routes/ services/ *.py
```

Jeder Endpunkt ohne `@worker_required` muss explizit gerechtfertigt werden
(bisherige bekannte Ausnahme: `_new_ticket_view` für anonyme Ticket-Erstellung).

### 7.3 Flask-Konfiguration

| Einstellung | Soll |
|---|---|
| `DEBUG` | **False** |
| `PROPAGATE_EXCEPTIONS` | False |
| `SESSION_COOKIE_SECURE` | True |
| `SESSION_COOKIE_HTTPONLY` | True |
| `SESSION_COOKIE_SAMESITE` | `'Lax'` |
| `SECRET_KEY` | Rotiert auf 64-byte random, aus HA-Secrets |
| `MAX_CONTENT_LENGTH` (global) | explizit gesetzt |
| `Server`-Header | via NGINX überschreiben |

**SECRET_KEY-Rotation als eigenständiger Vor-Schritt** (nicht Teil des
Launch-Fensters). Alle 4 aktiven Worker werden ausgeloggt und müssen sich
neu anmelden.

### 7.4 Security-Header in NGINX

```
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header Referrer-Policy "same-origin" always;
add_header Content-Security-Policy "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'" always;
```

CSP-Tests: bestehende Templates durchklicken, Inline-Scripts identifizieren.
Wenn etwas bricht: Templates fixen, **nicht** CSP aufweichen.

### 7.5 SQLite-Backup

- Täglicher Cron mit `sqlite3 .backup`
- Retention: 14 Tage
- Ablage im HA-persistenten Volume, außerhalb des App-Pfades

### 7.6 Secrets-Management

- `.env` nicht in Git (verifizieren via `git ls-files | grep -i env`)
- Flask `SECRET_KEY` → HA-Secret
- SMTP-Credentials → HA-Secret
- `cloudflared` Tunnel-Token → HA-Secret
- Grep nach Hardcoded Secrets:
  `grep -rn 'password\|secret\|api_key' --include='*.py' .`

### 7.7 Dependency-Audit

Einmal vor Launch: `pip list --outdated`, `pip-audit` oder `safety check`.
Hohe CVEs patchen. Wiederholung als regulärer Wartungsprozess (nicht Teil
dieses Specs).

## 8. DSGVO und Transkript-Handling

### 8.1 Datenklassen im Payload

| Feld | DSGVO-Relevanz |
|---|---|
| `phone` | personenbezogen |
| `contact_data.*` | personenbezogen |
| `summary` | kann personenbezogen sein |
| `messages[].content` | **wörtliches Gesprächstranskript**, hoher Schutzbedarf |
| `collected_data.*` | anbieter-definiert, potenziell sensibel |
| `main_task_id`, `forwarded_to`, `external_call_id` | Metadaten, indirekt personenbezogen |

### 8.2 Speicher-Entscheidungen

- **Transkript** in separater Tabelle `ticket_transcript` mit 90-Tage-Retention
  (Abschnitt 3.4)
- **`create_confidential_tickets`** default True für HalloPetra-Key →
  alle API-erzeugten Tickets automatisch vertraulich
- **Cascade-Delete** bei Ticket-Löschung entfernt Transkripte sofort

### 8.3 Hinweise in API-Doku

- Hinweis auf bestehenden AV-Vertrag mit HalloPetra (Betreiber-Pflicht,
  kein Code-Thema)
- Retention-Policy dokumentiert (Audit-Log 90 Tage, Transkript 90 Tage)

### 8.4 Folgeanforderungen (nicht Umfang)

- Auskunfts-/Löschsuche über UI (Art. 15/17 DSGVO)
- Formale Datenschutz-Folgenabschätzung (DSFA)

Explizit als offene Folgeanforderungen vermerkt; werden in separatem Spec
behandelt, wenn relevant.

## 9. Testing und Rollout

### 9.1 Pytest-Suite

Baseline aus CLAUDE.md: 7 passed, 8 known failures. Neue Tests **zusätzlich**
grün, keine existierenden brechen.

Neue Test-Dateien:
- `tests/test_api_auth.py`
- `tests/test_api_webhook.py`
- `tests/test_api_idempotency.py`
- `tests/test_api_rate_limit.py`
- `tests/test_api_ip_allowlist.py`
- `tests/test_api_audit_log.py`
- `tests/test_api_key_service.py`
- `tests/test_admin_api_keys_ui.py`

**19 kritische Tests** (müssen vor Launch grün sein):

| # | Test | Assertion |
|---|---|---|
| 1 | `test_unauthorized_returns_401_generic` | Falsches Token, fehlendes Token, falsches Format → alle 401 mit identischem Body |
| 2 | `test_timing_attack_resistance` | Token-Vergleich timing-stabil (statistischer Test via `time.perf_counter`) |
| 3 | `test_idempotency_returns_same_ticket` | Zweiter Call mit gleichem `data.id` → 200, gleiche `ticket_id`, kein zweites Ticket |
| 4 | `test_idempotency_concurrent_requests` | Parallel-Requests → genau ein Ticket, Unique-Constraint fängt Race |
| 5 | `test_ip_allowlist_enforced` | Fremde IP → 403, `outcome='ip_blocked'` |
| 6 | `test_empty_allowlist_allows_all` | Leere Allowlist → alle IPs okay |
| 7 | `test_payload_too_large` | > 128 KB → 413 |
| 8 | `test_malformed_json` | Invalides JSON → 400 validation_failed |
| 9 | `test_schema_rejects_unknown_fields` | Extra-Felder auf Message-Ebene → 400 |
| 10 | `test_worker_match_via_email_send_to` | `email_send_to` matcht Worker-Email → assignee = dieser Worker |
| 11 | `test_worker_fallback_to_default` | Kein Match → `default_assignee_worker_id` |
| 12 | `test_inactive_worker_fallback` | Match auf inaktiven Worker → Fallback, korrekter `assignment_method` |
| 13 | `test_confidential_flag_applied` | `create_confidential_tickets=True` → Ticket confidential |
| 14 | `test_revoked_key_rejected` | Widerrufener Key → 401 |
| 15 | `test_scope_mismatch` | Valider Key ohne `write:tickets` → 403 |
| 16 | `test_audit_log_retention_job` | Einträge > 90 Tage gelöscht, neuere bleiben |
| 17 | `test_transcript_retention_job` | Transkripte > 90 Tage gelöscht, Ticket bleibt |
| 18 | `test_admin_ui_requires_admin` | Nicht-Admin → 403 auf `/admin/api-keys/*` |
| 19 | `test_token_shown_once_only` | Edit-View zeigt niemals Klartext-Token |

### 9.2 Manueller Full-Stack-Smoke-Test

Vor Staging: lokale Instanz, Key anlegen, curl-Durchlauf, UI-Prüfung,
Audit-Log-Check, IP-Allowlist-Aktivierung.

### 9.3 Staging-Phase: 2 Wochen

- Dedizierte Subdomain `ticket-api-staging.euredomain.de`, separater Tunnel,
  **separate Flask-Instanz mit eigener SQLite-DB-Datei** (vollständige
  Isolation von Prod-Daten), eigener API-Key „HalloPetra Staging"
- HalloPetra-Testnummer auf Staging-URL konfigurieren
- IP-Allowlist bewusst leer → Quell-IPs beobachten
- Mindestens 5 Testanrufe mit verschiedenen Szenarien (einfach,
  Weiterleitung, Abbruch, verzögerte Antwort > 10 s zur Retry-Simulation)
- Nach jedem Anruf: Audit-Log + Ticket-UI prüfen

### 9.4 Rollout-Reihenfolge

```
Schritt 1 (Vor-Schritt, eigenständig)
├── SECRET_KEY rotieren
├── SQLite-Backup-Cron
├── Dependency-Audit + Updates
└── Verifikation: App läuft, Worker loggen sich neu ein

Schritt 2 (Migration + Code, LAN-only)
├── Alembic-Migrationen (api_key, api_key_ip_range, api_audit_log,
│   ticket_transcript, ticket.external_call_id, ticket.external_metadata)
├── api_bp deployed (Tunnel NOCH NICHT aktiv)
├── Admin-UI deployed
└── Verifikation: pytest grün, UI bedienbar, API im LAN testbar

Schritt 3 (Infrastruktur, noch ohne Nutzung)
├── Cloudflare Tunnel einrichten
├── Subdomain via Webadmin
├── NGINX-Härtung + Security-Header
├── Pre-Launch-Checkliste abgearbeitet
└── Verifikation: curl-Test-Matrix grün

Schritt 4 (Staging-Phase, 2 Wochen)
├── Staging-Key + Staging-Subdomain + Staging-Tunnel
├── HalloPetra auf Staging-URL konfigurieren
├── Testanrufe
└── Verifikation: alle Szenarien erzeugen korrekte Tickets

Schritt 5 (Produktions-Launch)
├── Produktions-Key anlegen, Klartext sicher hinterlegen
├── HalloPetra von Staging- auf Prod-URL umstellen
├── 1–2 Tage intensiv monitoren
└── Verifikation: echte Anrufe landen korrekt

Schritt 6 (Allowlist-Aktivierung, 2–5 Tage nach Launch)
├── Beobachtete Prod-IPs aus Admin-UI übernehmen
├── Bestätigen: Requests kommen weiterhin durch
└── Ab jetzt: Allowlist aktiv
```

### 9.5 Monitoring nach Launch

- **2 Wochen tägliche Routine:** Admin → Audit-Log → Filter `outcome !=
  'success'` → Sichtprüfung
- **Manueller Alert-Trigger:** > 10 `auth_failed` pro Stunde → potenzieller Angriff
- **Wöchentlich:** SQLite-DB-Größe prüfen

### 9.6 Rollback-Plan

1. **Schnell:** Cloudflare Tunnel deaktivieren → API offline, App LAN-only
2. **Mittel:** Produktions-Key widerrufen → HalloPetra bekommt 401, App läuft
3. **Notfall:** DB-Backup einspielen

Code-Rollback: Alembic-Downgrade in Schritt 2 (vor produktiven Daten) machbar.
Daher strikte Trennung „Migrationen in LAN-only-Phase" bevor der Tunnel aktiv ist.

## 10. Betriebshandbuch (Deliverable)

Eigenständiges Markdown-Dokument `docs/operations/public-api-handbook.md` mit:

- **Testing:** Pytest-Ausführung, Baseline-Check, Smoke-Test-Protokoll
- **Staging:** Einrichtung, Testszenarien, IP-Beobachtung, Übergang zu Prod
- **Rollout:** Die 6 Schritte aus 9.4 als Checkliste
- **Monitoring:** Tägliche/wöchentliche Routinen, Alert-Trigger, KPIs
- **Rollback:** 3-stufiger Plan mit konkreten Kommandos
- **Incident-Response:** Was tun bei `auth_failed`-Flood, bei Key-Leak, bei
  HalloPetra-Timeout-Beschwerden

Zielgruppe: Betreiber (du), Webadmin (für DNS), später ggf. weitere Admins.

## 11. Deliverables (Zusammenfassung)

1. **Code-Änderungen:** neuer `api_bp`, neue Modelle, neue Services, Admin-UI
2. **Datenbank-Migration:** Alembic-Migration mit Daten-Migration
3. **Tests:** 19 kritische + ergänzende Tests
4. **API-Dokumentation** (statisch, im App-Bundle)
5. **Webadmin-Anleitung** (DNS-CNAME-Setup) — im API-Doku als separater
   Abschnitt
6. **Pre-Launch-Checkliste** (`docs/operations/api-prelaunch-checklist.md`)
7. **Betriebshandbuch** (`docs/operations/public-api-handbook.md`)
8. **NGINX-Konfigurations-Snippets** für das HA-Add-on

## 12. Out-of-Scope

Explizit nicht Teil dieses Specs:

- Phase b (Lese-API) und Phase c (Workflow-API) — werden als separate
  Iterationen geplant, Datenmodell ist vorbereitet
- Swagger/OpenAPI-Dokumentation — statisches Markdown reicht für einen
  Konsumenten
- WAF-Regeln in Cloudflare (jenseits Default Bot-Fight-Mode)
- DSFA und Auskunftssuche in der UI — separate Folgeanforderung
- Multi-Worker-Deployment der Flask-App (würde Redis-Rate-Limit-Storage
  bedingen)
- Automatisierte Alerts (Prometheus/Slack) — manuelle Monitoring-Routine
  reicht für Start
- Token-Rotation-Feature — „neu erstellen + alt widerrufen" deckt den
  Use-Case in Phase a ab

## 13. Architekturelle Abweichungen von CLAUDE.md

Bewusste Ausnahmen von bestehenden Projektregeln, alle begründet:

| Regel | Abweichung | Begründung |
|---|---|---|
| Single `main_bp` Blueprint | Eigener `api_bp` | Grundlegend andere Auth-Semantik, Session-Isolation, JSON-only Error-Handler |
| „German-language UI text" | API-Fehler-Responses in Englisch | API ist Machine-to-Machine, Englisch ist Konvention (`"error":"unauthorized"`) |

Alle anderen CLAUDE.md-Regeln (Accessor-Pattern, Decorator-Stack für APIs,
Domain-Exceptions, zentrale Helpers) werden unverändert angewendet.
