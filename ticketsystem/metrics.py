"""Prometheus metrics definitions for the Ticket System."""

from prometheus_client import Counter, Gauge, Histogram

__all__ = [
    "HTTP_REQUESTS_TOTAL",
    "HTTP_REQUEST_DURATION_SECONDS",
    "ACTIVE_SESSIONS",
    "DB_OPERATION_DURATION_SECONDS",
]

HTTP_REQUESTS_TOTAL: Counter = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "http_status"],
)

HTTP_REQUEST_DURATION_SECONDS: Histogram = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
)

ACTIVE_SESSIONS: Gauge = Gauge(
    "active_sessions",
    "Number of currently active HTTP requests (concurrent sessions)",
)

DB_OPERATION_DURATION_SECONDS: Histogram = Histogram(
    "db_operation_duration_seconds",
    "Database operation duration in seconds",
    ["operation_type"],
)
