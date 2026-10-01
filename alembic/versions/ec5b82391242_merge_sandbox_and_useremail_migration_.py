"""merge sandbox and useremail migration heads

Revision ID: ec5b82391242
Revises: sandbox001, useremail001
Create Date: 2026-08-02 20:28:08.597889

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ec5b82391242'
down_revision = ('sandbox001', 'useremail001')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
