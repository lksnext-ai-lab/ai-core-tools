"""add_auth_fields_to_mcp_config

Revision ID: 6eddec222813
Revises: 7001831172b8
Create Date: 2025-10-28 14:50:17.917141

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6eddec222813'
down_revision = '7001831172b8'
branch_labels = None
depends_on = None


def upgrade():
    # Add authentication-related fields to MCPConfig table
    op.add_column('MCPConfig', sa.Column('requires_auth', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('MCPConfig', sa.Column('auth_type', sa.String(50), nullable=True, server_default='bearer'))


def downgrade():
    # Remove authentication-related fields from MCPConfig table
    op.drop_column('MCPConfig', 'auth_type')
    op.drop_column('MCPConfig', 'requires_auth')
