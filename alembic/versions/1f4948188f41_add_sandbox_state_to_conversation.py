"""add_sandbox_state_to_conversation

Revision ID: 1f4948188f41
Revises: sandbox_it3_builtins
Create Date: 2025-05-10 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1f4948188f41'
down_revision: Union[str, None] = 'sandbox_it3_builtins'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'conversations',
        sa.Column('sandbox_state', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('conversations', 'sandbox_state')
