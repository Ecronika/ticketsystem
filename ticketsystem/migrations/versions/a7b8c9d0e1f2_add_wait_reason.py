"""Add ticket.wait_reason column for WARTET sub-states.

Revision ID: a7b8c9d0e1f2
Revises: b1c2d3e4f5a6
Create Date: 2026-04-14 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "a7b8c9d0e1f2"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def _column_exists(table_name, column_name):
    bind = op.get_bind()
    result = bind.execute(sa.text(f"PRAGMA table_info({table_name})"))
    return column_name in [row[1] for row in result]


def upgrade():
    if not _column_exists("ticket", "wait_reason"):
        op.add_column(
            "ticket",
            sa.Column("wait_reason", sa.String(length=20), nullable=True),
        )


def downgrade():
    if _column_exists("ticket", "wait_reason"):
        with op.batch_alter_table("ticket") as batch:
            batch.drop_column("wait_reason")
