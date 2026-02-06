ARG BUILD_FROM=ghcr.io/hassio-addons/base:stable
FROM $BUILD_FROM

# Python und Pip installieren
RUN \
    apk add --no-cache \
    python3 \
    py3-pip

# Arbeitsverzeichnis setzen
WORKDIR /app

# Requirements kopieren und installieren
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages

# Den gesamten Code (inklusive run.sh) ins Arbeitsverzeichnis kopieren
COPY . .

# --- WICHTIGE ÄNDERUNG ---
# 1. Das run.sh Skript ausführbar machen (es liegt jetzt unter /app/run.sh)
RUN chmod a+x /app/run.sh

# 2. Den Startbefehl ändern, damit das Skript ausgeführt wird
CMD [ "/app/run.sh" ]
# -------------------------

# Datenbank-Pfad setzen
ENV DB_PATH=/data/werkzeug.db
