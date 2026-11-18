"""merge sandbox and middlewares heads

Revision ID: 178a5f35e5a7
Revises: a7171bf8edb1, ec5b82391242
Create Date: 2026-08-21 08:52:44.039865

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '178a5f35e5a7'
down_revision = ('a7171bf8edb1', 'ec5b82391242')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
