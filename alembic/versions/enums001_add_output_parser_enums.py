"""add output parser enum support

Revision ID: enums001
Revises: ec5b82391242
Create Date: 2026-08-05 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'enums001'
down_revision = 'ec5b82391242'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'OutputParser',
        sa.Column('is_enum', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column('OutputParser', 'is_enum')
