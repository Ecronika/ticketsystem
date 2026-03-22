
import os
import sys
import base64

# Add the app directory to sys.path
sys.path.append(os.path.join(os.getcwd()))

from app import app
from extensions import db
from models import Ticket, Attachment
from enums import TicketPriority

with app.app_context():
    ticket_id = 10
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket:
        print(f"Ticket {ticket_id} not found.")
        sys.exit(1)
        
    print(f"Adding manual attachment to Ticket {ticket_id} ({ticket.title})...")
    
    filename = "manual_test.png"
    attachment = Attachment(
        ticket_id=ticket.id,
        path=filename,
        filename=filename,
        mime_type="image/png"
    )
    db.session.add(attachment)
    db.session.commit()
    print("Attachment added to DB.")
