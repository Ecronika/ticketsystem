from flask import Flask, render_template, request, redirect, url_for, flash
from extensions import db, csrf, limiter
from routes import main_bp
from models import Azubi, Werkzeug, Examiner, Check
import os
import secrets
import logging
import sys

app = Flask(__name__)

# Security: Session Configuration
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    # SESSION_COOKIE_SECURE=True # Disabled for Ingress (SSL terminated by HA Proxy)
)

# Logging Configuration
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
app.logger.addHandler(handler)
app.logger.setLevel(logging.INFO)

# Database configuration
default_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'werkzeug.db')
db_path = os.environ.get('DB_PATH', default_db_path)
data_dir = os.path.dirname(db_path)

# Export DATA_DIR for routes to use
app.config['DATA_DIR'] = data_dir

# Ensure data directories exist
os.makedirs(os.path.join(data_dir, 'signatures'), exist_ok=True)
os.makedirs(os.path.join(data_dir, 'reports'), exist_ok=True)

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Security: Dynamic Secret Key (Persistent)
secret_file = os.path.join(data_dir, 'secret.key')
if os.path.exists(secret_file):
    try:
        with open(secret_file, 'r') as f:
            app.secret_key = f.read().strip()
    except Exception:
        app.secret_key = secrets.token_hex(32)
else:
    app.secret_key = secrets.token_hex(32)
    try:
        with open(secret_file, 'w') as f:
            f.write(app.secret_key)
    except OSError:
        pass

# Initialize Extensions
# Initialize Extensions
csrf.init_app(app)
db.init_app(app)
limiter.init_app(app)

# Register Blueprints
app.register_blueprint(main_bp)

# --- Helper to create DB and Seed Data ---
def setup_database():
    with app.app_context():
        db.create_all()
        
        import sqlite3
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # --- Check 'tech_param_value' in 'check' table ---
            cursor.execute('PRAGMA table_info("check")')
            check_columns = [info[1] for info in cursor.fetchall()]
            if 'tech_param_value' not in check_columns:
                app.logger.info("Migrating DB: Adding 'tech_param_value' column to check table.")
                cursor.execute('ALTER TABLE "check" ADD COLUMN tech_param_value VARCHAR(50)')
                conn.commit()

            # --- Check 'incident_reason' in 'check' table (Phase 2) ---
            if 'incident_reason' not in check_columns:
                 app.logger.info("Migrating DB: Adding 'incident_reason' column to check table.")
                 cursor.execute('ALTER TABLE "check" ADD COLUMN incident_reason VARCHAR(50)')
                 conn.commit()

            # --- Check 'tech_param_label' in 'werkzeug' table ---
            cursor.execute("PRAGMA table_info(werkzeug)")
            werkzeug_columns = [info[1] for info in cursor.fetchall()]
            if 'tech_param_label' not in werkzeug_columns:
                app.logger.info("Migrating DB: Adding 'tech_param_label' column to werkzeug table.")
                cursor.execute("ALTER TABLE werkzeug ADD COLUMN tech_param_label VARCHAR(50)")
                conn.commit()
                
            # --- Phase 3: Audit Trail Columns in 'Check' ---
            cursor.execute('PRAGMA table_info("check")')
            check_columns_audit = [info[1] for info in cursor.fetchall()]
            
            if 'check_type' not in check_columns_audit:
                app.logger.info("Migrating DB: Phase 3 Columns...")
                cursor.execute("ALTER TABLE \"check\" ADD COLUMN check_type VARCHAR(20) DEFAULT 'check'")
                cursor.execute("ALTER TABLE \"check\" ADD COLUMN examiner VARCHAR(100)")
                cursor.execute("ALTER TABLE \"check\" ADD COLUMN signature_azubi VARCHAR(200)")
                cursor.execute("ALTER TABLE \"check\" ADD COLUMN signature_examiner VARCHAR(200)")
                cursor.execute("ALTER TABLE \"check\" ADD COLUMN report_path VARCHAR(200)")
                conn.commit()
            
            # --- Phase 3.5: Examiner Table ---
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='examiner'")
            if not cursor.fetchone():
                pass 
            
            # --- Phase 6: is_archived in 'Azubi' ---
            cursor.execute("PRAGMA table_info(azubi)")
            azubi_columns = [info[1] for info in cursor.fetchall()]
            if 'is_archived' not in azubi_columns:
                app.logger.info("Migrating DB: Adding 'is_archived' column to azubi table.")
                cursor.execute("ALTER TABLE azubi ADD COLUMN is_archived BOOLEAN DEFAULT 0")
                conn.commit()

            # --- Phase 8: Performance Indexes ---
            cursor.execute("PRAGMA index_list('check')")
            # index_list returns (seq, name, unique)
            indexes = [row[1] for row in cursor.fetchall()]
            
            if 'idx_check_session_id' not in indexes:
                app.logger.info("Migrating DB: Creating Index idx_check_session_id")
                cursor.execute("CREATE INDEX idx_check_session_id ON \"check\" (session_id)")
                conn.commit()

            if 'idx_check_datum' not in indexes:
                app.logger.info("Migrating DB: Creating Index idx_check_datum")
                cursor.execute("CREATE INDEX idx_check_datum ON \"check\" (datum)")
                conn.commit()

            conn.close()
        except Exception as e:
            app.logger.error(f"Migration Info: {e}")



# --- Global Error Handlers ---
@app.errorhandler(413) # Payload Too Large
def request_entity_too_large(e):
    app.logger.warning(f"File upload too large: {request.content_length}")
    flash('Datei zu groß (max. 2MB).', 'error')
    return redirect(url_for('main.manage'))

@app.errorhandler(Exception)
def handle_exception(e):
    # Pass through HTTP errors
    if isinstance(e, int):
        return e
        
    app.logger.error(f"Unhandled Exception: {e}", exc_info=True)
    return render_template('base.html', content=f"<h1>Ein unerwarteter Fehler ist aufgetreten</h1><p>{e}</p>"), 500

if __name__ == '__main__':
    setup_database()
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)
