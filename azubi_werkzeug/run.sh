#!/usr/bin/with-contenv bashio

echo "Starting Azubi Werkzeug Tracker..."

# data directory is provided by Home Assistant for persistent storage
export DB_PATH=/data/werkzeug.db

echo "Using database at $DB_PATH"

# Run Gunicorn
# exec to replace the shell process
exec gunicorn --workers 3 --bind 0.0.0.0:5000 app:app
