"""public_api_phase_a

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
Create Date: 2026-04-12

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1c2d3e4f5a6'
down_revision = 'a0b1c2d3e4f5'
branch_labels = None
depends_on = None


def upgrade():
    # --- Neue Spalten auf ticket ---
    with op.batch_alter_table('ticket', schema=None) as batch_op:
        batch_op.add_column(sa.Column('external_call_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('external_metadata', sa.Text(), nullable=True))
        batch_op.create_index('ix_ticket_external_call_id', ['external_call_id'], unique=True)

    # --- api_key ---
    op.create_table(
        'api_key',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('key_prefix', sa.String(length=12), nullable=False),
        sa.Column('key_hash', sa.String(length=128), nullable=False),
        sa.Column('scopes', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('rate_limit_per_minute', sa.Integer(), nullable=False),
        sa.Column('expected_webhook_id', sa.String(length=128), nullable=True),
        sa.Column('default_assignee_worker_id', sa.Integer(), nullable=True),
        sa.Column('create_confidential_tickets', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by_worker_id', sa.Integer(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('last_used_ip', sa.String(length=45), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_by_worker_id', sa.Integer(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_worker_id'], ['worker.id']),
        sa.ForeignKeyConstraint(['default_assignee_worker_id'], ['worker.id']),
        sa.ForeignKeyConstraint(['revoked_by_worker_id'], ['worker.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key_hash'),
    )
    with op.batch_alter_table('api_key', schema=None) as batch_op:
        batch_op.create_index('ix_api_key_key_prefix', ['key_prefix'], unique=False)

    # --- api_key_ip_range ---
    op.create_table(
        'api_key_ip_range',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('api_key_id', sa.Integer(), nullable=False),
        sa.Column('cidr', sa.String(length=43), nullable=False),
        sa.Column('note', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by_worker_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['api_key_id'], ['api_key.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_worker_id'], ['worker.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('api_key_ip_range', schema=None) as batch_op:
        batch_op.create_index('ix_api_key_ip_range_api_key_id', ['api_key_id'], unique=False)

    # --- api_audit_log ---
    op.create_table(
        'api_audit_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('api_key_id', sa.Integer(), nullable=True),
        sa.Column('key_prefix', sa.String(length=12), nullable=True),
        sa.Column('source_ip', sa.String(length=45), nullable=False),
        sa.Column('method', sa.String(length=8), nullable=False),
        sa.Column('path', sa.String(length=255), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=False),
        sa.Column('latency_ms', sa.Integer(), nullable=False),
        sa.Column('outcome', sa.String(length=32), nullable=False),
        sa.Column('external_ref', sa.String(length=64), nullable=True),
        sa.Column('assignment_method', sa.String(length=24), nullable=True),
        sa.Column('request_id', sa.String(length=36), nullable=False),
        sa.Column('error_detail', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['api_key_id'], ['api_key.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('api_audit_log', schema=None) as batch_op:
        batch_op.create_index('ix_api_audit_log_timestamp', ['timestamp'], unique=False)
        batch_op.create_index('ix_api_audit_log_external_ref', ['external_ref'], unique=False)
        batch_op.create_index('ix_api_audit_log_api_key_id', ['api_key_id'], unique=False)

    # --- ticket_transcript ---
    op.create_table(
        'ticket_transcript',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticket_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['ticket_id'], ['ticket.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ticket_id', 'position', name='uq_transcript_ticket_position'),
    )
    with op.batch_alter_table('ticket_transcript', schema=None) as batch_op:
        batch_op.create_index('ix_ticket_transcript_ticket_id', ['ticket_id'], unique=False)


def downgrade():
    with op.batch_alter_table('ticket_transcript', schema=None) as batch_op:
        batch_op.drop_index('ix_ticket_transcript_ticket_id')
    op.drop_table('ticket_transcript')

    with op.batch_alter_table('api_audit_log', schema=None) as batch_op:
        batch_op.drop_index('ix_api_audit_log_api_key_id')
        batch_op.drop_index('ix_api_audit_log_external_ref')
        batch_op.drop_index('ix_api_audit_log_timestamp')
    op.drop_table('api_audit_log')

    with op.batch_alter_table('api_key_ip_range', schema=None) as batch_op:
        batch_op.drop_index('ix_api_key_ip_range_api_key_id')
    op.drop_table('api_key_ip_range')

    with op.batch_alter_table('api_key', schema=None) as batch_op:
        batch_op.drop_index('ix_api_key_key_prefix')
    op.drop_table('api_key')

    with op.batch_alter_table('ticket', schema=None) as batch_op:
        batch_op.drop_index('ix_ticket_external_call_id')
        batch_op.drop_column('external_call_id')
        batch_op.drop_column('external_metadata')
