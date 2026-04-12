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
