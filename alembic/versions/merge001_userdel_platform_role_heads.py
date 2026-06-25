"""Merge the user-deletion and platform-role migration heads.

Both branches forked from spoint001:
  spoint001 -> localauth001 -> userdel001            (feat/local-auth-mode)
  spoint001 -> platform_role001 -> platform_role002  (develop / roles PR #172)

This is a no-op merge revision that unifies the two heads so there is a single
linear head again. No schema changes.

Revision ID: merge001_userdel_platform_role
Revises: userdel001, platform_role002
Create Date: 2026-06-05
"""

# revision identifiers, used by Alembic.
revision = 'merge001_userdel_platform_role'
down_revision = ('userdel001',)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
