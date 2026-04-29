"""add remote A2A task continuity fields to conversation

Revision ID: a2a004
Revises: a2a003
Create Date: 2026-04-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a2a004'
down_revision = 'a2a003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('Conversation', sa.Column('a2a_remote_task_id', sa.String(length=255), nullable=True))
    op.add_column('Conversation', sa.Column('a2a_remote_context_id', sa.String(length=255), nullable=True))
    op.add_column('Conversation', sa.Column('a2a_remote_task_state', sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column('Conversation', 'a2a_remote_task_state')
    op.drop_column('Conversation', 'a2a_remote_context_id')
    op.drop_column('Conversation', 'a2a_remote_task_id')
