"""worker email + ticket last_escalated_at

Revision ID: c1d2e3f4a5b6
Revises: b3c4d5e6f7a8
Create Date: 2026-04-04 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'c1d2e3f4a5b6'
down_revision = 'b3c4d5e6f7a8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('worker', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email', sa.String(length=120), nullable=True))

    with op.batch_alter_table('ticket', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_escalated_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('ticket', schema=None) as batch_op:
        batch_op.drop_column('last_escalated_at')

    with op.batch_alter_table('worker', schema=None) as batch_op:
        batch_op.drop_column('email')
