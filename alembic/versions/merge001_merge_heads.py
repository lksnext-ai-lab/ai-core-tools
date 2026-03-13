"""merge heads: 08001655fb7e and onboard001

Revision ID: merge001
Revises: 08001655fb7e, onboard001
Create Date: 2026-03-13 09:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'merge001'
down_revision = ('08001655fb7e', 'onboard001')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
