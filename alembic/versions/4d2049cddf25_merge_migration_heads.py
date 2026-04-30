"""merge_migration_heads 

Revision ID: 4d2049cddf25
Revises: 08001655fb7e, d7a8c97d3c91
Create Date: 2026-03-11 10:17:30.163821

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4d2049cddf25'
down_revision = ('08001655fb7e', 'd7a8c97d3c91')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
