"""
PDF Generation Utilities for Azubi Werkzeug Tracker.

Handles creation of:
- Handover protocols (Issue, Return, Check, Exchange)
- End of Training reports
- QR Code sheets
"""
import os
import tempfile
from datetime import datetime
import qrcode
from fpdf import FPDF
from flask import current_app
from models import CheckType

# Logo path wird dynamisch über current_app.config geholt


def get_logo_path():
    """Get logo path from Flask app config (DATA_DIR)."""
    try:
        data_dir = current_app.config.get(
            'DATA_DIR', os.path.dirname(__file__))
    except RuntimeError:
        # Fallback wenn außerhalb des App-Kontexts
        data_dir = os.environ.get('DATA_DIR', os.path.dirname(__file__))
    return os.path.join(data_dir, 'static', 'img', 'logo.png')


def parse_check_type(value):
    """
    Safely parses a check type from string or Enum.

    Returns the CheckType enum member or None.
    """
    if isinstance(value, CheckType):
        return value

    if not value:
        return CheckType.CHECK  # Default

    try:
        # Try exact match (e.g. 'issue' -> CheckType.ISSUE)
        return CheckType(value)
    except ValueError:
        # Try case-insensitive lookup
        val_lower = str(value).lower()
        for member in CheckType:
            if member.value.lower() == val_lower:
                return member

        current_app.logger.warning(
            f"Unknown CheckType: {value}, defaulting to CHECK")
        return CheckType.CHECK


class HandoverReport(FPDF):
    """Custom FPDF class for Werkzeug reports with consistent Header/Footer."""

    def __init__(self, title="Werkzeug-Protokoll"):
        """Initialize the report."""
        super().__init__()
        self.report_title = title
        self.set_auto_page_break(auto=True, margin=15)
        self.add_page()

    def header(self):
        """Header of the report."""
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
        self.ln(20)  # Abstand zum Inhalt (angepasst an Logo-Höhe)

    def footer(self):
        """Footer of the report."""
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128)
        # Use {nb} for total pages (requires alias_nb_pages() call)
        self.cell(0, 10, f'Seite {self.page_no()}/{{nb}}', 0, 0, 'C')

    def chapter_title(self, label):
        """Add a standardized chapter title to the PDF."""
        self.set_font('Arial', 'B', 11)
        self.set_fill_color(240, 240, 240)  # Hellgrau
        self.set_text_color(0)
        self.cell(0, 8, label, 0, 1, 'L', 1)  # Höhe reduziert auf 8
        self.ln(2)  # Kleiner Abstand


# Shared status/category maps
_STATUS_MAP = {
    'ok': 'In Ordnung', 'missing': 'Fehlt',
    'broken': 'Defekt', 'not_issued': 'Nicht ausgegeben'
}
_CAT_MAP = {
    'standard': 'Std', 'spezial': 'Spez',
    'psa': 'PSA', 'elektro': 'Elektro'
}
_BAD_STATUSES = ('missing', 'broken', 'defekt', 'fehlt', 'verloren')

_TYPE_MAP = {
    CheckType.ISSUE: 'Ausgabeprotokoll',
    CheckType.RETURN: 'Rückgabeprotokoll',
    CheckType.CHECK: 'Prüfprotokoll',
    CheckType.EXCHANGE: 'Austauschprotokoll'
}


# pylint: disable=too-many-arguments,too-many-positional-arguments
def _render_tool_row(pdf, tool, w_name, w_cat, w_status, h_row):
    """Render a single tool row in a PDF table."""
    status_text = _STATUS_MAP.get(
        tool.get('status'), tool.get('status')) or ""
    if tool.get('incident_reason'):
        status_text += f" ({tool.get('incident_reason')})"

    category = tool.get('category') or 'standard'
    cat_text = _CAT_MAP.get(category, category) or "Std"
    name = (tool.get('name') or "")[:50]

    s_check = str(tool['status']).lower()
    if any(x in s_check for x in _BAD_STATUSES):
        pdf.set_text_color(200, 0, 0)
        pdf.set_font('Arial', 'B', 9)
    else:
        pdf.set_text_color(0)
        pdf.set_font('Arial', '', 9)

    pdf.cell(w_name, h_row, name, 1)
    pdf.cell(w_cat, h_row, cat_text, 1)
    pdf.cell(w_status, h_row, status_text, 1)
    pdf.ln()


