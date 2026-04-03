"""Auto Repair Orphans

Revision ID: 9a531112
Revises: 079270ff0a87
Create Date: 2026-03-29 08:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9a531112'
down_revision = '1feee5a80ffa'
branch_labels = None
depends_on = None


def upgrade():
    # Automated Data Repair before enabling Foreign Key enforcement
    
    # 1. Repair orphaned Comment.author_id
    op.execute("UPDATE comment SET author_id = NULL WHERE author_id IS NOT NULL AND author_id NOT IN (SELECT id FROM worker)")
    
    # 2. Repair orphaned Ticket references
    op.execute("UPDATE ticket SET assigned_to_id = NULL WHERE assigned_to_id IS NOT NULL AND assigned_to_id NOT IN (SELECT id FROM worker)")
    op.execute("UPDATE ticket SET approved_by_id = NULL WHERE approved_by_id IS NOT NULL AND approved_by_id NOT IN (SELECT id FROM worker)")
    op.execute("UPDATE ticket SET rejected_by_id = NULL WHERE rejected_by_id IS NOT NULL AND rejected_by_id NOT IN (SELECT id FROM worker)")
    
    # 3. Repair orphaned ChecklistItem references
    op.execute("UPDATE checklist_item SET assigned_to_id = NULL WHERE assigned_to_id IS NOT NULL AND assigned_to_id NOT IN (SELECT id FROM worker)")
    op.execute("UPDATE checklist_item SET depends_on_item_id = NULL WHERE depends_on_item_id IS NOT NULL AND depends_on_item_id NOT IN (SELECT id FROM checklist_item)")
    
    # 4. Delete orphans for rigid constraints
    op.execute("DELETE FROM attachment WHERE ticket_id NOT IN (SELECT id FROM ticket)")
    op.execute("DELETE FROM notification WHERE user_id NOT IN (SELECT id FROM worker)")
    op.execute("DELETE FROM checklist_item WHERE ticket_id NOT IN (SELECT id FROM ticket)")
    op.execute("DELETE FROM ticket_tags WHERE ticket_id NOT IN (SELECT id FROM ticket) OR tag_id NOT IN (SELECT id FROM tag)")
    op.execute("DELETE FROM worker_team WHERE worker_id NOT IN (SELECT id FROM worker) OR team_id NOT IN (SELECT id FROM team)")


def downgrade():
    # No way to restore deleted orphaned data
    pass
