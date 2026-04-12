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
