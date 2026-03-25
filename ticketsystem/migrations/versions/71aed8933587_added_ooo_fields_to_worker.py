"""Added OOO fields to Worker

Revision ID: 71aed8933587
Revises: 175380aaff7c
Create Date: 2026-03-25 22:01:08.623426

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '71aed8933587'
down_revision = '175380aaff7c'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('worker', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_out_of_office', sa.Boolean(), nullable=True))
        
    with op.batch_alter_table('worker', schema=None) as batch_op:
        batch_op.add_column(sa.Column('delegate_to_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_worker_delegate', 'worker', ['delegate_to_id'], ['id'])


def downgrade():
    with op.batch_alter_table('worker', schema=None) as batch_op:
        batch_op.drop_constraint('fk_worker_delegate', type_='foreignkey')
        batch_op.drop_column('delegate_to_id')
        
    with op.batch_alter_table('worker', schema=None) as batch_op:
        batch_op.drop_column('is_out_of_office')
