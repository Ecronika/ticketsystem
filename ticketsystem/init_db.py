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
