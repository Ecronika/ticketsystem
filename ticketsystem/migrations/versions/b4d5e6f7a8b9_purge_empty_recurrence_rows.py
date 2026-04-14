"""Purge ticket_recurrence rows with empty rule (legacy migration artefact).

The earlier extraction migration (e6f7a8b9c0d1) filtered the legacy
`ticket.recurrence_rule` column on `IS NOT NULL` only — but the form's
"Einmalig" option submits an empty string, which was stored verbatim in
the legacy column. Those empty-string rows were copied into
`ticket_recurrence` with `rule=''`, causing non-recurring tickets to
display the recurrence icon.

Revision ID: b4d5e6f7a8b9
Revises: a7b8c9d0e1f2
Create Date: 2026-04-14 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "b4d5e6f7a8b9"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def _table_exists(table_name):
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=:n"
    ), {"n": table_name})
    return result.first() is not None


def upgrade():
    if _table_exists("ticket_recurrence"):
        op.execute(
            "DELETE FROM ticket_recurrence "
            "WHERE rule IS NULL OR TRIM(rule) = ''"
        )


def downgrade():
    # Data cleanup — no reverse operation possible.
    pass
