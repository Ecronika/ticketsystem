# NGINX-Konfiguration für Public REST API

In der HA-Add-on NGINX-Config folgende Änderungen vornehmen.

## Security-Header (global)

Diese Header gelten für alle Location-Blöcke. Sie sollten im `http`- oder
`server`-Kontext gesetzt werden, damit sie bei jeder Antwort mitgehen.

```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header Referrer-Policy "same-origin" always;
add_header Content-Security-Policy "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'" always;
server_tokens off;  # keine Version im Server-Header
```

## API-Location (Defense-in-Depth zusätzlich zu Cloudflare Ingress)

Der folgende Block begrenzt die Anfragegröße auf 128 KB und setzt einen engen
Timeout, um langsame oder bösartige Clients abzuwehren. `Cookie ""` verhindert,
dass Session-Cookies der internen Anwendung in die API-Antworten sickern.

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

In `cloudflared/config.yml` (siehe auch `ticketsystem/cloudflared/config.yml.example`):

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
