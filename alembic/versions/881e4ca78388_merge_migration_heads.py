"""merge migration heads

Revision ID: 881e4ca78388
Revises: 3e9d370bd29b, mcpservers001
Create Date: 2026-02-09 10:18:48.029661

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '881e4ca78388'
down_revision = ('3e9d370bd29b', 'mcpservers001')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
