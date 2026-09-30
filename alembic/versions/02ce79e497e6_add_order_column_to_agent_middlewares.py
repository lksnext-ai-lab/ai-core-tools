"""add order column to agent_middlewares

Revision ID: 02ce79e497e6
Revises: mw003
Create Date: 2026-07-16 14:26:40.144227

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '02ce79e497e6'
down_revision = 'mw003'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'agent_middlewares',
        sa.Column('order', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade():
    op.drop_column('agent_middlewares', 'order')
