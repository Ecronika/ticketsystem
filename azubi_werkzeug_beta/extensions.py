from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_apscheduler import APScheduler

db = SQLAlchemy()
csrf = CSRFProtect()
scheduler = APScheduler()
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://"  # Explizit für Single-Worker-Setup
)
