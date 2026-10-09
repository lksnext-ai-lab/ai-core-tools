"""Add middleware_mcps join table.

Revision ID: mw002
Revises: mwrag001
Create Date: 2026-05-15
"""
from alembic import op
import sqlalchemy as sa

revision = 'mw002'
down_revision = 'mwrag001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'middleware_mcps',
        sa.Column('middleware_id', sa.Integer(), nullable=False),
        sa.Column('config_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['middleware_id'], ['Middleware.middleware_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['config_id'], ['MCPConfig.config_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('middleware_id', 'config_id'),
    )


def downgrade() -> None:
    op.drop_table('middleware_mcps')
