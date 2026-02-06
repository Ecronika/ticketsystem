ARG BUILD_FROM=ghcr.io/hassio-addons/base:stable
FROM $BUILD_FROM

# Install Python and Pip
RUN \
    apk add --no-cache \
    python3 \
    py3-pip

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install dependencies
# --break-system-packages is needed for newer Python versions in Alpine/Debian managed environments
RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages

# Copy application code
COPY . .

# Set persistent database path
ENV DB_PATH=/data/werkzeug.db

# Run Gunicorn directly
# 3 workers, binding to all interfaces on port 5000
CMD ["gunicorn", "--workers", "3", "--bind", "0.0.0.0:5000", "app:app"]
