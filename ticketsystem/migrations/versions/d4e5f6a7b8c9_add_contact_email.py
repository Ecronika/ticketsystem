"""Add contact_email to ticket

Revision ID: d4e5f6a7b8c9
Revises: b3c4d5e6f7a8
Branch Labels: None
Depends On: None

"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e5f6a7b8c9'
down_revision = 'b3c4d5e6f7a8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('ticket', schema=None) as batch_op:
        batch_op.add_column(sa.Column('contact_email', sa.String(length=150), nullable=True))


def downgrade():
    with op.batch_alter_table('ticket', schema=None) as batch_op:
        batch_op.drop_column('contact_email')
