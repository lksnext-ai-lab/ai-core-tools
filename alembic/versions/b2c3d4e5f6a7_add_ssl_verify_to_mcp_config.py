"""add_ssl_verify_to_mcp_config

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-06 16:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('MCPConfig', sa.Column('ssl_verify', sa.Boolean(), nullable=False, server_default='true'))


def downgrade() -> None:
    op.drop_column('MCPConfig', 'ssl_verify')
