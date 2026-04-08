"""Add checklist sort_order and fix template FK ondelete

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


def upgrade():
    # Add sort_order column to checklist_item for drag & drop reordering
    with op.batch_alter_table('checklist_item', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0')
        )

    # Fix the foreign key on ticket.checklist_template_id to SET NULL on delete
    with op.batch_alter_table('ticket', schema=None) as batch_op:
        batch_op.drop_constraint(
            'fk_ticket_checklist_template_id', type_='foreignkey'
        )
        batch_op.create_foreign_key(
            'fk_ticket_checklist_template_id',
            'checklist_template',
            ['checklist_template_id'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade():
    with op.batch_alter_table('ticket', schema=None) as batch_op:
        batch_op.drop_constraint(
            'fk_ticket_checklist_template_id', type_='foreignkey'
        )
        batch_op.create_foreign_key(
            'fk_ticket_checklist_template_id',
            'checklist_template',
            ['checklist_template_id'],
            ['id'],
        )

    with op.batch_alter_table('checklist_item', schema=None) as batch_op:
        batch_op.drop_column('sort_order')
