"""merge middlewares and conversation starters heads

Revision ID: a7171bf8edb1
Revises: mw004, 20260717_conversation_starters
Create Date: 2026-07-28 12:02:11.072928

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7171bf8edb1'
down_revision = ('mw004', '20260717_conversation_starters')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
