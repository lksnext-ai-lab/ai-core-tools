"""richer agent metrics: llm_calls, time_to_first_token_ms, provider, BUILTIN tools

Revision ID: metrics003
Revises: metrics002
Create Date: 2026-09-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'metrics003'
down_revision = 'metrics002'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('agent_execution_event', sa.Column('llm_calls', sa.Integer(), nullable=True))
    op.add_column('agent_execution_event', sa.Column('time_to_first_token_ms', sa.Integer(), nullable=True))
    op.add_column('agent_execution_event', sa.Column('provider', sa.String(45), nullable=True))
    # System-wide dashboards filter on the time range alone.
    op.create_index('ix_aee_started', 'agent_execution_event', [sa.text('started_at DESC')])
    # Platform tools (sandbox, skills, file helpers) were previously unclassified.
    op.execute("ALTER TYPE agent_tool_call_type ADD VALUE IF NOT EXISTS 'BUILTIN'")


def downgrade():
    # PostgreSQL cannot drop an enum value; 'BUILTIN' stays in agent_tool_call_type (harmless).
    op.execute("DELETE FROM agent_tool_call WHERE tool_type = 'BUILTIN'")
    op.drop_index('ix_aee_started', table_name='agent_execution_event')
    op.drop_column('agent_execution_event', 'provider')
    op.drop_column('agent_execution_event', 'time_to_first_token_ms')
    op.drop_column('agent_execution_event', 'llm_calls')
