"""Merge the middlewares branch (mw007) with develop's scheduled-task output channels (output001_output_channels).

No schema changes: output001 only touches the scheduled task and output delivery tables,
which the middlewares branch does not modify.

Revision ID: mw008
Revises: mw007, output001_output_channels
Create Date: 2026-10-14
"""

revision = 'mw008'
down_revision = ('mw007', 'output001_output_channels')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
