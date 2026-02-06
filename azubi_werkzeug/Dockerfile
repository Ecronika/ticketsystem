ARG BUILD_FROM=ghcr.io/hassio-addons/base:stable
FROM $BUILD_FROM

# Python, Pip und dos2unix installieren
RUN \
    apk add --no-cache \
    python3 \
    py3-pip \
    dos2unix \
    curl

# Arbeitsverzeichnis setzen
WORKDIR /app

# Requirements kopieren und installieren
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages

# Den gesamten Code ins Arbeitsverzeichnis kopieren
COPY . .

# S6-Service-Skripte kopieren und ausführbar machen
COPY rootfs /

# Windows-Zeilenumbrüche reparieren für Service-Skripte
RUN dos2unix /etc/services.d/azubi-werkzeug/run && \
    dos2unix /etc/services.d/azubi-werkzeug/finish && \
    chmod a+x /etc/services.d/azubi-werkzeug/run && \
    chmod a+x /etc/services.d/azubi-werkzeug/finish

# Datenbank-Pfad setzen
ENV DB_PATH=/data/werkzeug.db

# KEIN CMD! S6 übernimmt das Starten über /etc/services.d/

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1