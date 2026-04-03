"""v1.15.0 - Customer contact fields for Kundendienst quick-capture

Revision ID: b3c4d5e6f7a8
Revises: 9a531112_auto
Create Date: 2026-04-03 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3c4d5e6f7a8'
down_revision = '9a531112_auto'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('ticket', schema=None) as batch_op:
        batch_op.add_column(sa.Column('contact_name', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('contact_phone', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('contact_channel', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('callback_requested', sa.Boolean(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('callback_due', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('ticket', schema=None) as batch_op:
        batch_op.drop_column('callback_due')
        batch_op.drop_column('callback_requested')
        batch_op.drop_column('contact_channel')
        batch_op.drop_column('contact_phone')
        batch_op.drop_column('contact_name')
