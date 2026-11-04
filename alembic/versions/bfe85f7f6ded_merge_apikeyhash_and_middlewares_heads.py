"""merge apikeyhash and middlewares heads

Revision ID: bfe85f7f6ded
Revises: 178a5f35e5a7, apikeyhash001
Create Date: 2026-09-30 12:49:12.638148

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bfe85f7f6ded'
down_revision = ('178a5f35e5a7', 'apikeyhash001')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
