"""add recurrence is_active

Revision ID: 4f87fbd972e0
Revises: b4d5e6f7a8b9
Create Date: 2026-04-17 06:39:30.854049

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4f87fbd972e0'
down_revision = 'b4d5e6f7a8b9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("ticket_recurrence") as batch_op:
        batch_op.add_column(
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        )


def downgrade():
    with op.batch_alter_table("ticket_recurrence") as batch_op:
        batch_op.drop_column("is_active")
