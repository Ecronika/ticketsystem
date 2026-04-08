"""Add push_notifications_enabled to Worker

Revision ID: c2d3e4f5a6b7
Revises: b2c3d4e5f6a7
Branch Labels: None
Depends On: None

"""
from alembic import op
import sqlalchemy as sa


revision = 'c2d3e4f5a6b7'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('worker', schema=None) as batch_op:
        batch_op.add_column(sa.Column('push_notifications_enabled', sa.Boolean(), nullable=False, server_default='1'))


def downgrade():
    with op.batch_alter_table('worker', schema=None) as batch_op:
        batch_op.drop_column('push_notifications_enabled')
