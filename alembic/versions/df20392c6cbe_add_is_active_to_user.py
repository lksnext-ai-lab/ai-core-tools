"""add_is_active_to_user

Revision ID: df20392c6cbe
Revises: 3328c4012e93
Create Date: 2025-10-27 15:22:19.996348

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'df20392c6cbe'
down_revision = '3328c4012e93'
branch_labels = None
depends_on = None


def upgrade():
    # Add is_active column with default True
    op.add_column('User', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))


def downgrade():
    # Remove is_active column
    op.drop_column('User', 'is_active')
