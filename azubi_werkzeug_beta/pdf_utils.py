from fpdf import FPDF
import os
from datetime import datetime
from flask import current_app
from models import CheckType

# Logo path wird dynamisch über current_app.config geholt
def get_logo_path():
    """Get logo path from Flask app config (DATA_DIR)"""
    try:
        data_dir = current_app.config.get('DATA_DIR', os.path.dirname(__file__))
    except RuntimeError:
        # Fallback wenn außerhalb des App-Kontexts
        data_dir = os.environ.get('DATA_DIR', os.path.dirname(__file__))
    return os.path.join(data_dir, 'static', 'img', 'logo.png')

class HandoverReport(FPDF):
    def __init__(self, title="Werkzeug-Protokoll"):
        super().__init__()
        self.report_title = title
        self.set_auto_page_break(auto=True, margin=15)
        self.add_page()
        
    def header(self):
        # 1. Logo Einbindung (wenn vorhanden)
        logo_path = get_logo_path()
        if os.path.exists(logo_path):
            # x=10, y=8, w=30 (Breite 30mm, Höhe automatisch proportional)
            self.image(logo_path, 10, 8, 30)
            # Verschiebe den Titel nach rechts, damit er nicht im Logo steht
            self.set_x(45) 
        
        # 2. Titel
        self.set_font('Arial', 'B', 16)
        # Titelbreite 0 = bis zum rechten Rand
        self.cell(0, 10, self.report_title, 0, 1, 'R') 
        
        # Linie unter dem Header
        self.set_draw_color(200, 200, 200)
        self.line(10, 25, 200, 25)
        self.ln(20) # Abstand zum Inhalt (angepasst an Logo-Höhe)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128)
        # Use {nb} for total pages (requires alias_nb_pages() call)
        self.cell(0, 10, f'Seite {self.page_no()}/{{nb}}', 0, 0, 'C')

    def chapter_title(self, label):
        self.set_font('Arial', 'B', 11)
        self.set_fill_color(240, 240, 240) # Hellgrau
        self.set_text_color(0)
        self.cell(0, 8, label, 0, 1, 'L', 1) # Höhe reduziert auf 8
        self.ln(2) # Kleiner Abstand

