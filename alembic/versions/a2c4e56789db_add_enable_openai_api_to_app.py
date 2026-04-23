"""Add enable_openai_api to App model

Revision ID: a2c4e56789db
Revises: srotilms3ht3
Create Date: 2026-03-19 23:42:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a2c4e56789db'
down_revision = 'srotilms3ht3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('App', sa.Column('enable_openai_api', sa.Boolean(), server_default='false', nullable=False))


def downgrade():
    op.drop_column('App', 'enable_openai_api')
