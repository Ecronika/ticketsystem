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

# Copy and make run script executable
COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
