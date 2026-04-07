"""add A2A auth config to agent extension table

Revision ID: a2a003
Revises: a2a002
Create Date: 2026-03-31 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a2a003'
down_revision = 'a2a002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('A2AAgent', sa.Column('auth_config', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('A2AAgent', 'auth_config')
