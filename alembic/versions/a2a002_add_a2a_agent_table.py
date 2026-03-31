"""add A2A agent extension table

Revision ID: a2a002
Revises: saas003
Create Date: 2026-03-31 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a2a002'
down_revision = 'saas003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'A2AAgent',
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('card_url', sa.String(length=2048), nullable=False),
        sa.Column('remote_agent_id', sa.String(length=512), nullable=True),
        sa.Column('remote_skill_id', sa.String(length=255), nullable=False),
        sa.Column('remote_skill_name', sa.String(length=255), nullable=False),
        sa.Column('remote_agent_metadata', sa.JSON(), nullable=False),
        sa.Column('remote_skill_metadata', sa.JSON(), nullable=False),
        sa.Column('sync_status', sa.String(length=32), nullable=False),
        sa.Column('health_status', sa.String(length=32), nullable=False),
        sa.Column('last_successful_refresh_at', sa.DateTime(), nullable=True),
        sa.Column('last_refresh_attempt_at', sa.DateTime(), nullable=True),
        sa.Column('last_refresh_error', sa.Text(), nullable=True),
        sa.Column('documentation_url', sa.String(length=2048), nullable=True),
        sa.Column('icon_url', sa.String(length=2048), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['agent_id'], ['Agent.agent_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('agent_id'),
    )


def downgrade() -> None:
    op.drop_table('A2AAgent')
