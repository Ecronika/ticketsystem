"""Prometheus metrics definitions for Azubi Werkzeug Tracker."""
from prometheus_client import Counter, Gauge, Histogram


# --- Prometheus Metrics Definitions ---

# Tracks total HTTP requests by method and endpoint
HTTP_REQUESTS_TOTAL = Counter(
    'http_requests_total',
    'Total number of HTTP requests',
    ['method', 'endpoint', 'http_status']
)

# Tracks latency of HTTP requests
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint']
)

# Custom Application Metrics
ACTIVE_SESSIONS = Gauge(
    'active_sessions',
    'Number of currently active HTTP requests (concurrent sessions)'
)

DB_OPERATION_DURATION_SECONDS = Histogram(
    'db_operation_duration_seconds',
    'Database operation duration in seconds',
    ['operation_type']  # e.g., 'query', 'commit'
)

