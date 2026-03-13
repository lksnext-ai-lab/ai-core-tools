"""add_onboarding_dismissed_to_app

Revision ID: onboard001
Revises: b2c3d4e5f6a7
Create Date: 2026-03-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'onboard001'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('App', sa.Column('onboarding_dismissed', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('App', 'onboarding_dismissed')
