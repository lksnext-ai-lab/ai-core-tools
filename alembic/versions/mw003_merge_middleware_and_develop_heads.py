"""Merge the middlewares branch head with the develop head.

Two branches forked from platform_role002:
  platform_role002 -> ragcfg001 -> ... -> merge001_userdel_platform_role -> d3adbeef1234  (develop)
  platform_role002 -> mw001 -> mwrag001 -> mw002                                          (feature/middlewares)

This is a no-op merge revision that unifies the two heads so there is a single
linear head again. No schema changes.

Revision ID: mw003
Revises: mw002, d3adbeef1234
Create Date: 2026-07-13
"""

# revision identifiers, used by Alembic.
revision = 'mw003'
down_revision = ('mw002', 'd3adbeef1234')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
