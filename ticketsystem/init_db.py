"""
Dedicated Database Initialization Script.
Runs BEFORE the web server starts to ensure migrations and seeding are complete.
"""
import os
import sys
import logging

# Ensure project root is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app
from database_init import init_database
from models import Worker
from extensions import db
from werkzeug.security import generate_password_hash

# Configure basic logging to console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("db_init")

def run():
    logger.info("Starting pre-boot database initialization...")
    try:
        with app.app_context():
            # init_database handles migrations and seeding
            init_database(app, logger=logger)
            
            # Diagnostic: List existing workers to help user find the right login name
            workers = Worker.query.all()
            if workers:
                names = [f"'{w.name}' ({'Admin' if w.is_admin else 'Worker'})" for w in workers]
                logger.info("Found existing workers: %s", ", ".join(names))
            else:
                logger.warning("No workers found in database after seeding!")
                
            # Emergency Reset: Ensure at least one admin has PIN '0000' if requested or as fallback
            # (In HA context, we can use this to recover if migrations mess up the admin account)
            admin = Worker.query.filter_by(is_admin=True, is_active=True).first()
            if admin and not admin.pin_hash:
                logger.warning("Admin '%s' has no PIN. Setting to '0000'.", admin.name)
                admin.pin_hash = generate_password_hash("0000")
                db.session.commit()

        logger.info("Database initialization successful.")
        sys.exit(0)
    except Exception as e:
        import traceback
        logger.critical("DATABASE INITIALIZATION FAILED!")
        print(f"ERROR: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        sys.stdout.flush()
        sys.exit(1)

if __name__ == "__main__":
    run()
