#!/bin/sh

# Wechsel ins Arbeitsverzeichnis
cd /app

# Datenbank initialisieren
echo "Initialisiere Datenbank..."
python3 -c "from app import setup_database; setup_database()"

# Server starten
echo "Starte Azubi Werkzeug Tracker..."
exec gunicorn --workers 3 --bind 0.0.0.0:5000 app:app