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
