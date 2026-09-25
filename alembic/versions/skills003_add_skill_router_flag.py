"""add skill_router_enabled flag to Agent

Revision ID: skills003
Revises: skills002
Create Date: 2026-09-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'skills003'
down_revision = 'skills002'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'Agent',
        sa.Column('skill_router_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column('Agent', 'skill_router_enabled')
