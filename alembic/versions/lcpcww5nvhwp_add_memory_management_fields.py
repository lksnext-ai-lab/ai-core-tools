"""add memory management fields to agent

Revision ID: lcpcww5nvhwp
Revises: df20392c6cbe
Create Date: 2025-11-09

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'lcpcww5nvhwp'
down_revision = '42c2b73b86da'
branch_labels = None
depends_on = None


def upgrade():
    # Add memory management configuration fields to Agent table
    op.add_column('Agent', sa.Column('memory_max_messages', sa.Integer(), nullable=False, server_default='20'))
    op.add_column('Agent', sa.Column('memory_max_tokens', sa.Integer(), nullable=True, server_default='4000'))
    op.add_column('Agent', sa.Column('memory_summarize_threshold', sa.Integer(), nullable=False, server_default='10'))


def downgrade():
    # Remove memory management configuration fields
    op.drop_column('Agent', 'memory_summarize_threshold')
    op.drop_column('Agent', 'memory_max_tokens')
    op.drop_column('Agent', 'memory_max_messages')

