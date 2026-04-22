"""merge_feature_and_saas_branches

Revision ID: 14b4c9c42164
Revises: a3f1b9c2d4e7, saas003
Create Date: 2026-04-14 11:01:20.242974

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '14b4c9c42164'
down_revision = ('a3f1b9c2d4e7', 'saas003')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
