# Ticket System Boilerplate

A clean, modern boilerplate for a Ticket Management System, built with Flask, SQLAlchemy, and a Bento-Grid design system.

## Features
- **Modern UI**: Bento-Grid layout with vanilla CSS and Bootstrap 5.3.
- **Dark Mode**: Built-in theme switcher with high-contrast support.
- **PIN Authentication**: Secure access via PIN login.
- **Docker Ready**: Includes Dockerfile and docker-compose configurations.
- **Prometheus Metrics**: Pre-configured `/metrics` endpoint for monitoring.
- **SQLite Optimization**: Pre-optimized for local SQLite deployments (WAL mode).

## Getting Started
1. Clone the repository.
2. Initialize migrations: `flask db init`.
3. Start the application: `python app.py` or `docker-compose up`.

## Project Structure
- `app.py`: Main entry point.
- `models.py`: Database models (includes a placeholder `Ticket` model).
- `routes/`: Blueprint-based routing logic.
- `static/`: CSS, JS, and image assets.
- `templates/`: Jinja2 templates.
