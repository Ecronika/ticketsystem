from extensions import db
from datetime import datetime

from enum import Enum

class CheckType(str, Enum):
    CHECK = 'check'
    ISSUE = 'issue'
    RETURN = 'return'
    EXCHANGE = 'exchange'

class Azubi(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    lehrjahr = db.Column(db.Integer, default=1)
    is_archived = db.Column(db.Boolean, default=False)
    checks = db.relationship('Check', backref='azubi', lazy=True)

    def __repr__(self):
        return f'<Azubi {self.name}>'

class Werkzeug(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    material_category = db.Column(db.String(20), default="standard")
    tech_param_label = db.Column(db.String(50), nullable=True)
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
    session_id = db.Column(db.String(36), nullable=True, index=True)
    datum = db.Column(db.DateTime, default=datetime.now, index=True)
    azubi_id = db.Column(db.Integer, db.ForeignKey('azubi.id'), nullable=False)
    werkzeug_id = db.Column(db.Integer, db.ForeignKey('werkzeug.id'), nullable=False)
    bemerkung = db.Column(db.String(200), nullable=True)
    tech_param_value = db.Column(db.String(50), nullable=True)
    incident_reason = db.Column(db.String(50), nullable=True)
    
    # Audit Trail
    check_type = db.Column(db.String(20), default=CheckType.CHECK)
    examiner = db.Column(db.String(100), nullable=True)
    signature_azubi = db.Column(db.String(200), nullable=True)
    signature_examiner = db.Column(db.String(200), nullable=True)
    report_path = db.Column(db.String(200), nullable=True)
