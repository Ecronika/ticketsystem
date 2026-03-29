"""
Dedicated Database Initialization Script.
Runs BEFORE the web server starts to ensure migrations and seeding are complete.
"""
import os
import sys
import logging

# Ensure project root is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# FIX: Suppress scheduler during DB initialization to prevent locks
os.environ["RUN_SCHEDULER"] = "0"

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
    print("--- PRE-BOOT DATABASE INIT START ---", file=sys.stderr, flush=True)
    try:
        with app.app_context():
            # init_database handles migrations and seeding
            init_database(app, logger=logger)
            
            # Diagnostics
            workers = Worker.query.all()
            if workers:
                names = [f"'{w.name}' ({'Admin' if w.is_admin else 'Worker'})" for w in workers]
                print(f"Found existing workers: {', '.join(names)}", file=sys.stderr, flush=True)
            else:
                print("WARNING: No workers found in database!", file=sys.stderr, flush=True)

        print("--- PRE-BOOT DATABASE INIT SUCCESSFUL ---", file=sys.stderr, flush=True)
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
