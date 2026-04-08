"""Add checklist sort_order column

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-08 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def _column_exists(table_name, column_name):
    """Check if a column already exists (SQLite-compatible)."""
    bind = op.get_bind()
    result = bind.execute(sa.text(f"PRAGMA table_info({table_name})"))
    columns = [row[1] for row in result]
    return column_name in columns


def upgrade():
    # Add sort_order column to checklist_item for drag & drop reordering.
    # Guard against the column already existing (e.g. from db.create_all).
    if not _column_exists('checklist_item', 'sort_order'):
        with op.batch_alter_table('checklist_item', schema=None) as batch_op:
            batch_op.add_column(
                sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0')
            )

    # Note: The FK ondelete="SET NULL" for ticket.checklist_template_id is
    # enforced at the application level in _delete_template() which nullifies
    # references before deletion.  The model definition includes the correct
    # ondelete for any fresh db.create_all() invocations.


def downgrade():
    if _column_exists('checklist_item', 'sort_order'):
        with op.batch_alter_table('checklist_item', schema=None) as batch_op:
            batch_op.drop_column('sort_order')