def _render_signature_boxes(pdf, signature_paths):
    """Render signature boxes (Azubi + Examiner) on the PDF."""
    if pdf.get_y() > 230:
        pdf.add_page()

    pdf.chapter_title("Unterschriften")
    start_y = pdf.get_y()
    box_height = 35

    # Box Azubi
    pdf.set_xy(10, start_y)
    pdf.rect(10, start_y, 90, box_height)
    pdf.set_font('Arial', '', 8)
    pdf.text(12, start_y + 4, "Unterschrift Azubi")
    if signature_paths.get('azubi') and os.path.exists(
            signature_paths['azubi']):
        pdf.image(signature_paths['azubi'], x=15, y=start_y + 5, w=60, h=25)

    # Box Prüfer
    pdf.set_xy(110, start_y)
    pdf.rect(110, start_y, 80, box_height)
    pdf.text(112, start_y + 4, "Unterschrift Prüfer")
    if signature_paths.get('examiner') and os.path.exists(
            signature_paths['examiner']):
        pdf.image(
            signature_paths['examiner'], x=115, y=start_y + 5, w=60, h=25)

    return start_y, box_height


def _render_handover_table(pdf, tools, title_text):
    """Render the tool table for handover reports."""
    pdf.chapter_title(f"Betroffene Werkzeuge ({len(tools)} Stück)")
    pdf.set_font('Arial', 'B', 9)
    pdf.set_fill_color(220, 220, 220)
    w_name, w_cat, w_status, h_row = 90, 50, 50, 7
    pdf.cell(w_name, h_row, "Werkzeugbezeichnung", 1, 0, 'L', True)
    pdf.cell(w_cat, h_row, "Kategorie", 1, 0, 'L', True)
    pdf.cell(w_status, h_row, "Zustand / Status", 1, 1, 'L', True)

    for tool in tools:
        if not tool.get('name'):
            current_app.logger.warning(
                f"PDF Gen: Tool name missing in {title_text}")
        _render_tool_row(pdf, tool, w_name, w_cat, w_status, h_row)

    pdf.set_text_color(0)
    pdf.ln(10)


