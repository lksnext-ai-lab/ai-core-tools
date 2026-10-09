"""merge A2A agent server and output channel heads

Revision ID: merge002_a2a_output
Revises: a2a001_agent_server, e6e01122c5f2
Create Date: 2026-10-09

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'merge002_a2a_output'
down_revision = ('a2a001_agent_server', 'e6e01122c5f2')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
