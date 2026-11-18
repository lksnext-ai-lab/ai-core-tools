"""Add middlewares and agent_middlewares tables.

Revision ID: mw001
Revises: platform_role002
Create Date: 2026-05-13
"""
from alembic import op
import sqlalchemy as sa

revision = 'mw001'
down_revision = 'platform_role002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'Middleware',
        sa.Column('middleware_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('middleware_type', sa.String(), nullable=False),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('create_date', sa.DateTime(), nullable=True),
        sa.Column('update_date', sa.DateTime(), nullable=True),
        sa.Column('is_frozen', sa.Boolean(), nullable=True),
        sa.Column('app_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['app_id'], ['App.app_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('middleware_id'),
    )
    op.create_index(op.f('ix_Middleware_middleware_id'), 'Middleware', ['middleware_id'], unique=False)

    op.create_table(
        'agent_middlewares',
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('middleware_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['agent_id'], ['Agent.agent_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['middleware_id'], ['Middleware.middleware_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('agent_id', 'middleware_id'),
    )


def downgrade() -> None:
    op.drop_table('agent_middlewares')
    op.drop_index(op.f('ix_Middleware_middleware_id'), table_name='Middleware')
    op.drop_table('Middleware')
