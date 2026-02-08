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

def generate_qr_codes_pdf(tools):
    import qrcode
    import tempfile
    
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=10)

    # Grid config (A4: 210mm wide)
    # 4 columns approx 50mm each
    col_width = 45
    row_height = 55
    margin_x = 10
    margin_y = 10
    
    x = margin_x
    y = margin_y
    
    tools_processed = 0
    
    for tool in tools:
        # Generate QR Code image
        qr = qrcode.QRCode(box_size=10, border=1)
        # Content: Simple string or URL. For now ID + Name
        qr.add_data(f"ID:{tool.id}\n{tool.name}")
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Save temp file
        temp_qr_path = os.path.join(tempfile.gettempdir(), f"qr_{tool.id}.png")
        img.save(temp_qr_path)
        
        # Draw Cell
        # Check page break
        if y + row_height > 280:
            pdf.add_page()
            x = margin_x
            y = margin_y
            
        pdf.rect(x, y, col_width, row_height)
        
        # Title
        pdf.set_xy(x, y + 2)
        pdf.set_font("Arial", 'B', 8)
        # Truncate name to avoid overflow
        name = tool.name[:40]
        pdf.multi_cell(col_width, 4, name, align='C')
        
        # QR Image
        # Center image: (45 - 35) / 2 = 5 padding
        if os.path.exists(temp_qr_path):
            pdf.image(temp_qr_path, x=x+5, y=y+12, w=35, h=35)
            try:
                os.remove(temp_qr_path) # Clean up
            except:
                pass
            
        # ID text
        pdf.set_xy(x, y + 48)
        pdf.set_font("Arial", '', 8)
        pdf.cell(col_width, 5, f"ID: {tool.id}", 0, 1, 'C')
        
        # Move Cursor
        x += col_width + 5
        tools_processed += 1
        
        # New Row
        if tools_processed % 4 == 0:
            x = margin_x
            y += row_height + 5
            # Reset X
            x = margin_x
            
    # Return PDF object (to be outputted by caller)
    return pdf

def generate_end_of_training_report(azubi, history_entries, is_inventory_clear):
    pdf = HandoverReport(title="Ausbildungs-Ende Protokoll")
    pdf.alias_nb_pages()
    
    # Azubi Details
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, f"Azubi: {azubi.name} (Lehrjahr: {azubi.lehrjahr})", 0, 1)
    pdf.set_font('Arial', '', 11)
    pdf.cell(0, 8, f"Datum Bericht: {datetime.now().strftime('%d.%m.%Y')}", 0, 1)
    
    # Inventory Status
    pdf.ln(5)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, "Status Werkzeugrückgabe:", 0, 1)
    
    pdf.set_font('Arial', '', 11)
    if is_inventory_clear:
        # Green-ish
        pdf.set_text_color(0, 100, 0)
        pdf.cell(0, 10, "[OK] Alle Werkzeuge wurden zurückgegeben.", 0, 1)
    else:
        # Red
        pdf.set_text_color(200, 0, 0)
        pdf.cell(0, 10, "[ACHTUNG] Es befinden sich noch Werkzeuge im Besitz!", 0, 1)
    pdf.set_text_color(0, 0, 0)
    
    # History Summary
    pdf.ln(10)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, "Historie Zusammenfassung:", 0, 1)
    
    # Table Header
    pdf.set_font('Arial', 'B', 10)
    pdf.set_fill_color(240, 240, 240)
    # Widths: Date(25), Type(25), Examiner(40), Tool/Status(100)
    pdf.cell(25, 8, "Datum", 1, 0, 'C', True)
    pdf.cell(25, 8, "Typ", 1, 0, 'C', True)
    pdf.cell(40, 8, "Prüfer", 1, 0, 'C', True)
    pdf.cell(100, 8, "Werkzeug / Status", 1, 1, 'L', True)
    
    pdf.set_font('Arial', '', 9)
    for entry in history_entries:
        date_str = entry.date.strftime('%d.%m.%Y')
        type_str = (entry.check_type or "CHECK").upper()
        examiner = entry.examiner_name or "-"
        
        # Tool Name + Status
        tool_name = entry.tool.name if entry.tool else "Unbekannt"
        status = entry.status
        details = f"{tool_name} ({status})"
        
        pdf.cell(25, 8, date_str, 1, 0, 'C')
        pdf.cell(25, 8, type_str, 1, 0, 'C')
        pdf.cell(40, 8, examiner[:20], 1, 0, 'C')
        pdf.cell(100, 8, details[:55], 1, 1, 'L')

    # Signatures
    pdf.ln(20)
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(0, 10, "Hiermit bestätige ich die ordnungsgemäße Rückgabe/Übernahme:", 0, 1)
    pdf.ln(15)
    
    y = pdf.get_y()
    pdf.line(10, y, 90, y)
    pdf.line(110, y, 190, y)
    
    pdf.cell(80, 5, "Unterschrift Azubi", 0, 0, 'C')
    pdf.cell(20, 5, "", 0, 0) # Gap
    pdf.cell(80, 5, "Unterschrift Ausbilder", 0, 1, 'C')

    return pdf