def generate_handover_pdf(azubi_name, examiner_name, tools, check_type, signature_paths, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Titel Logik
    # Titel Logik
    type_map = {
        CheckType.ISSUE: 'Ausgabeprotokoll',
        CheckType.RETURN: 'Rückgabeprotokoll',
        CheckType.CHECK: 'Prüfprotokoll',
        CheckType.EXCHANGE: 'Austauschprotokoll'
    }
    title_text = type_map.get(check_type, 'Werkzeug-Protokoll')
    
    pdf = HandoverReport(title=title_text)
    pdf.alias_nb_pages()
    
    # --- KOMPAKTE METADATEN (NEBENEINANDER) ---
    pdf.set_y(30) # Startposition nach Header fixieren
    pdf.set_font('Arial', '', 10)
    
    # Zeilenhöhe 6mm statt 10mm
    h = 6 
    
    # Wir nutzen Cell mit ln=0 für Nebeneinander
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(20, h, "Datum:", 0, 0)
    pdf.set_font('Arial', '', 10)
    pdf.cell(40, h, datetime.now().strftime('%d.%m.%Y %H:%M'), 0, 0)
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(15, h, "Azubi:", 0, 0)
    pdf.set_font('Arial', '', 10)
    pdf.cell(50, h, azubi_name, 0, 0)
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(15, h, "Prüfer:", 0, 0)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, h, examiner_name, 0, 1) # ln=1 für Zeilenumbruch am Ende
    
    pdf.ln(5) # Kleiner Abstand zur Tabelle
    
    # --- TABELLE ---
    pdf.chapter_title(f"Betroffene Werkzeuge ({len(tools)} Stück)")
    
    # Tabellenkopf
    pdf.set_font('Arial', 'B', 9)
    pdf.set_fill_color(220, 220, 220)
    # Breiten optimiert: Name bekommt den meisten Platz
    w_name = 90
    w_cat = 50
    w_status = 50
    h_row = 7 # Reduzierte Zeilenhöhe (war 10)
    
    pdf.cell(w_name, h_row, "Werkzeugbezeichnung", 1, 0, 'L', True)
    pdf.cell(w_cat, h_row, "Kategorie", 1, 0, 'L', True)
    pdf.cell(w_status, h_row, "Zustand / Status", 1, 1, 'L', True)
    
    # Inhalt
    pdf.set_font('Arial', '', 9)
    
    for tool in tools:
        # Status Übersetzung
        status_map = {
            'ok': 'In Ordnung',
            'missing': 'Fehlt',
            'broken': 'Defekt',
            'not_issued': 'Nicht ausgegeben'
        }
        status_text = status_map.get(tool.get('status'), tool.get('status')) or ""
        
        # Kategorie Übersetzung
        cat_map = {
            'standard': 'Standard',
            'teilisoliert': 'Teilisoliert',
            'vollisoliert': 'Vollisoliert (1000V)',
            'isolierend': 'Vollkunststoff'
        }
        cat_text = cat_map.get(tool.get('category'), tool.get('category')) or ""

        # Name kürzen falls zu lang für eine Zeile
        name = (tool.get('name') or "")[:50] 
        
        # Farbliche Hervorhebung bei Problemen
        if tool['status'] in ['missing', 'broken']:
            pdf.set_text_color(200, 0, 0) # Rot
            pdf.set_font('Arial', 'B', 9)
        else:
            pdf.set_text_color(0)
            pdf.set_font('Arial', '', 9)

        pdf.cell(w_name, h_row, name, 1)
        pdf.cell(w_cat, h_row, cat_text, 1)
        pdf.cell(w_status, h_row, status_text, 1)
        pdf.ln()
        
    pdf.set_text_color(0) # Reset Farbe
    pdf.ln(10)
    
    # --- UNTERSCHRIFTEN ---
    # Prüfen, ob noch genug Platz auf der Seite ist (ca 50mm nötig), sonst neue Seite
    if pdf.get_y() > 230:
        pdf.add_page()
        
    pdf.chapter_title("Unterschriften")
    
    start_y = pdf.get_y()
    box_height = 35 # Etwas kompakter (war 40)
    
    # Box Azubi
    pdf.set_xy(10, start_y)
    pdf.rect(10, start_y, 90, box_height) # Rahmen zeichnen
    pdf.set_font('Arial', '', 8)
    pdf.text(12, start_y + 4, "Unterschrift Azubi")
    
    if signature_paths.get('azubi') and os.path.exists(signature_paths['azubi']):
        # Bild einpassen
        pdf.image(signature_paths['azubi'], x=15, y=start_y+5, w=60, h=25)
        
    # Box Prüfer
    pdf.set_xy(110, start_y)
    pdf.rect(110, start_y, 80, box_height)
    pdf.text(112, start_y + 4, "Unterschrift Prüfer")
    
    if signature_paths.get('examiner') and os.path.exists(signature_paths['examiner']):
        pdf.image(signature_paths['examiner'], x=115, y=start_y+5, w=60, h=25)
    
    # Rechtlicher Hinweis unten drunter (optional, aber professionell)
    pdf.set_xy(10, start_y + box_height + 2)
    pdf.set_font('Arial', 'I', 7)
    pdf.multi_cell(0, 3, "Mit der Unterschrift wird die Vollständigkeit (bei Ausgabe) bzw. der oben genannte Zustand (bei Prüfung/Rückgabe) bestätigt.")

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
    
    # --- Kopfdaten ---
    pdf.set_y(30)
    pdf.set_font('Arial', '', 10)
    h = 6
    
    # Matched Layout with HandoverReport
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(20, h, "Datum:", 0, 0)
    pdf.set_font('Arial', '', 10)
    pdf.cell(40, h, datetime.now().strftime('%d.%m.%Y'), 0, 0)

    pdf.set_font('Arial', 'B', 10)
    pdf.cell(15, h, "Azubi:", 0, 0)
    pdf.set_font('Arial', '', 10)
    pdf.cell(50, h, f"{azubi.name} (Lehrjahr: {azubi.lehrjahr})", 0, 1)
    
    pdf.ln(5)
    
    # --- Status Werkzeugrückgabe ---
    pdf.chapter_title("Status Werkzeugrückgabe")
    pdf.set_font('Arial', '', 10)
    
    if is_inventory_clear:
        pdf.set_text_color(0, 100, 0) # Dunkelgrün
        pdf.cell(0, 8, "[OK] Alle Werkzeuge wurden zurückgegeben.", 0, 1)
    else:
        pdf.set_text_color(200, 0, 0) # Rot
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 8, "[ACHTUNG] Es befinden sich noch Werkzeuge im Besitz!", 0, 1)
    
    pdf.set_text_color(0)
    pdf.set_font('Arial', '', 10)
    pdf.ln(5)
    
    # --- Historie Zusammenfassung ---
    pdf.chapter_title("Historie Zusammenfassung")
    
    # Tabellenkopf
    pdf.set_font('Arial', 'B', 9) 
    pdf.set_fill_color(220, 220, 220)
    h_row = 7
    
    # Breiten optimieren: Datum(25), Typ(25), Ausbilder(40), Werkzeug(100)
    pdf.cell(25, h_row, "Datum", 1, 0, 'L', True)
    pdf.cell(25, h_row, "Vorgang", 1, 0, 'L', True)
    pdf.cell(40, h_row, "Ausbilder", 1, 0, 'L', True)
    pdf.cell(100, h_row, "Werkzeug / Status", 1, 1, 'L', True)
    
    pdf.set_font('Arial', '', 9)
    
    # Type Mapping
    type_map = {
        CheckType.ISSUE: 'Ausgabe',
        CheckType.RETURN: 'Rückgabe',
        CheckType.CHECK: 'Prüfung'
    }
    
    for entry in history_entries:
        date_str = entry.datum.strftime('%d.%m.%Y')
        # Translate Link
        raw_type = entry.check_type or CheckType.CHECK
        type_str = type_map.get(raw_type, raw_type.capitalize())
        
        examiner = entry.examiner or "-"
        
        # Tool Name + Status
        tool_name = entry.werkzeug.name if entry.werkzeug else "Unbekannt"
        
        # Parse status from bemerkung
        status = ""
        if entry.bemerkung:
             parts = entry.bemerkung.split('|')
             for p in parts:
                 if "Status:" in p:
                     status = p.replace("Status:", "").strip()
                     break
        
        # Map common status codes to German
        status_map_display = {
            'ok': 'i.O.',
            'missing': 'Fehlt',
            'broken': 'Defekt',
            'not_issued': 'Nicht ausgegeben'
        }
        status_display = status_map_display.get(status, status)
        
        if status_display:
            details = f"{tool_name} ({status_display})"
        else:
            details = tool_name
        
        # Name kürzen falls nötig
        details = details[:55]
        
        # Conditional Color
        if status in ['missing', 'broken']:
            pdf.set_text_color(200, 0, 0)
            pdf.set_font('Arial', 'B', 9)
        else:
            pdf.set_text_color(0)
            pdf.set_font('Arial', '', 9)

        pdf.cell(25, h_row, date_str, 1)
        pdf.cell(25, h_row, type_str, 1)
        pdf.cell(40, h_row, examiner[:20], 1)
        pdf.cell(100, h_row, details, 1)
        pdf.ln()

    # Reset Color
    pdf.set_text_color(0)
    pdf.set_font('Arial', '', 10)

    # --- Signatures ---
    # Check page break
    if pdf.get_y() > 230:
        pdf.add_page()
        
    pdf.ln(10)
    pdf.chapter_title("Bestätigung")
    
    pdf.set_font('Arial', '', 10)
    pdf.multi_cell(0, 5, "Hiermit wird die Kenntnisnahme des oben genannten Status sowie die ordnungsgemäße Abwicklung zum Ausbildungsende bestätigt.")
    pdf.ln(10)
    
    start_y = pdf.get_y()
    box_height = 35
    
    # Box Azubi
    pdf.set_xy(10, start_y)
    pdf.rect(10, start_y, 90, box_height)
    pdf.set_font('Arial', '', 8)
    pdf.text(12, start_y + 4, "Unterschrift Azubi")
    
    # Box Ausbilder
    pdf.set_xy(110, start_y)
    pdf.rect(110, start_y, 80, box_height)
    pdf.text(112, start_y + 4, "Unterschrift Ausbilder / Verantwortlicher")
    
    return pdf
