"""Merge sandbox and SharePoint migration heads.

Revision ID: merge_sandbox_sharepoint_heads
Revises: 8a1d9c3f4b2e, spoint001
Create Date: 2026-05-25
"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "merge_sandbox_sharepoint_heads"
down_revision: Union[str, tuple[str, str], None] = (
    "8a1d9c3f4b2e",
    "spoint001",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op merge migration."""


def downgrade() -> None:
    """No-op merge migration."""
