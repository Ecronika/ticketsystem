from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import secrets
import uuid
import base64
from pdf_utils import generate_handover_pdf

app = Flask(__name__)
# Database configuration
# Use DB_PATH env var if available (for HA Add-on persistence), else local file
default_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'werkzeug.db')
db_path = os.environ.get('DB_PATH', default_db_path)

# Ensure data directories exist
data_dir = os.path.dirname(db_path)
os.makedirs(os.path.join(data_dir, 'signatures'), exist_ok=True)
os.makedirs(os.path.join(data_dir, 'reports'), exist_ok=True)

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
    # inventory_number = db.Column(db.String(50), nullable=True) # DEPRECATED v2.0.2
    # serial_number = db.Column(db.String(50), nullable=True) # DEPRECATED v2.0.2
    material_category = db.Column(db.String(20), default="standard") # REQ-SEC-01 (standard, vollisoliert, teilisoliert, isolierend)
    # inspection_interval_months = db.Column(db.Integer, default=12) # DEPRECATED v2.0.2
    # last_inspection_date = db.Column(db.DateTime, nullable=True) # DEPRECATED v2.0.2
    tech_param_label = db.Column(db.String(50), nullable=True) # New v2.0.2: e.g. "Größe", "Gewicht"
    checks = db.relationship('Check', backref='werkzeug', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Werkzeug {self.name}>'

class Examiner(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    
    def __repr__(self):
        return f'<Examiner {self.name}>'

class Check(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(36), nullable=True) # UUID for grouping
    datum = db.Column(db.DateTime, default=datetime.now)
    azubi_id = db.Column(db.Integer, db.ForeignKey('azubi.id'), nullable=False)
    werkzeug_id = db.Column(db.Integer, db.ForeignKey('werkzeug.id'), nullable=False)
    bemerkung = db.Column(db.String(200), nullable=True)
    tech_param_value = db.Column(db.String(50), nullable=True) # New v2.0.2: e.g. "10", "500g"
    incident_reason = db.Column(db.String(50), nullable=True) # New v2.1.0: "Verschleiß", "Verloren", "Defekt (Fahrlässig)"
    
    # Phase 3: Audit Trail & Handover
    check_type = db.Column(db.String(20), default="check") # 'issue', 'check', 'return'
    examiner = db.Column(db.String(100), nullable=True)
    signature_azubi = db.Column(db.String(200), nullable=True) # Path to signature file
    signature_examiner = db.Column(db.String(200), nullable=True) # Path to signature file
    report_path = db.Column(db.String(200), nullable=True) # Path to generated PDF

# --- Routes ---



# --- Helper Functions ---
def get_assigned_tools(azubi_id):
    """Calculates currently assigned tools for an Azubi based on history."""
    # Logic: 
    # Iterate through all checks/issues/returns for this azubi, ordered by date.
    # Maintain a set of assigned tool_ids.
    # Issue -> Add to set
    # Return -> Remove from set
    # Check -> No change
    # If a tool has NEVER been issued, it is NOT assigned.
    
    checks = Check.query.filter_by(azubi_id=azubi_id).order_by(Check.datum.asc()).all()
    assigned = set()
    
    for c in checks:
        if c.check_type == 'issue':
            assigned.add(c.werkzeug_id)
        elif c.check_type == 'return':
            if c.werkzeug_id in assigned:
                assigned.remove(c.werkzeug_id)
        # 'check' type assumes tool is already assigned, doesn't change status
        
    return assigned

@app.route('/')
def index():
    azubis_db = Azubi.query.all()
    azubis_data = []
    
    for azubi in azubis_db:
        # Get last check (any type)
        last_check = Check.query.filter_by(azubi_id=azubi.id).order_by(Check.datum.desc()).first()
        
        status = "Unbekannt"
        status_class = "secondary"
        last_check_str = "Noch nie"
        
        if last_check:
            last_check_str = last_check.datum.strftime("%d. %b %Y")
            days_since = (datetime.now() - last_check.datum).days
            
            # Global 3-Month Rule (90 Days)
            if days_since < 90:
                status = "Geprüft"
                status_class = "success"
            else:
                status = "Überfällig (> 3 Mon.)"
                status_class = "danger"
                last_check_str = f"Vor {days_since} Tagen"
        else:
            # New Phase 3: If no check, maybe just registered
            status = "Neu / Leer"
            status_class = "info"
        
        assigned_count = len(get_assigned_tools(azubi.id))
        
        azubis_data.append({
            'id': azubi.id,
            'name': azubi.name,
            'lehrjahr': azubi.lehrjahr,
            'status': status,
            'status_class': status_class,
            'last_check': last_check_str,
            'assigned_count': assigned_count
        })

    return render_template('index.html', azubis=azubis_data)

@app.route('/check/<int:azubi_id>', methods=['GET'])
def check_azubi(azubi_id):
    azubi = Azubi.query.get_or_404(azubi_id)
    werkzeuge = Werkzeug.query.all()
    examiners = Examiner.query.all()
    current_date = datetime.now().strftime("%d. %b %Y")
    
    # Calculate assigned tools
    assigned_ids = get_assigned_tools(azubi.id)
    
    # Pre-fill logic: Fetch last check for each tool for this azubi
    tool_status_map = {}
    tool_tech_values = {}
    
    last_check_global = Check.query.filter_by(azubi_id=azubi.id).order_by(Check.datum.desc()).first()
    days_since_global = (datetime.now() - last_check_global.datum).days if last_check_global else 999
    is_overdue = days_since_global > 90

    mapped_werkzeuge = []
    for w in werkzeuge:
        last_entry = Check.query.filter_by(azubi_id=azubi.id, werkzeug_id=w.id).order_by(Check.datum.desc()).first()
        status = 'ok' # Default
        tech_val = ""
        
        if last_entry:
            if last_entry.bemerkung:
                 parts = last_entry.bemerkung.split('|')
                 for p in parts:
                     if p.strip().startswith("Status:"):
                         status = p.replace("Status:", "").strip()
                         break
            if last_entry.tech_param_value:
                tech_val = last_entry.tech_param_value

        mapped_werkzeuge.append({
            'obj': w,
            'is_assigned': w.id in assigned_ids,
            'last_status': status,
            'last_tech_val': tech_val
        })

    return render_template('check.html', azubi=azubi, werkzeuge=mapped_werkzeuge, examiners=examiners, current_date=current_date, 
                           is_overdue=is_overdue)

@app.route('/submit_check', methods=['POST'])
def submit_check():
    azubi_id = request.form.get('azubi_id')
    bemerkung_global = request.form.get('bemerkung')
    check_type = request.form.get('check_type', 'check')
    examiner = request.form.get('examiner')
    
    if not azubi_id or not examiner:
        flash('Fehler: Azubi und Prüfer müssen angegeben werden.', 'error')
        ingress = request.headers.get('X-Ingress-Path', '')
        return redirect(f"{ingress}{url_for('index')}")

    # Handle Signatures
    sig_azubi_data = request.form.get('signature_azubi_data')
    sig_examiner_data = request.form.get('signature_examiner_data')
    
    # Save Signatures to Disk
    session_id = str(uuid.uuid4())
    sig_azubi_path = None
    sig_examiner_path = None
    
    if sig_azubi_data and ',' in sig_azubi_data:
        # data:image/png;base64,.....
        header, encoded = sig_azubi_data.split(",", 1)
        data = base64.b64decode(encoded)
        path = os.path.join(data_dir, 'signatures', f"{session_id}_azubi.png")
        with open(path, "wb") as f:
            f.write(data)
        sig_azubi_path = path

    if sig_examiner_data and ',' in sig_examiner_data:
        header, encoded = sig_examiner_data.split(",", 1)
        data = base64.b64decode(encoded)
        path = os.path.join(data_dir, 'signatures', f"{session_id}_examiner.png")
        with open(path, "wb") as f:
            f.write(data)
        sig_examiner_path = path

    check_date = datetime.now()
    
    # Process Selected Tools
    selected_tools = [] # For PDF
    werkzeuge = Werkzeug.query.all()
    
    reports_to_create = []

    for werkzeug in werkzeuge:
        # Check if this tool was part of the form submission (checkbox or hidden input)
        # The form should send data for selected tools.
        # Logic: We depend on 'tool_{id}' existing in form.
        
        status = request.form.get(f'tool_{werkzeug.id}')
        
        if status: # Tool was selected/checked
            tech_val = request.form.get(f'tech_param_{werkzeug.id}')
            incident_reason = request.form.get(f'incident_reason_{werkzeug.id}') 
            
            full_bemerkung = f"Status: {status}"
            if bemerkung_global:
                full_bemerkung += f" | {bemerkung_global}"
            
            new_check = Check(
                session_id=session_id,
                azubi_id=azubi_id, 
                werkzeug_id=werkzeug.id, 
                bemerkung=full_bemerkung,
                tech_param_value=tech_val,
                incident_reason=incident_reason,
                datum=check_date,
                check_type=check_type,
                examiner=examiner,
                signature_azubi=sig_azubi_path,
                signature_examiner=sig_examiner_path
            )
            db.session.add(new_check)
            reports_to_create.append(new_check)
            
            selected_tools.append({
                'id': werkzeug.id,
                'name': werkzeug.name,
                'category': werkzeug.material_category,
                'status': status
            })

    # Generate PDF
    if selected_tools:
        azubi = Azubi.query.get(azubi_id)
        pdf_filename = f"Protokoll_{check_type}_{azubi.name.replace(' ', '_')}_{check_date.strftime('%Y%m%d_%H%M')}.pdf"
        pdf_path = os.path.join(data_dir, 'reports', pdf_filename)
        
        generate_handover_pdf(
            azubi_name=azubi.name, 
            examiner_name=examiner, 
            tools=selected_tools, 
            check_type=check_type, 
            signature_paths={'azubi': sig_azubi_path, 'examiner': sig_examiner_path},
            output_path=pdf_path
        )
        
        # Update records with report path
        for record in reports_to_create:
            record.report_path = pdf_path

    db.session.commit()
    flash(f'{check_type.capitalize()} erfolgreich gespeichert! PDF erstellt.', 'success')
    ingress = request.headers.get('X-Ingress-Path', '')
    return redirect(f"{ingress}{url_for('index')}")

# ... (history routes omitted) ...

@app.route('/history')
def history():
    # Group checks by session_id (or approximated by logic)
    # We fetch all checks ordered by date desc
    # Performance Fix: Limit to 100 most recent checks to prevent rendering lag
    all_checks = Check.query.order_by(Check.datum.desc()).limit(100).all()
    
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
    
    # Audit Data (Phase 3)
    # Assumes same for all checks in session
    first_c = checks[0]
    check_type = first_c.check_type
    examiner = first_c.examiner
    report_path = first_c.report_path
    
    # Signature Paths (Relative for template if needed, but currently served via specific route maybe? 
    # Actually, we can just serve them via a route or assume they are static if moved?
    # Better to serve via route for security/simplicity outside static)
    
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
                # Potential note
                if p and not global_bemerkung: 
                     global_bemerkung = p
        
        tech_label = c.werkzeug.tech_param_label
        tech_value = c.tech_param_value
        incident_reason = c.incident_reason

        parsed_checks.append({
            'werkzeug': c.werkzeug.name,
            'status': status_code,
            'tech_label': tech_label,
            'tech_value': tech_value,
            'incident_reason': incident_reason
        })

    return render_template('history_details.html', 
                           azubi=azubi, 
                           datum=datum, 
                           checks=parsed_checks, 
                           global_bemerkung=global_bemerkung,
                           check_type=check_type,
                           examiner=examiner,
                           report_path=report_path)

@app.route('/download_report/<path:filename>')
def download_report(filename):
    # Securely serve PDF from reports directory
    reports_dir = os.path.join(data_dir, 'reports')
    return send_from_directory(reports_dir, filename, as_attachment=True)

@app.route('/manage')
def manage():
    azubis = Azubi.query.all()
    werkzeuge = Werkzeug.query.all()
    examiners = Examiner.query.all()
    return render_template('manage.html', azubis=azubis, werkzeuge=werkzeuge, examiners=examiners)

@app.route('/add_examiner', methods=['POST'])
def add_examiner():
    name = request.form.get('name')
    if name:
        new_examiner = Examiner(name=name)
        db.session.add(new_examiner)
        db.session.commit()
        flash(f'Prüfer {name} hinzugefügt.', 'success')
    ingress = request.headers.get('X-Ingress-Path', '')
    return redirect(f"{ingress}{url_for('manage')}")

@app.route('/delete_examiner/<int:id>', methods=['POST'])
def delete_examiner(id):
    examiner = Examiner.query.get_or_404(id)
    db.session.delete(examiner)
    db.session.commit()
    flash(f'Prüfer {examiner.name} gelöscht.', 'success')
    ingress = request.headers.get('X-Ingress-Path', '')
    return redirect(f"{ingress}{url_for('manage')}")

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

@app.route('/edit_azubi/<int:id>', methods=['POST'])
def edit_azubi(id):
    azubi = Azubi.query.get_or_404(id)
    name = request.form.get('name')
    lehrjahr = request.form.get('lehrjahr')
    
    if name:
        azubi.name = name
    if lehrjahr:
        azubi.lehrjahr = lehrjahr
        
    db.session.commit()
    flash(f'Azubi {azubi.name} aktualisiert.', 'success')
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
    # Inventory/Serial removed in UI
    material_category = request.form.get('material_category', 'standard')
    tech_param_label = request.form.get('tech_param_label') # New
    
    if name:
        new_werkzeug = Werkzeug(
            name=name,
            material_category=material_category,
            tech_param_label=tech_param_label
        )
        db.session.add(new_werkzeug)
        db.session.commit()
        flash(f'Werkzeug {name} hinzugefügt.', 'success')
    ingress = request.headers.get('X-Ingress-Path', '')
    return redirect(f"{ingress}{url_for('manage')}")

@app.route('/edit_werkzeug/<int:id>', methods=['POST'])
def edit_werkzeug(id):
    werkzeug = Werkzeug.query.get_or_404(id)
    name = request.form.get('name')
    material_category = request.form.get('material_category')
    tech_param_label = request.form.get('tech_param_label')
    
    if name:
        werkzeug.name = name
    if material_category:
        werkzeug.material_category = material_category
    if tech_param_label is not None: # Can be empty string
        werkzeug.tech_param_label = tech_param_label
        
    db.session.commit()
    flash(f'Werkzeug {werkzeug.name} aktualisiert.', 'success')
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
        
        import sqlite3
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # --- Check 'tech_param_value' in 'check' table ---
            cursor.execute('PRAGMA table_info("check")')
            check_columns = [info[1] for info in cursor.fetchall()]
            if 'tech_param_value' not in check_columns:
                print("Migrating DB: Adding 'tech_param_value' column to check table.")
                cursor.execute('ALTER TABLE "check" ADD COLUMN tech_param_value VARCHAR(50)')
                conn.commit()

            # --- Check 'incident_reason' in 'check' table (Phase 2) ---
            if 'incident_reason' not in check_columns:
                 print("Migrating DB: Adding 'incident_reason' column to check table.")
                 cursor.execute('ALTER TABLE "check" ADD COLUMN incident_reason VARCHAR(50)')
                 conn.commit()

            # --- Check 'tech_param_label' in 'werkzeug' table ---
            cursor.execute("PRAGMA table_info(werkzeug)")
            werkzeug_columns = [info[1] for info in cursor.fetchall()]
            if 'tech_param_label' not in werkzeug_columns:
                print("Migrating DB: Adding 'tech_param_label' column to werkzeug table.")
                cursor.execute("ALTER TABLE werkzeug ADD COLUMN tech_param_label VARCHAR(50)")
                conn.commit()
                
            # --- Phase 3: Audit Trail Columns in 'Check' ---
            cursor.execute('PRAGMA table_info("check")')
            check_columns_audit = [info[1] for info in cursor.fetchall()]
            
            if 'check_type' not in check_columns_audit:
                print("Migrating DB: Phase 3 Columns...")
                cursor.execute("ALTER TABLE \"check\" ADD COLUMN check_type VARCHAR(20) DEFAULT 'check'")
                cursor.execute("ALTER TABLE \"check\" ADD COLUMN examiner VARCHAR(100)")
                cursor.execute("ALTER TABLE \"check\" ADD COLUMN signature_azubi VARCHAR(200)")
                cursor.execute("ALTER TABLE \"check\" ADD COLUMN signature_examiner VARCHAR(200)")
                cursor.execute("ALTER TABLE \"check\" ADD COLUMN report_path VARCHAR(200)")
                conn.commit()
            
            # --- Phase 3.5: Examiner Table ---
            # SQLAlchemy create_all handles creation if not exists, but good to be explicit or handle migrations
            # if we were adding columns. Since it's a new table, create_all should cover it.
            # However, let's verify it exists just in case.
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='examiner'")
            if not cursor.fetchone():
                print("Migrating DB: Creating 'examiner' table...")
                # create_all above should have done this, but if db already existed, it might skip?
                # Actually create_all ONLY creates tables that don't exist.
                # So if we added the model, it should be fine.
                pass 
            
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
            
        # Seed dummy examiner if none?
        if not Examiner.query.first():
             # Optional: Seed a default examiner
             pass

if __name__ == '__main__':
    setup_database()
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)
