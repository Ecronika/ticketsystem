#!/usr/bin/with-contenv bashio

# Wechselt sicherheitshalber ins Arbeitsverzeichnis
cd /app

# Info-Log
echo "Starte Azubi Werkzeug Tracker..."

# --- NEU: Datenbank initialisieren ---
# Führt die setup_database Funktion einmalig vor dem Serverstart aus
echo "Initialisiere Datenbank..."
python3 -c "from app import setup_database; setup_database()"

# Startet Gunicorn
# 'exec' sorgt dafür, dass Gunicorn die PID des Skripts übernimmt
exec gunicorn --workers 3 --bind 0.0.0.0:5000 app:app
