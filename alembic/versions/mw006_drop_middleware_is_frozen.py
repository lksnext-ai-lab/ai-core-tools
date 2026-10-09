"""Drop Middleware.is_frozen: middlewares have no tier limit, so nothing ever froze them.

Revision ID: mw006
Revises: agentdel001
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa

revision = 'mw006'
down_revision = 'agentdel001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column('Middleware', 'is_frozen')


def downgrade() -> None:
    op.add_column(
        'Middleware',
        sa.Column('is_frozen', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
