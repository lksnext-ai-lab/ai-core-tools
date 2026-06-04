"""add platform_role to user

Revision ID: platform_role001
Revises: spoint001
Create Date: 2026-06-03
"""
from alembic import op
import sqlalchemy as sa


revision = 'platform_role001'
down_revision = 'spoint001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'User',
        sa.Column('platform_role', sa.String(50), nullable=False, server_default='editor')
    )
    # Align DB-level default with application intent after backfill
    op.alter_column('User', 'platform_role', server_default='viewer')


def downgrade():
    op.drop_column('User', 'platform_role')
