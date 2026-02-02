"""add MCP servers feature

Revision ID: mcpservers001
Revises: a35f5996ece4
Create Date: 2025-11-15

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'mcpservers001'
down_revision = 'a35f5996ece4'
branch_labels = None
depends_on = None


def upgrade():
    # Add slug column to App table (nullable initially for existing apps)
    op.add_column('App', sa.Column('slug', sa.String(100), nullable=True))
    op.create_index('ix_app_slug', 'App', ['slug'], unique=True)

    # Create MCPServer table
    op.create_table(
        'MCPServer',
        sa.Column('server_id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False),
        sa.Column('description', sa.String(1000), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('rate_limit', sa.Integer(), server_default='0', nullable=False),
        sa.Column('create_date', sa.DateTime(), nullable=True),
        sa.Column('update_date', sa.DateTime(), nullable=True),
        sa.Column('app_id', sa.Integer(), sa.ForeignKey('App.app_id', ondelete='CASCADE'), nullable=False),
    )

    # Create unique constraint on (app_id, slug) for MCPServer
    op.create_unique_constraint('uq_mcp_server_app_slug', 'MCPServer', ['app_id', 'slug'])

    # Create mcp_server_agents association table
    op.create_table(
        'mcp_server_agents',
        sa.Column('server_id', sa.Integer(), sa.ForeignKey('MCPServer.server_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('agent_id', sa.Integer(), sa.ForeignKey('Agent.agent_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('tool_name_override', sa.String(100), nullable=True),
        sa.Column('tool_description_override', sa.String(1000), nullable=True),
    )


def downgrade():
    # Drop mcp_server_agents table
    op.drop_table('mcp_server_agents')

    # Drop MCPServer unique constraint and table
    op.drop_constraint('uq_mcp_server_app_slug', 'MCPServer', type_='unique')
    op.drop_table('MCPServer')

    # Drop App slug column
    op.drop_index('ix_app_slug', 'App')
    op.drop_column('App', 'slug')
