from app import app, db
from models import Attachment, Ticket
import os

with app.app_context():
    count = Attachment.query.count()
    print(f"Total Attachments: {count}")
    attachments = Attachment.query.all()
    for a in attachments:
        print(f"ID: {a.id}, Ticket: {a.ticket_id}, Filename: {a.filename}, Path: {a.path}")
        
    # Check if files exist on disk
    data_dir = app.config.get('DATA_DIR', '/data')
    attachments_dir = os.path.join(data_dir, 'attachments')
    if os.path.exists(attachments_dir):
        print(f"\nFiles in {attachments_dir}:")
        print(os.listdir(attachments_dir))
    else:
        print(f"\nDirectory {attachments_dir} does not exist.")
