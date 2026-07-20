"""add SandboxService, Agent/App sandbox FKs, and Conversation sandbox state

Adds the generic sandbox code-execution configuration used by the provider
abstraction (OpenSandbox/Daytona/E2B):

- ``SandboxService`` table: per-app (or system-wide, ``app_id IS NULL``)
  sandbox provider credential configuration. Mirrors ``AIService``'s column
  set (``service_id``, ``name``, ``create_date``, ``endpoint``, ``api_key``,
  ``description``, ``api_version``, ``extra_config``) plus its own
  ``provider`` and ``app_id`` columns.
- ``Agent.sandbox_service_id``: optional agent-level ``SandboxService``
  override (``NULL`` = inherit from the app).
- ``App.default_sandbox_service_id``: optional app-level ``SandboxService``
  override (``NULL`` = inherit ``SANDBOX_DEFAULT_PROVIDER``).
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
    op.create_table(
        'SandboxService',
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('create_date', sa.DateTime(), nullable=True),
        sa.Column('endpoint', sa.String(length=255), nullable=True),
        sa.Column('api_key', sa.Text(), nullable=True),
        sa.Column('description', sa.String(length=1000), nullable=True),
        sa.Column('api_version', sa.String(length=50), nullable=True),
        sa.Column('extra_config', sa.Text(), nullable=True),
        sa.Column('provider', sa.String(length=45), nullable=False),
        sa.Column('app_id', sa.Integer(), nullable=True),  # NULL = system/platform-wide
        sa.ForeignKeyConstraint(['app_id'], ['App.app_id']),
        sa.PrimaryKeyConstraint('service_id'),
    )
    op.create_index(op.f('ix_SandboxService_service_id'), 'SandboxService', ['service_id'], unique=False)

    op.add_column('Agent', sa.Column('sandbox_service_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'Agent_sandbox_service_id_fkey',
        'Agent', 'SandboxService', ['sandbox_service_id'], ['service_id'],
        ondelete='SET NULL',
    )

    op.add_column('App', sa.Column('default_sandbox_service_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'App_default_sandbox_service_id_fkey',
        'App', 'SandboxService', ['default_sandbox_service_id'], ['service_id'],
        ondelete='SET NULL',
    )

    op.add_column('Conversation', sa.Column('sandbox_session_id', sa.String(length=255), nullable=True))
    op.add_column('Conversation', sa.Column('sandbox_state', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('Conversation', 'sandbox_state')
    op.drop_column('Conversation', 'sandbox_session_id')

    op.drop_constraint('App_default_sandbox_service_id_fkey', 'App', type_='foreignkey')
    op.drop_column('App', 'default_sandbox_service_id')

    op.drop_constraint('Agent_sandbox_service_id_fkey', 'Agent', type_='foreignkey')
    op.drop_column('Agent', 'sandbox_service_id')

    op.drop_index(op.f('ix_SandboxService_service_id'), table_name='SandboxService')
    op.drop_table('SandboxService')
