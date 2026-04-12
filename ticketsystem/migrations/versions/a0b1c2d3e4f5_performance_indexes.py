"""performance indexes

Revision ID: a0b1c2d3e4f5
Revises: e6f7a8b9c0d1
Create Date: 2026-04-12

"""
from alembic import op

revision = 'a0b1c2d3e4f5'
down_revision = 'e6f7a8b9c0d1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ticket: häufigste Filter-Spalten
    op.create_index('ix_ticket_status', 'ticket', ['status'])
    op.create_index('ix_ticket_is_deleted', 'ticket', ['is_deleted'])
    # Komposit-Index für den häufigsten kombinierten Filter (is_deleted + status)
    op.create_index('ix_ticket_is_deleted_status', 'ticket', ['is_deleted', 'status'])
    op.create_index('ix_ticket_assigned_to_id', 'ticket', ['assigned_to_id'])
    op.create_index('ix_ticket_assigned_team_id', 'ticket', ['assigned_team_id'])
    op.create_index('ix_ticket_due_date', 'ticket', ['due_date'])
    op.create_index('ix_ticket_created_at', 'ticket', ['created_at'])
    # Comment: ticket_id-Subqueries in Suche und Vertraulichkeits-Filter
    op.create_index('ix_comment_ticket_id', 'comment', ['ticket_id'])
    # Notification: User-spezifische Abfragen
    op.create_index('ix_notification_user_id', 'notification', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_notification_user_id', table_name='notification')
    op.drop_index('ix_comment_ticket_id', table_name='comment')
    op.drop_index('ix_ticket_created_at', table_name='ticket')
    op.drop_index('ix_ticket_due_date', table_name='ticket')
    op.drop_index('ix_ticket_assigned_team_id', table_name='ticket')
    op.drop_index('ix_ticket_assigned_to_id', table_name='ticket')
    op.drop_index('ix_ticket_is_deleted_status', table_name='ticket')
    op.drop_index('ix_ticket_is_deleted', table_name='ticket')
    op.drop_index('ix_ticket_status', table_name='ticket')
