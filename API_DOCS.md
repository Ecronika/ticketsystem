# API Documentation - Azubi Werkzeug Tracker v2.9

This document outlines the available API endpoints and helper scripts for the Azubi Werkzeug application.

## Base URL
All API requests are relative to the application root. When running locally: `http://localhost:5000`

## Authenticated Endpoints
Most endpoints require a valid user session (login). CSRF tokens are required for POST requests.

### 1. Tool Management

#### `GET /api/assigned_tools/<int:azubi_id>`
Returns a list of tools currently assigned to a specific Azubi.

- **Parameters:**
    - `azubi_id` (path): ID of the Azubi.
- **Response:** JSON array of objects.
    ```json
    [
        {"id": 1, "name": "Hammer"},
        {"id": 5, "name": "Zange"}
    ]
    ```

### 2. Operations

#### `POST /exchange_tool`
Performs a one-click tool exchange (Return old + Issue new).

- **Content-Type:** `application/x-www-form-urlencoded`
- **Parameters:**
    - `azubi_id`: ID of the Azubi.
    - `exchange_data`: JSON string representing an array of selected tools and their reasons. Example: `[{"tool_id": "1", "reason": "Defekt"}, {"tool_id": "5", "reason": "Verloren"}]`.
    - `is_payable`: "on" if the Azubi must pay for the replacement (optional).
    - `signature_azubi_data`: Base64 encoded PNG signature (data:image/png;base64,...).
    - `csrf_token`: Valid CSRF token.

#### `GET /api/history`
Fetches a paginated list of check sessions for dynamic "Load More" functionality on the frontend.

- **Parameters (Query):**
    - `page` (int, default: 1): The page number to retrieve.
    - `azubi_id` (int or "all", default: "all"): Filter history by a specific Azubi.
- **Response:** JSON
    ```json
    {
        "success": true,
        "sessions": [ ... ],
        "has_next": true,
        "next_page": 2,
        "total": 150
    }
    ```

### 3. Authentication & Security

#### `POST /recover_pin`
Consumes a single-use recovery token to securely log in and prompt the user to reset a forgotten admin PIN.

- **Parameters:**
    - `token`: The emergency recovery token (e.g., `RT-XXXX-XXXX`).

#### `POST /settings/security/generate_tokens`
Generates a new batch of 5 emergency recovery tokens. Invalidates all previously generated tokens immediately.

### 4. System

#### `GET /health`
Health check endpoint for monitoring (e.g., Docker Healthcheck).

- **Response:** JSON
    ```json
    {"status": "healthy", "uptime": 123.45}
    ```
- **Status Codes:**
    - `200`: OK
    - `500`: Database or App failure

#### `GET /metrics`
Prometheus metrics endpoint. Exposes application metrics like HTTP request durations (`flask_http_request_duration_seconds`), check submissions (`werkzeug_checks_submitted_total`), and scan counts (`werkzeug_scans_total`).

## CLI Commands

These commands are executed via the command line from the application root directory.

### Database Migrations (Alembic)
Manage database schemas seamlessly via Alembic.
```bash
flask db upgrade
flask db migrate -m "Description"
```

### Backup
Create a snapshot of the database, signatures, and config.
```bash
python backup.py
```
- **Output:** `backups/backup_YYYYMMDD_HHMMSS.zip`

### Rollback
Restore the application state from a specific backup.
```bash
python rollback.py <backup_filename>
```
- **Example:** `python rollback.py backup_20260213_120000.zip`
- **Warning:** This overwrites the current database and signatures!
