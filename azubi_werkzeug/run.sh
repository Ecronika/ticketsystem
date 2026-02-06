#!/usr/bin/with-contenv bashio

# Wechselt sicherheitshalber ins Arbeitsverzeichnis
cd /app

# Info-Log
echo "Starte Azubi Werkzeug Tracker..."

# Startet Gunicorn
# 'exec' sorgt dafür, dass Gunicorn die PID des Skripts übernimmt
exec gunicorn --workers 3 --bind 0.0.0.0:5000 app:app
