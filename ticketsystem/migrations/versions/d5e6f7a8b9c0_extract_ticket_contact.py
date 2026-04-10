"""Extract contact fields from ticket into ticket_contact table.

Revision ID: d5e6f7a8b9c0
Revises: c2d3e4f5a6b7
Create Date: 2026-04-09 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5e6f7a8b9c0'
down_revision = 'c2d3e4f5a6b7'
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
    # Guard: db.create_all() may have already created ticket_contact
    if not _table_exists('ticket_contact'):
        op.create_table(
            'ticket_contact',
            sa.Column('ticket_id', sa.Integer(),
                      sa.ForeignKey('ticket.id', ondelete='CASCADE'),
                      primary_key=True),
            sa.Column('name', sa.String(length=100), nullable=True),
            sa.Column('phone', sa.String(length=50), nullable=True),
            sa.Column('email', sa.String(length=150), nullable=True),
            sa.Column('channel', sa.String(length=20), nullable=True),
            sa.Column('callback_requested', sa.Boolean(),
                      server_default='0', nullable=False),
            sa.Column('callback_due', sa.DateTime(), nullable=True),
        )

    # Copy data only if old columns still exist on ticket
    if _column_exists('ticket', 'contact_name'):
        # Populate ticket_contact for tickets that don't have a row yet
        op.execute("""
            INSERT OR IGNORE INTO ticket_contact
                (ticket_id, name, phone, email, channel,
                 callback_requested, callback_due)
            SELECT id, contact_name, contact_phone, contact_email,
                   contact_channel, callback_requested, callback_due
            FROM ticket
        """)

        # Drop the old columns (batch mode for SQLite compat)
        with op.batch_alter_table('ticket', schema=None) as batch_op:
            batch_op.drop_column('contact_name')
            batch_op.drop_column('contact_phone')
            batch_op.drop_column('contact_email')
            batch_op.drop_column('contact_channel')
            batch_op.drop_column('callback_requested')
            batch_op.drop_column('callback_due')


def downgrade():
    # Re-add columns to ticket
    with op.batch_alter_table('ticket', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('contact_name', sa.String(length=100), nullable=True))
        batch_op.add_column(
            sa.Column('contact_phone', sa.String(length=50), nullable=True))
        batch_op.add_column(
            sa.Column('contact_email', sa.String(length=150), nullable=True))
        batch_op.add_column(
            sa.Column('contact_channel', sa.String(length=20), nullable=True))
        batch_op.add_column(
            sa.Column('callback_requested', sa.Boolean(),
                      server_default='0', nullable=False))
        batch_op.add_column(
            sa.Column('callback_due', sa.DateTime(), nullable=True))

    # Copy data back
    op.execute("""
        UPDATE ticket SET
            contact_name = (
                SELECT name FROM ticket_contact
                WHERE ticket_contact.ticket_id = ticket.id),
            contact_phone = (
                SELECT phone FROM ticket_contact
                WHERE ticket_contact.ticket_id = ticket.id),
            contact_email = (
                SELECT email FROM ticket_contact
                WHERE ticket_contact.ticket_id = ticket.id),
            contact_channel = (
                SELECT channel FROM ticket_contact
                WHERE ticket_contact.ticket_id = ticket.id),
            callback_requested = (
                SELECT callback_requested FROM ticket_contact
                WHERE ticket_contact.ticket_id = ticket.id),
            callback_due = (
                SELECT callback_due FROM ticket_contact
                WHERE ticket_contact.ticket_id = ticket.id)
    """)

    # Drop ticket_contact table
    op.drop_table('ticket_contact')
