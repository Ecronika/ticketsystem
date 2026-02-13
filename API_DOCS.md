# API Documentation - Azubi Werkzeug Tracker v2.5.1

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
    - `tool_id`: ID of the tool being exchanged.
    - `reason`: Reason for exchange ("Defekt", "Verloren", "Verschlissen").
    - `is_payable`: "on" if the Azubi must pay for the replacement (optional).
    - `signature_azubi_data`: Base64 encoded PNG signature (data:image/png;base64,...).
    - `csrf_token`: Valid CSRF token.

### 3. System

#### `GET /health`
Health check endpoint for monitoring (e.g., Docker Healthcheck).

- **Response:** JSON
    ```json
    {"status": "healthy", "uptime": 123.45}
    ```
- **Status Codes:**
    - `200`: OK
    - `500`: Database or App failure

## Helper Scripts (CLI)

These scripts are located in the application root directory.

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
