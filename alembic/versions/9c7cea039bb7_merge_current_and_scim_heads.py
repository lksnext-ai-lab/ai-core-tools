"""merge current and SCIM heads

Revision ID: 9c7cea039bb7
Revises: 0cfc09dbc8df, scim002
Create Date: 2026-11-24 12:39:17.317569

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9c7cea039bb7'
down_revision = ('0cfc09dbc8df', 'scim002')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
