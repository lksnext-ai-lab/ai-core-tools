"""rename platform_role omniadmin to admin

Revision ID: platform_role002
Revises: platform_role001
Create Date: 2026-06-04
"""
from alembic import op


revision = 'platform_role002'
down_revision = 'platform_role001'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE \"User\" SET platform_role = 'admin' WHERE platform_role = 'omniadmin'")


def downgrade():
    op.execute("UPDATE \"User\" SET platform_role = 'omniadmin' WHERE platform_role = 'admin'")
