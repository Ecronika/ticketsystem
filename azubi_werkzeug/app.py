from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import secrets

app = Flask(__name__)
# Database configuration
# Use DB_PATH env var if available (for HA Add-on persistence), else local file
default_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'werkzeug.db')
db_path = os.environ.get('DB_PATH', default_db_path)

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

@app.context_processor
def inject_ingress_path():
    # Helper to fix links in Home Assistant Ingress
    return {'ingress_path': request.headers.get('X-Ingress-Path', '')}

# Security: Dynamic Secret Key
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

db = SQLAlchemy(app)

# --- Database Models ---

class Azubi(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    lehrjahr = db.Column(db.Integer, default=1)
    checks = db.relationship('Check', backref='azubi', lazy=True)

    def __repr__(self):
        return f'<Azubi {self.name}>'

class Werkzeug(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    checks = db.relationship('Check', backref='werkzeug', lazy=True)

    def __repr__(self):
        return f'<Werkzeug {self.name}>'

import uuid

class Check(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(36), nullable=True) # UUID for grouping
    datum = db.Column(db.DateTime, default=datetime.utcnow)
    azubi_id = db.Column(db.Integer, db.ForeignKey('azubi.id'), nullable=False)
    werkzeug_id = db.Column(db.Integer, db.ForeignKey('werkzeug.id'), nullable=False)
    bemerkung = db.Column(db.String(200), nullable=True)

# --- Routes ---

@app.route('/')
def index():
    azubis_db = Azubi.query.all()
    azubis_data = []
    
    for azubi in azubis_db:
        # Get last check
        last_check = Check.query.filter_by(azubi_id=azubi.id).order_by(Check.datum.desc()).first()
        
        status = "Unbekannt"
        status_class = "secondary"
        last_check_str = "Noch nie"
        
        if last_check:
            last_check_str = last_check.datum.strftime("%d. %b %Y")
            days_since = (datetime.utcnow() - last_check.datum).days
            
            if days_since < 30:
                status = "Geprüft"
                status_class = "success"
            else:
                status = "Überfällig"
                status_class = "danger"
                last_check_str = f"Vor {days_since} Tagen"
        
        azubis_data.append({
            'id': azubi.id,
            'name': azubi.name,
            'lehrjahr': azubi.lehrjahr,
            'status': status,
            'status_class': status_class,
            'last_check': last_check_str
        })

    return render_template('index.html', azubis=azubis_data)

@app.route('/check/<int:azubi_id>', methods=['GET'])
def check_azubi(azubi_id):
    azubi = Azubi.query.get_or_404(azubi_id)
    werkzeuge = Werkzeug.query.all()
    current_date = datetime.now().strftime("%d. %b %Y")
    
    # Pre-fill logic: Fetch last check for each tool for this azubi
    tool_status_map = {}
    for w in werkzeuge:
        last_entry = Check.query.filter_by(azubi_id=azubi.id, werkzeug_id=w.id).order_by(Check.datum.desc()).first()
        status = 'ok' # Default
        if last_entry and last_entry.bemerkung:
             # Parse status from string "Status: xyz | ..."
             parts = last_entry.bemerkung.split('|')
             for p in parts:
                 if p.strip().startswith("Status:"):
                     status = p.replace("Status:", "").strip()
                     break
        tool_status_map[w.id] = status

    return render_template('check.html', azubi=azubi, werkzeuge=werkzeuge, current_date=current_date, tool_status_map=tool_status_map)

@app.route('/submit_check', methods=['POST'])
def submit_check():
    azubi_id = request.form.get('azubi_id')
    bemerkung_global = request.form.get('bemerkung')
    
    if not azubi_id:
        flash('Fehler: Kein Azubi ausgewählt.', 'error')
        # Ingress aware redirect
        ingress = request.headers.get('X-Ingress-Path', '')
        return redirect(f"{ingress}{url_for('index')}")

    # Generate Session ID
    session_id = str(uuid.uuid4())
    check_date = datetime.utcnow()

    werkzeuge = Werkzeug.query.all()
    for werkzeug in werkzeuge:
        status = request.form.get(f'tool_{werkzeug.id}')
        if status:
            full_bemerkung = f"Status: {status}"
            if bemerkung_global:
                full_bemerkung += f" | {bemerkung_global}"
            
            new_check = Check(
                session_id=session_id,
                azubi_id=azubi_id, 
                werkzeug_id=werkzeug.id, 
                bemerkung=full_bemerkung,
                datum=check_date
            )
            db.session.add(new_check)
    
    db.session.commit()
    flash('Prüfung erfolgreich gespeichert!', 'success')
    ingress = request.headers.get('X-Ingress-Path', '')
    return redirect(f"{ingress}{url_for('index')}")

@app.route('/history')
def history():
    # Group checks by session_id (or approximated by logic)
    # We fetch all checks ordered by date desc
    all_checks = Check.query.order_by(Check.datum.desc()).all()
    
    sessions = []
    seen_sessions = set()
    
    for check in all_checks:
        sid = check.session_id
        # Fallback for old data without session_id: group by exact timestamp + azubi
        if not sid:
            sid = f"{check.azubi_id}_{check.datum.timestamp()}"
            
        if sid not in seen_sessions:
            seen_sessions.add(sid)
            
            # Analyze this session's checks
            if check.session_id:
                session_checks = [c for c in all_checks if c.session_id == sid]
            else:
                session_checks = [c for c in all_checks if c.azubi_id == check.azubi_id and c.datum == check.datum]
            
            # Determine status
            is_ok = True
            for c in session_checks:
                # "not_issued" is neutral, doesn't break "OK" status
                if "Status: missing" in (c.bemerkung or "") or "Status: broken" in (c.bemerkung or ""):
                    is_ok = False
                    break
            
            sessions.append({
                'session_id': check.session_id if check.session_id else "LEGACY_" + sid,
                'datum': check.datum,
                'azubi_name': check.azubi.name,
                'is_ok': is_ok,
                'count': len(session_checks)
            })
            
    return render_template('history.html', sessions=sessions)

@app.route('/history_details/<path:session_id>')
def history_details(session_id):
    if session_id.startswith("LEGACY_"):
        # Decode legacy ID: "LEGACY_azubiId_timestamp"
        _, azubi_id_str, timestamp_str = session_id.split('_')
        target_time = datetime.fromtimestamp(float(timestamp_str))
        checks = Check.query.filter_by(azubi_id=int(azubi_id_str), datum=target_time).all()
    else:
        checks = Check.query.filter_by(session_id=session_id).all()
        
    if not checks:
        flash('Prüfung nicht gefunden.', 'error')
        ingress = request.headers.get('X-Ingress-Path', '')
        return redirect(f"{ingress}{url_for('history')}")

    azubi = checks[0].azubi
    datum = checks[0].datum.strftime("%d. %b %Y %H:%M")
    
    # Parse status from bemerkung for display
    # bemerkung format: "Status: ok | Note: ..."
    parsed_checks = []
    global_bemerkung = ""
    
    for c in checks:
        status_code = "ok"
        note = ""
        parts = (c.bemerkung or "").split('|')
        for p in parts:
            p = p.strip()
            if p.startswith("Status:"):
                status_code = p.replace("Status:", "").strip()
            elif not p.startswith("Status:"):
                note = p # Take the rest as note
                if note and not global_bemerkung: 
                     # Try to extract the global note (it's repeated in every check currently)
                     # In new structure we append | <global_note>
                     # simple heuristic: use the longest note found or just the first non-empty
                     global_bemerkung = note

        parsed_checks.append({
            'werkzeug': c.werkzeug.name,
            'status': status_code,
            'note': note
        })

    return render_template('history_details.html', azubi=azubi, datum=datum, checks=parsed_checks, global_bemerkung=global_bemerkung)

@app.route('/manage')
def manage():
    azubis = Azubi.query.all()
    werkzeuge = Werkzeug.query.all()
    return render_template('manage.html', azubis=azubis, werkzeuge=werkzeuge)

@app.route('/add_azubi', methods=['POST'])
def add_azubi():
    name = request.form.get('name')
    lehrjahr = request.form.get('lehrjahr', 1)
    if name:
        new_azubi = Azubi(name=name, lehrjahr=lehrjahr)
        db.session.add(new_azubi)
        db.session.commit()
        flash(f'Azubi {name} hinzugefügt.', 'success')
    ingress = request.headers.get('X-Ingress-Path', '')
    return redirect(f"{ingress}{url_for('manage')}")

@app.route('/delete_azubi/<int:id>', methods=['POST'])
def delete_azubi(id):
    azubi = Azubi.query.get_or_404(id)
    db.session.delete(azubi)
    db.session.commit()
    flash(f'Azubi {azubi.name} gelöscht.', 'success')
    ingress = request.headers.get('X-Ingress-Path', '')
    return redirect(f"{ingress}{url_for('manage')}")

@app.route('/add_werkzeug', methods=['POST'])
def add_werkzeug():
    name = request.form.get('name')
    if name:
        new_werkzeug = Werkzeug(name=name)
        db.session.add(new_werkzeug)
        db.session.commit()
        flash(f'Werkzeug {name} hinzugefügt.', 'success')
    ingress = request.headers.get('X-Ingress-Path', '')
    return redirect(f"{ingress}{url_for('manage')}")

@app.route('/delete_werkzeug/<int:id>', methods=['POST'])
def delete_werkzeug(id):
    werkzeug = Werkzeug.query.get_or_404(id)
    db.session.delete(werkzeug)
    db.session.commit()
    flash(f'Werkzeug {werkzeug.name} gelöscht.', 'success')
    ingress = request.headers.get('X-Ingress-Path', '')
    return redirect(f"{ingress}{url_for('manage')}")

# --- Helper to create DB and Seed Data ---
def setup_database():
    with app.app_context():
        db.create_all()
        
        # Simple Migration for 'lehrjahr' column
        import sqlite3
        try:
            # We need to check if column exists. SQLAlchemy doesn't do this easily with create_all.
            # We connect directly to check.
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(azubi)")
            columns = [info[1] for info in cursor.fetchall()]
            
            if 'lehrjahr' not in columns:
                print("Migrating DB: Adding 'lehrjahr' column to azubi table.")
                cursor.execute("ALTER TABLE azubi ADD COLUMN lehrjahr INTEGER DEFAULT 1")
                conn.commit()

            # Check migration for 'check' table (reserved keyword needs quoting)
            # 1. Verify table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='check'")
            if cursor.fetchone():
                # 2. Get columns
                cursor.execute('PRAGMA table_info("check")')
                check_columns = [info[1] for info in cursor.fetchall()]
                
                # 3. Add column if missing
                if 'session_id' not in check_columns:
                    print("Migrating DB: Adding 'session_id' column to check table.")
                    cursor.execute('ALTER TABLE "check" ADD COLUMN session_id VARCHAR(36)')
                    conn.commit()
            
            conn.close()
        except Exception as e:
            print(f"Migration Info: {e}")

        # Seed only if absolutely empty? Or just leave it.
        # Original logic preserved for "Dummy Data" if strictly needed, 
        # but user likely wants to manage their own.
        if not Azubi.query.first():
            db.session.add(Azubi(name="Max Mustermann", lehrjahr=2))
            db.session.add(Azubi(name="Lisa Müller", lehrjahr=1))
            db.session.commit()
            print("Created Dummy Azubis")
            
        if not Werkzeug.query.first():
            db.session.add(Werkzeug(name="Schlitzschraubendreher 3mm"))
            db.session.add(Werkzeug(name="Kreuzschlitz PH2"))
            db.session.add(Werkzeug(name="Zange Knipex"))
            db.session.add(Werkzeug(name="Hammer 500g"))
            db.session.commit()
            print("Created Dummy Werkzeuge")

if __name__ == '__main__':
    setup_database()
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)
