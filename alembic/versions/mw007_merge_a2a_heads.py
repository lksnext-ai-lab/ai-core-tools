"""Merge the middlewares branch (mw006) with develop's A2A agent server (a2a001_agent_server).

No schema changes: the two branches touch different tables. a2a_context_link's foreign keys
to Agent and Conversation are ON DELETE CASCADE, so they follow agentdel001's cascade.

Revision ID: mw007
Revises: mw006, a2a001_agent_server
Create Date: 2026-10-09
"""

revision = 'mw007'
down_revision = ('mw006', 'a2a001_agent_server')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
