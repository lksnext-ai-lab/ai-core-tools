"""merge collabuni and silo indexing heads

Revision ID: 0cfc09dbc8df
Revises: collabuni001, siloidx001
Create Date: 2026-11-24 12:05:24.760840

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0cfc09dbc8df'
down_revision = ('collabuni001', 'siloidx001')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
