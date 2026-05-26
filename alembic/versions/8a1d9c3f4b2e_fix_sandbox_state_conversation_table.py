"""fix_sandbox_state_conversation_table

Revision ID: 8a1d9c3f4b2e
Revises: 1f4948188f41
Create Date: 2026-05-10 00:00:00.000000

"""
from typing import Any, Sequence, Union

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a1d9c3f4b2e'
down_revision: Union[str, None] = '1f4948188f41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE_NAME = 'Conversation'
_COLUMN_NAME = 'sandbox_state'


def _has_table(inspector: Any, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector: Any, table_name: str, column_name: str) -> bool:
    return any(column['name'] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if context.is_offline_mode():
        op.add_column(
            _TABLE_NAME,
            sa.Column(_COLUMN_NAME, sa.Text(), nullable=True),
        )
        return

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, _TABLE_NAME):
        raise RuntimeError(f"Expected table {_TABLE_NAME!r} to exist before applying migration {revision}")

    if not _has_column(inspector, _TABLE_NAME, _COLUMN_NAME):
        op.add_column(
            _TABLE_NAME,
            sa.Column(_COLUMN_NAME, sa.Text(), nullable=True),
        )


def downgrade() -> None:
    if context.is_offline_mode():
        op.drop_column(_TABLE_NAME, _COLUMN_NAME)
        return

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, _TABLE_NAME) and _has_column(inspector, _TABLE_NAME, _COLUMN_NAME):
        op.drop_column(_TABLE_NAME, _COLUMN_NAME)
