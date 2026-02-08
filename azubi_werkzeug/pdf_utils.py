from fpdf import FPDF
import os
from datetime import datetime

class HandoverReport(FPDF):
    def __init__(self, title="Werkzeug-Protokoll"):
        super().__init__()
        self.report_title = title
        self.add_page()
        
    def header(self):
        # Logo could go here
        # self.image('logo.png', 10, 8, 33)
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, self.report_title, 0, 1, 'C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Seite {self.page_no()}/{{nb}}', 0, 0, 'C')

    def chapter_title(self, label):
        self.set_font('Arial', 'B', 12)
        self.set_fill_color(200, 220, 255)
        self.cell(0, 6, label, 0, 1, 'L', 1)
        self.ln(4)

    def chapter_body(self, text):
        self.set_font('Arial', '', 12)
        self.multi_cell(0, 5, text)
        self.ln()

def generate_handover_pdf(azubi_name, examiner_name, tools, check_type, signature_paths, output_path):
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Translate Check Type for Title
    type_map = {
        'issue': 'Ausgabe',
        'return': 'Rückgabe',
        'check': 'Prüf'
    }
    title_type = type_map.get(check_type, 'Protokoll')
    
    pdf = HandoverReport(title=f"Werkzeug-{title_type}-Protokoll")
    pdf.alias_nb_pages()
    
    # Meta Data
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 10, f"Datum: {datetime.now().strftime('%d.%m.%Y %H:%M')}", 0, 1)
    pdf.cell(0, 10, f"Azubi: {azubi_name}", 0, 1)
    pdf.cell(0, 10, f"Prüfer: {examiner_name}", 0, 1)
    pdf.ln(10)
    
    # Tool List
    pdf.chapter_title("Betroffene Werkzeuge")
    pdf.set_font('Arial', 'B', 10)
    # Header - Total width ~190
    # pdf.cell(10, 10, "ID", 1) # Removed
    pdf.cell(90, 10, "Werkzeug", 1)
    pdf.cell(50, 10, "Kategorie", 1)
    pdf.cell(50, 10, "Zustand", 1)
    pdf.ln()
    
    pdf.set_font('Arial', '', 10)
    for tool in tools:
        # tool struct: {'id': 1, 'name': 'Hammer', 'category': 'standard', 'status': 'ok'}
        
        # Translate Status
        status_map = {
            'ok': 'In Ordnung',
            'missing': 'Fehlt',
            'broken': 'Defekt',
            'not_issued': 'Nicht ausgegeben'
        }
        status_text = status_map.get(tool['status'], tool['status'])
        
        # Translate Category (if needed, though likely already German-ish in DB 'standard', 'teilisoliert')
        # DB limits: standard, teilisoliert, vollisoliert, isolierend
        cat_map = {
            'standard': 'Standard',
            'teilisoliert': 'Teilisoliert',
            'vollisoliert': 'Vollisoliert (1000V)',
            'isolierend': 'Vollkunststoff'
        }
        cat_text = cat_map.get(tool['category'], tool['category'])

        # pdf.cell(10, 10, str(tool['id']), 1) # Removed
        pdf.cell(90, 10, tool['name'], 1)
        pdf.cell(50, 10, cat_text, 1)
        pdf.cell(50, 10, status_text, 1)
        pdf.ln()
        
    pdf.ln(20)
    
    # Signatures
    pdf.chapter_title("Unterschriften")
    
    start_y = pdf.get_y()
    
    # Azubi Signature
    pdf.set_xy(10, start_y)
    pdf.cell(90, 40, "", 1) # Box
    pdf.text(12, start_y + 5, "Unterschrift Azubi")
    if signature_paths.get('azubi') and os.path.exists(signature_paths['azubi']):
        pdf.image(signature_paths['azubi'], x=15, y=start_y+10, w=80, h=30)
        
    # Examiner Signature
    pdf.set_xy(110, start_y)
    pdf.cell(90, 40, "", 1) # Box
    pdf.text(112, start_y + 5, f"Unterschrift Prüfer")
    if signature_paths.get('examiner') and os.path.exists(signature_paths['examiner']):
        pdf.image(signature_paths['examiner'], x=115, y=start_y+10, w=80, h=30)
        
    pdf.output(output_path)
    return output_path
