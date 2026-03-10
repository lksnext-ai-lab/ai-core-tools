"""add_avatar_path_to_user

Revision ID: a7f3c9d2b1e8
Revises: 08001655fb7e
Create Date: 2026-03-10 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7f3c9d2b1e8'
down_revision = '08001655fb7e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('User', sa.Column('avatar_path', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('User', 'avatar_path')
