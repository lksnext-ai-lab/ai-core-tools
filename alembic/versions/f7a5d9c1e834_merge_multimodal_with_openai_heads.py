"""merge multimodal head (#146) with openai api / saas head

Revision ID: f7a5d9c1e834
Revises: 125b5f2e52be, 14b4c9c42164
Create Date: 2026-04-23 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f7a5d9c1e834'
down_revision = ('125b5f2e52be', '14b4c9c42164')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
