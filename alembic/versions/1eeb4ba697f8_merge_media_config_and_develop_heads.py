"""merge media config and develop heads

Revision ID: 1eeb4ba697f8
Revises: ec5b82391242, mediaemb001
Create Date: 2026-09-07 14:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1eeb4ba697f8'
down_revision = ('ec5b82391242', 'mediaemb001')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
