# Azubi Werkzeug Tracker - Home Assistant Repository

Dieses Repository enthält Home Assistant Add-ons für den Azubi Werkzeug Tracker.

## Verfügbare Add-ons

- **Azubi Werkzeug Tracker**: Eine Anwendung zur Verwaltung und Prüfung von Werkzeugen.

## Installation

1. Kopieren Sie die URL dieses Repositories.
2. Öffnen Sie Home Assistant.
3. Gehen Sie zu **Einstellungen -> Add-ons -> Add-on Store**.
4. Klicken Sie auf die drei Punkte oben rechts und wählen Sie **Repositories**.
5. Fügen Sie die URL dieses Repositories hinzu.
6. Laden Sie die Seite neu (oder klicken Sie auf "Überprüfen auf Updates").
7. Installieren Sie das "Azubi Werkzeug Tracker" Add-on.

## Erste Schritte (Standalone Nutzung)

Wenn Sie das Projekt lokal oder als Standalone-Anwendung (ohne Home Assistant) betreiben:

1. **Abhängigkeiten installieren:** 
   ```bash
   pip install -r requirements.txt
   ```
2. **Datenbank initialisieren/aktualisieren:** 
   ```bash
   flask db upgrade
   ```
3. **Erster Login:** 
   - Rufen Sie die Anwendung im Browser auf (typischerweise `http://localhost:5000` oder `8099`).
   - Der initiale Admin-Login erfolgt über die **Standard-PIN: `0000`**.
   - Ändern Sie diese PIN umgehend nach dem ersten Login in den Einstellungen.
