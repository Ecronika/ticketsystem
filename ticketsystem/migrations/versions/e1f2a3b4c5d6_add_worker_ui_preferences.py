"""Add ui_theme and email_notifications_enabled to Worker

Revision ID: e1f2a3b4c5d6
Revises: d4e5f6a7b8c9
Branch Labels: None
Depends On: None

"""
from alembic import op
import sqlalchemy as sa


revision = 'e1f2a3b4c5d6'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('worker', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ui_theme', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('email_notifications_enabled', sa.Boolean(), nullable=False, server_default='1'))


def downgrade():
    with op.batch_alter_table('worker', schema=None) as batch_op:
        batch_op.drop_column('email_notifications_enabled')
        batch_op.drop_column('ui_theme')
