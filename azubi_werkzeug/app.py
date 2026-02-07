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

class Check(db.Model):
    id = db.Column(db.Integer, primary_key=True)
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
    return render_template('check.html', azubi=azubi, werkzeuge=werkzeuge, current_date=current_date)

@app.route('/submit_check', methods=['POST'])
def submit_check():
    azubi_id = request.form.get('azubi_id')
    bemerkung = request.form.get('bemerkung')
    
    if not azubi_id:
        flash('Fehler: Kein Azubi ausgewählt.', 'error')
        # Ingress aware redirect
        ingress = request.headers.get('X-Ingress-Path', '')
        return redirect(f"{ingress}{url_for('index')}")

    # Iterate over all tools and save status
    werkzeuge = Werkzeug.query.all()
    for werkzeug in werkzeuge:
        status = request.form.get(f'tool_{werkzeug.id}')
        if status:
            full_bemerkung = f"Status: {status}"
            if bemerkung:
                full_bemerkung += f" | Note: {bemerkung}"
            
            new_check = Check(
                azubi_id=azubi_id, 
                werkzeug_id=werkzeug.id, 
                bemerkung=full_bemerkung,
                datum=datetime.utcnow() 
            )
            db.session.add(new_check)
    
    db.session.commit()
    flash('Prüfung erfolgreich gespeichert!', 'success')
    ingress = request.headers.get('X-Ingress-Path', '')
    return redirect(f"{ingress}{url_for('index')}")

@app.route('/history')
def history():
    # Show last 50 checks, newest first
    checks = Check.query.order_by(Check.datum.desc()).limit(50).all()
    return render_template('history.html', checks=checks)

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
