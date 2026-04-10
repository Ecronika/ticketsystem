"""Extract approval/recurrence into satellite tables, due_date to DATE.

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-04-10 05:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e6f7a8b9c0d1'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


def _table_exists(name):
    """Check if a table exists (SQLite-compatible)."""
    bind = op.get_bind()
    result = bind.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
        {"n": name},
    )
    return result.fetchone() is not None


def _column_exists(table_name, column_name):
    """Check if a column exists (SQLite-compatible)."""
    bind = op.get_bind()
    result = bind.execute(sa.text(f"PRAGMA table_info({table_name})"))
    return column_name in [row[1] for row in result]


def upgrade():
    # --- ticket_approval ---
    if not _table_exists('ticket_approval'):
        op.create_table(
            'ticket_approval',
            sa.Column('ticket_id', sa.Integer(),
                      sa.ForeignKey('ticket.id', ondelete='CASCADE'),
                      primary_key=True),
            sa.Column('status', sa.String(length=20),
                      server_default='none', nullable=False),
            sa.Column('approved_by_id', sa.Integer(),
                      sa.ForeignKey('worker.id'), nullable=True),
            sa.Column('approved_at', sa.DateTime(), nullable=True),
            sa.Column('rejected_by_id', sa.Integer(),
                      sa.ForeignKey('worker.id'), nullable=True),
            sa.Column('reject_reason', sa.Text(), nullable=True),
        )

    if _column_exists('ticket', 'approval_status'):
        # Populate ticket_approval for tickets that have a non-default status
        op.execute("""
            INSERT OR IGNORE INTO ticket_approval
                (ticket_id, status, approved_by_id, approved_at,
                 rejected_by_id, reject_reason)
            SELECT id, approval_status, approved_by_id, approved_at,
                   rejected_by_id, reject_reason
            FROM ticket
            WHERE approval_status != 'none'
        """)

        with op.batch_alter_table('ticket', schema=None) as batch_op:
            batch_op.drop_column('approval_status')
            batch_op.drop_column('approved_by_id')
            batch_op.drop_column('approved_at')
            batch_op.drop_column('rejected_by_id')
            batch_op.drop_column('reject_reason')

    # --- ticket_recurrence ---
    if not _table_exists('ticket_recurrence'):
        op.create_table(
            'ticket_recurrence',
            sa.Column('ticket_id', sa.Integer(),
                      sa.ForeignKey('ticket.id', ondelete='CASCADE'),
                      primary_key=True),
            sa.Column('rule', sa.String(length=50), nullable=False),
            sa.Column('next_date', sa.DateTime(), nullable=True),
        )

    if _column_exists('ticket', 'recurrence_rule'):
        op.execute("""
            INSERT OR IGNORE INTO ticket_recurrence
                (ticket_id, rule, next_date)
            SELECT id, recurrence_rule, next_recurrence_date
            FROM ticket
            WHERE recurrence_rule IS NOT NULL
        """)

        with op.batch_alter_table('ticket', schema=None) as batch_op:
            batch_op.drop_column('recurrence_rule')
            batch_op.drop_column('next_recurrence_date')

    # --- due_date: DateTime -> Date (SQLite treats these identically,
    #     but the column affinity changes for documentation) ---
    # SQLite does not enforce column types, so no actual ALTER needed.
    # New rows written via the ORM will use date objects.


def downgrade():
    # Re-add recurrence columns
    with op.batch_alter_table('ticket', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('recurrence_rule', sa.String(length=50), nullable=True))
        batch_op.add_column(
            sa.Column('next_recurrence_date', sa.DateTime(), nullable=True))

    op.execute("""
        UPDATE ticket SET
            recurrence_rule = (
                SELECT rule FROM ticket_recurrence
                WHERE ticket_recurrence.ticket_id = ticket.id),
            next_recurrence_date = (
                SELECT next_date FROM ticket_recurrence
                WHERE ticket_recurrence.ticket_id = ticket.id)
    """)
    op.drop_table('ticket_recurrence')

    # Re-add approval columns
    with op.batch_alter_table('ticket', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('approval_status', sa.String(length=20),
                      server_default='none', nullable=False))
        batch_op.add_column(
            sa.Column('approved_by_id', sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column('approved_at', sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column('rejected_by_id', sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column('reject_reason', sa.Text(), nullable=True))

    op.execute("""
        UPDATE ticket SET
            approval_status = (
                SELECT status FROM ticket_approval
                WHERE ticket_approval.ticket_id = ticket.id),
            approved_by_id = (
                SELECT approved_by_id FROM ticket_approval
                WHERE ticket_approval.ticket_id = ticket.id),
            approved_at = (
                SELECT approved_at FROM ticket_approval
                WHERE ticket_approval.ticket_id = ticket.id),
            rejected_by_id = (
                SELECT rejected_by_id FROM ticket_approval
                WHERE ticket_approval.ticket_id = ticket.id),
            reject_reason = (
                SELECT reject_reason FROM ticket_approval
                WHERE ticket_approval.ticket_id = ticket.id)
    """)
    op.drop_table('ticket_approval')
