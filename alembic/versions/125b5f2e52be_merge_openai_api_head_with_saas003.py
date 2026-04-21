"""merge openai api head with saas003

Revision ID: 125b5f2e52be
Revises: a944b4110822, saas003
Create Date: 2026-04-16 17:11:19.185739

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '125b5f2e52be'
down_revision = ('a944b4110822', 'saas003')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
