from prometheus_client import Counter, Histogram, Gauge

# --- Prometheus Metrics Definitions ---

# Tracks total HTTP requests by method and endpoint
HTTP_REQUESTS_TOTAL = Counter(
    'werkzeug_http_requests_total',
    'Total number of HTTP requests',
    ['method', 'endpoint', 'http_status']
)

# Tracks latency of HTTP requests
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    'werkzeug_http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint']
)

# Custom Application Metrics
SCANS_TOTAL = Counter(
    'werkzeug_scans_total',
    'Total number of Azubi QR scans performed'
)

CHECKS_SUBMITTED_TOTAL = Counter(
    'werkzeug_checks_submitted_total',
    'Total number of tool checks/issues submitted',
    ['check_type'] # e.g., 'check', 'issue', 'return'
)

ACTIVE_SESSIONS = Gauge(
    'werkzeug_active_sessions',
    'Estimated number of active user sessions (logins)'
)

DB_OPERATION_DURATION_SECONDS = Histogram(
    'werkzeug_db_operation_duration_seconds',
    'Database operation duration in seconds',
    ['operation_type'] # e.g., 'query', 'commit'
)
