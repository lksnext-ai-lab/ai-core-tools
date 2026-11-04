"""Delete an agent's conversations with it (Conversation.agent_id ON DELETE CASCADE).

``Conversation.agent_id`` had no ON DELETE action, so deleting any agent with
conversations made the ORM emit ``SET agent_id = NULL`` on a NOT NULL column and the
deletion failed. Hitl approvals, scheduled task runs and execution events already
follow the conversation (CASCADE / SET NULL).

Revision ID: agentdel001
Revises: hitl001
Create Date: 2026-10-09
"""
from alembic import op

revision = 'agentdel001'
down_revision = 'hitl001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint('Conversation_agent_id_fkey', 'Conversation', type_='foreignkey')
    op.create_foreign_key(
        'fk_conversation_agent_id_agent',
        'Conversation', 'Agent',
        ['agent_id'], ['agent_id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint('fk_conversation_agent_id_agent', 'Conversation', type_='foreignkey')
    op.create_foreign_key(
        'Conversation_agent_id_fkey',
        'Conversation', 'Agent',
        ['agent_id'], ['agent_id'],
    )
