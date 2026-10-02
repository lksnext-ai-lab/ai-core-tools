"""Conversation.agent_id FK: ON DELETE CASCADE.

Deleting an agent with conversations failed: the FK had no ON DELETE rule and
``agent_id`` is NOT NULL, so the ORM's ``UPDATE "Conversation" SET agent_id=NULL``
raised NotNullViolation. AgentService.delete_agent now purges the agent's
conversations (checkpoints, files, media) itself; this FK is the DB-level
backstop, paired with ``passive_deletes=True`` on the ``Agent.conversations`` backref.

Revision ID: convagent001
Revises: apikeyhash001
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa

revision = 'convagent001'
down_revision = 'apikeyhash001'
branch_labels = None
depends_on = None


def _agent_fk_name() -> str | None:
    for fk in sa.inspect(op.get_bind()).get_foreign_keys('Conversation'):
        if fk['referred_table'] == 'Agent' and fk['constrained_columns'] == ['agent_id']:
            return fk['name']
    return None


def upgrade() -> None:
    name = _agent_fk_name()
    if name:
        op.drop_constraint(name, 'Conversation', type_='foreignkey')
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