# pylint: disable=too-many-locals
def generate_handover_pdf(
    azubi_name, examiner_name, tools, check_type, signature_paths, output_path,
    extra_lines=None
):
    """
    Generate a PDF report for tool handover/check/exchange.

    # pylint: disable=too-many-arguments,too-many-positional-arguments


    Args:
        azubi_name (str): Name of the apprentice.
        examiner_name (str): Name of the examiner.
        tools (list): List of tool dictionaries.
        check_type (CheckType): generic or specific check type.
        signature_paths (dict): Paths to signature images.
        output_path (str): Destination path for the PDF.

    Returns:
        str: The output path of the generated PDF.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    c_type_enum = parse_check_type(check_type)
    title_text = _TYPE_MAP.get(c_type_enum, 'Werkzeug-Protokoll')

    pdf = HandoverReport(title=title_text)
    pdf.alias_nb_pages()

    # --- Metadata ---
    pdf.set_y(30)
    h = 6
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
    pdf.cell(0, h, examiner_name, 0, 1)
    pdf.ln(5)

    pdf.ln(5)

    # --- Tool Table ---
    _render_handover_table(pdf, tools, title_text)

    # --- Extra Lines (e.g. Price) ---
    if extra_lines:
        pdf.set_font('Arial', 'B', 10)
        for line in extra_lines:
            # Fix: Replace € with EUR to prevent encoding errors in standard fonts
            safe_line = line.replace('€', 'EUR')
            pdf.cell(0, 6, safe_line, 0, 1, 'R')
        pdf.ln(5)

    # --- Signatures ---
    start_y, box_height = _render_signature_boxes(pdf, signature_paths)

    pdf.set_xy(10, start_y + box_height + 2)
    pdf.set_font('Arial', 'I', 7)
    disclaimer = (
        "Mit der Unterschrift wird die Vollständigkeit (bei Ausgabe) "
        "bzw. der oben genannte Zustand (bei Prüfung/Rückgabe) bestätigt."
    )
    pdf.multi_cell(0, 3, disclaimer)

    pdf.output(output_path)
    return output_path


def generate_qr_codes_pdf(azubis):
    """
    Generate a PDF containing QR codes for the provided Azubis.

    Layout: Avery Zweckform B5274-50 (52x74mm, 4x4 grid)

    Args:
        azubis (list): List of Azubi objects (id, name, lehrjahr).

    Returns:
        FPDF: The generated PDF object (not saved to disk).
    """
    # pylint: disable=too-many-locals

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=0)  # Full control
    pdf.add_page()
    pdf.set_font("Arial", size=10)

    # Avery B5274-50 Layout Config (approximate for A4)
    # 4 columns, 4 rows = 16 labels per page
    # Label size: 52mm x 74mm
    # Home Assistant / Browser print margins can vary, so we use safe margins.

    # Layout definition
    margin_left = 6
    margin_top = 4.5
    col_width = 52.5  # Includes horizontal gap
    row_height = 74.0  # Includes vertical gap (0 usually)

    # Inner Label Bounds (printable area)
    label_w = 48
    # label_h = 70  # Unused

    # Grid state
    col = 0
    row = 0
    items_on_page = 0

    for azubi in azubis:
        # Calculate X/Y based on grid
        x = margin_left + (col * col_width)
        y = margin_top + (row * row_height)

        # Draw Label Boundary (Optional: Debugging, remove for final)
        # pdf.rect(x, y, label_w, label_h)

        # --- Content ---

        # QR Code
        qr_content = f"AZUBI:{azubi.id}"
        qr = qrcode.QRCode(box_size=10, border=1)
        qr.add_data(qr_content)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        temp_qr_path = os.path.join(tempfile.gettempdir(), f"qr_az_{azubi.id}.png")
        img.save(temp_qr_path)

        # QR Image Centered
        # Width 35mm
        qr_size = 35
        qr_x = x + (label_w - qr_size) / 2
        qr_y = y + 10  # 10mm defined space from top

        if os.path.exists(temp_qr_path):
            pdf.image(temp_qr_path, x=qr_x, y=qr_y, w=qr_size, h=qr_size)
            try:
                os.remove(temp_qr_path)
            except OSError:
                pass

        # Text below QR
        text_y_start = qr_y + qr_size + 5
        pdf.set_xy(x, text_y_start)
        pdf.set_font("Arial", 'B', 11)
        pdf.multi_cell(label_w, 5, azubi.name, align='C')

        pdf.set_xy(x, pdf.get_y() + 1)
        pdf.set_font("Arial", '', 9)
        pdf.cell(label_w, 5, f"Lehrjahr {azubi.lehrjahr}", 0, 1, 'C')

        # --- Grid Logic ---
        col += 1
        items_on_page += 1

        # New Row
        if col >= 4:
            col = 0
            row += 1

        # New Page
        if items_on_page >= 16:
            pdf.add_page()
            col = 0
            row = 0
            items_on_page = 0

    return pdf


# Status map for end-of-training report
_HIST_STATUS_MAP = {
    'ok': 'i.O.', 'missing': 'Fehlt',
    'broken': 'Defekt', 'not_issued': 'Nicht ausgegeben'
}


def _render_history_row(pdf, entry, type_map, h_row):
    """Render a single history row in the end-of-training report."""
    date_str = entry.datum.strftime('%d.%m.%Y')
    c_type_enum = parse_check_type(entry.check_type)
    type_str = type_map.get(c_type_enum, 'Prüfung')
    examiner = entry.examiner or "-"
    tool_name = entry.werkzeug.name if entry.werkzeug else "Unbekannt"

    # Parse status from bemerkung
    status = ""
    if entry.bemerkung:
        for p in entry.bemerkung.split('|'):
            if "Status:" in p:
                status = p.replace("Status:", "").strip()
                break

    status_display = _HIST_STATUS_MAP.get(status, status)
    details = f"{tool_name} ({status_display})" if status_display else tool_name
    details = details[:55]

    if status in ('missing', 'broken'):
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


def generate_end_of_training_report(
        azubi,
        history_entries,
        is_inventory_clear,
        output_path=None):
    """
    Generate a final report at the end of training.

    Summarizes the tool history and confirms inventory status.
    Args:
        azubi: The apprentice object.
        history_entries: A list of history entries.
        is_inventory_clear: Boolean indicating if inventory is clear.
        output_path: Path to save the PDF (optional).
    """
    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pdf = HandoverReport(title="Ausbildungs-Ende Protokoll")
    pdf.alias_nb_pages()

    # --- Kopfdaten ---
    _render_eot_header(pdf, azubi)

    # --- Status Werkzeugrückgabe ---
    _render_eot_status(pdf, is_inventory_clear)

    # --- Historie Zusammenfassung ---
    _render_eot_history(pdf, history_entries)

    # --- Signatures ---
    _render_eot_signatures(pdf)

    if output_path:
        pdf.output(output_path)
        return output_path

    return pdf


def _render_eot_header(pdf, azubi):
    """Render report header."""
    pdf.set_y(30)
    pdf.set_font('Arial', '', 10)
    h = 6

    pdf.set_font('Arial', 'B', 10)
    pdf.cell(20, h, "Datum:", 0, 0)
    pdf.set_font('Arial', '', 10)
    pdf.cell(40, h, datetime.now().strftime('%d.%m.%Y'), 0, 0)

    pdf.set_font('Arial', 'B', 10)
    pdf.cell(15, h, "Azubi:", 0, 0)
    pdf.set_font('Arial', '', 10)
    pdf.cell(50, h, f"{azubi.name} (Lehrjahr: {azubi.lehrjahr})", 0, 1)

    pdf.ln(5)


def _render_eot_status(pdf, is_inventory_clear):
    """Render inventory status section."""
    pdf.chapter_title("Status Werkzeugrückgabe")
    pdf.set_font('Arial', '', 10)

    if is_inventory_clear:
        pdf.set_text_color(0, 100, 0)  # Dunkelgrün
        pdf.cell(0, 8, "[OK] Alle Werkzeuge wurden zurückgegeben.", 0, 1)
    else:
        pdf.set_text_color(200, 0, 0)  # Rot
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(
            0,
            8,
            "[ACHTUNG] Es befinden sich noch Werkzeuge im Besitz!",
            0,
            1)

    pdf.set_text_color(0)
    pdf.set_font('Arial', '', 10)
    pdf.ln(5)


def _render_eot_history(pdf, history_entries):
    """Render check history table."""
    pdf.chapter_title("Historie Zusammenfassung")

    # Tabellenkopf
    pdf.set_font('Arial', 'B', 9)
    pdf.set_fill_color(220, 220, 220)
    h_row = 7

    pdf.cell(25, h_row, "Datum", 1, 0, 'L', True)
    pdf.cell(25, h_row, "Vorgang", 1, 0, 'L', True)
    pdf.cell(40, h_row, "Ausbilder", 1, 0, 'L', True)
    pdf.cell(100, h_row, "Werkzeug / Status", 1, 1, 'L', True)

    pdf.set_font('Arial', '', 9)

    _hist_type_map = {
        CheckType.ISSUE: 'Ausgabe',
        CheckType.RETURN: 'Rückgabe',
        CheckType.CHECK: 'Prüfung'
    }

    for entry in history_entries:
        _render_history_row(pdf, entry, _hist_type_map, h_row)

    pdf.set_text_color(0)
    pdf.set_font('Arial', '', 10)


def _render_eot_signatures(pdf):
    """Render end-of-training signatures."""
    if pdf.get_y() > 230:
        pdf.add_page()

    pdf.ln(10)
    pdf.chapter_title("Bestätigung")

    pdf.set_font('Arial', '', 10)
    text = (
        "Hiermit wird die Kenntnisnahme des oben genannten Status sowie "
        "die ordnungsgemäße Abwicklung zum Ausbildungsende bestätigt."
    )
    pdf.multi_cell(0, 5, text)
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
