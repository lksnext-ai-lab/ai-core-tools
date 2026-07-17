"""add sandbox_provider to App and sandbox_session_id/sandbox_state to Conversation

Adds the generic sandbox code-execution configuration columns used by the
provider abstraction (subprocess/OpenSandbox/Daytona/E2B):

- ``App.sandbox_provider``: nullable override of the system-wide default
  sandbox provider (NULL = inherit ``SANDBOX_DEFAULT_PROVIDER``).
- ``Conversation.sandbox_session_id``: provider-assigned sandbox id, used to
  attempt reconnecting after a backend restart.
- ``Conversation.sandbox_state``: serialized JSON snapshot of sandbox session
  state (provider, session_key, sandbox_id, timestamps).

Revision ID: sandbox001
Revises: bedrock001
Create Date: 2026-07-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'sandbox001'
down_revision = 'bedrock001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('App', sa.Column('sandbox_provider', sa.String(length=50), nullable=True))
    op.add_column('Conversation', sa.Column('sandbox_session_id', sa.String(length=255), nullable=True))
    op.add_column('Conversation', sa.Column('sandbox_state', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('Conversation', 'sandbox_state')
    op.drop_column('Conversation', 'sandbox_session_id')
    op.drop_column('App', 'sandbox_provider')
