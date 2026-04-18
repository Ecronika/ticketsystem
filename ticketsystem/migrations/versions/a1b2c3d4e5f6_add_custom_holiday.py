"""Add custom_holiday table for company-specific holidays.

Revision ID: a1b2c3d4e5f6
Revises: 4f87fbd972e0
Branch Labels: None
Depends On: None
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = '4f87fbd972e0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'custom_holiday',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('label', sa.String(100), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('date'),
    )


def downgrade():
    op.drop_table('custom_holiday')
