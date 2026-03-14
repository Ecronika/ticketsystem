
import os
import sys

# Add the app directory to sys.path
sys.path.append(os.path.join(os.getcwd()))

from app import app
from extensions import db
from models import Check, Werkzeug

def backfill_prices():
    with app.app_context():
        print("Starting price backfill...")
        checks = Check.query.all()
        updated_count = 0
        
        for check in checks:
            if check.price is None:
                # Fallback to current tool price
                if check.werkzeug:
                    check.price = check.werkzeug.price
                else:
                    check.price = 0.0
                updated_count += 1
        
        db.session.commit()
        print(f"Backfill completed. Updated {updated_count} records.")

if __name__ == "__main__":
    backfill_prices()
