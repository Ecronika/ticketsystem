
import os
import sys

# Add the app directory to sys.path
sys.path.append(os.path.join(os.getcwd()))

from app import app
from extensions import db

with app.app_context():
    print("Creating all tables...")
    db.create_all()
    print("Done!")
