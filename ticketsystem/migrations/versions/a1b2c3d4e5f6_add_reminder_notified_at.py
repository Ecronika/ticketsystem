"""add reminder_notified_at to ticket

Revision ID: a1b2c3d4e5f6
Revises: f2a3b4c5d6e7
Create Date: 2026-04-07 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'f2a3b4c5d6e7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('ticket', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reminder_notified_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('ticket', schema=None) as batch_op:
        batch_op.drop_column('reminder_notified_at')
