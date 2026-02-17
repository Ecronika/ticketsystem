ARG BUILD_FROM
FROM $BUILD_FROM

# Python, Pip und notwendige Tools installieren
RUN \
    apk add --no-cache \
    python3 \
    py3-pip \
    curl

# Arbeitsverzeichnis setzen
WORKDIR /app

# Requirements kopieren und installieren
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages

# App-Code kopieren
COPY app.py .
COPY pdf_utils.py .
COPY extensions.py .
COPY models.py .
COPY routes/ routes/
COPY services.py .
COPY forms.py .
COPY templates templates/
COPY static static/

# Service-Skripte kopieren
COPY rootfs /

# Ausführungsrechte für Service-Skripte setzen
RUN chmod a+x /etc/services.d/azubi-werkzeug/run && \
    chmod a+x /etc/services.d/azubi-werkzeug/finish

# Datenbank-Pfad setzen
ENV DB_PATH=/data/werkzeug.db

# Healthcheck (Optimized for SD Card / Slow Start)
HEALTHCHECK --interval=30s --timeout=15s --start-period=30s --retries=5 \
    CMD curl -f http://localhost:5000/health || exit 1
