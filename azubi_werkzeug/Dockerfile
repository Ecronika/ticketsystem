ARG BUILD_FROM=ghcr.io/hassio-addons/base:stable
FROM $BUILD_FROM

# Python, Pip UND dos2unix installieren
# dos2unix ist wichtig, um Windows-Zeilenumbrüche zu reparieren
RUN \
    apk add --no-cache \
    python3 \
    py3-pip \
    dos2unix

# Arbeitsverzeichnis setzen
WORKDIR /app

# Requirements kopieren und installieren
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages

# Den gesamten Code ins Arbeitsverzeichnis kopieren
COPY . .

# --- FIX FÜR WINDOWS USER ---
# 1. Konvertiere run.sh ins Unix-Format (entfernt unsichtbare \r Zeichen)
RUN dos2unix /app/run.sh
# 2. Mache das Skript ausführbar
RUN chmod a+x /app/run.sh
# ----------------------------

# Den Startbefehl setzen
CMD [ "/app/run.sh" ]

# Datenbank-Pfad setzen
ENV DB_PATH=/data/werkzeug.db