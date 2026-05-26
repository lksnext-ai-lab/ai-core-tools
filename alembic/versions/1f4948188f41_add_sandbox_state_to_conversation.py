"""add_sandbox_state_to_conversation

Revision ID: 1f4948188f41
Revises: sandbox_it3_builtins
Create Date: 2025-05-10 00:30:00.000000

"""
from typing import Any, Sequence, Union

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1f4948188f41'
down_revision: Union[str, None] = 'sandbox_it3_builtins'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE_NAME = 'conversations'
_COLUMN_NAME = 'sandbox_state'


def _has_table(inspector: Any, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector: Any, table_name: str, column_name: str) -> bool:
    return any(column['name'] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if context.is_offline_mode():
        return

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, _TABLE_NAME) and not _has_column(inspector, _TABLE_NAME, _COLUMN_NAME):
        op.add_column(
            _TABLE_NAME,
            sa.Column(_COLUMN_NAME, sa.Text(), nullable=True),
        )


def downgrade() -> None:
    if context.is_offline_mode():
        return

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, _TABLE_NAME) and _has_column(inspector, _TABLE_NAME, _COLUMN_NAME):
        op.drop_column(_TABLE_NAME, _COLUMN_NAME)
