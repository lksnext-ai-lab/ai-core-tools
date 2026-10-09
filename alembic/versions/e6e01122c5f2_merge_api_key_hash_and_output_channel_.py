"""merge API key hash and output channel heads

Revision ID: e6e01122c5f2
Revises: apikeyhash001, periodic008
Create Date: 2026-10-07 11:59:53.045343

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e6e01122c5f2'
down_revision = ('apikeyhash001', 'periodic008')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
