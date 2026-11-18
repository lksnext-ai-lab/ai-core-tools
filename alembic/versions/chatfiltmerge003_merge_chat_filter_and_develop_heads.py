"""Merge chat-filter branch with develop (agent last-used) migration heads

Revision ID: chatfiltmerge003
Revises: chatfiltmerge002, agentlast001
Create Date: 2026-11-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'chatfiltmerge003'
down_revision = ('chatfiltmerge002', 'agentlast001')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
