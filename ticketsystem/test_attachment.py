
import os
import sys
import base64

# Add the app directory to sys.path
sys.path.append(os.path.join(os.getcwd()))

from app import app
from extensions import db
from models import Ticket, Attachment
from enums import TicketPriority
from services.ticket_service import TicketService

with app.app_context():
    # Small red dot base64
    red_dot = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUAAAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO9TXL0Y4OHwAAAABJRU5ErkJggg=="
    
    print("Testing create_ticket with attachment...")
    try:
        ticket = TicketService.create_ticket(
            title="Diagnostic Ticket",
            description="Testing image processing",
            priority=TicketPriority.MITTEL,
            author_name="Diagnostic Script",
            image_base64=red_dot
        )
        print(f"Ticket created: ID {ticket.id}")
        
        attachments = Attachment.query.filter_by(ticket_id=ticket.id).all()
        print(f"Attachments in DB: {[a.filename for a in attachments]}")
        
        if attachments:
            path = os.path.join(app.config['DATA_DIR'], 'attachments', attachments[0].filename)
            print(f"Checking file at: {path}")
            if os.path.exists(path):
                print("File EXISTS on disk.")
            else:
                print("File MISSING on disk.")
        else:
            print("NO attachment created in DB.")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
