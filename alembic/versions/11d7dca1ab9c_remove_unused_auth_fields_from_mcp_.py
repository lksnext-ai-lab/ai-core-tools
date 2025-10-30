"""remove_unused_auth_fields_from_mcp_config

Revision ID: 11d7dca1ab9c
Revises: 6eddec222813
Create Date: 2025-10-30 10:03:08.169716

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '11d7dca1ab9c'
down_revision = '6eddec222813'
branch_labels = None
depends_on = None


def upgrade():
    # Drop unused authentication columns from MCPConfig
    # These fields were never checked in the code - authentication is automatic when user has a token
    op.drop_column('MCPConfig', 'requires_auth')
    op.drop_column('MCPConfig', 'auth_type')


def downgrade():
    # Re-add the columns if needed (for rollback)
    op.add_column('MCPConfig', sa.Column('requires_auth', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('MCPConfig', sa.Column('auth_type', sa.String(), nullable=True, server_default='bearer'))
