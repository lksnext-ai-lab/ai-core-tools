"""agent metrics tables (agent_execution_event, agent_tool_call) in core

Revision ID: metrics002
Revises: skills003
Create Date: 2026-09-25 00:00:00.000000

Agent metrics used to ship as the mattin-metrics plugin, which created these
tables through its own Alembic chain (version table ``alembic_version_metrics``).
Databases that ran the plugin already have the tables, so creation is skipped
when they exist and the plugin's version table is dropped.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'metrics002'
down_revision = 'skills003'
branch_labels = None
depends_on = None

ENUM_TYPES = [
    ('agent_execution_caller_type', ['INTERNAL_PLAYGROUND', 'PUBLIC_API', 'MCP', 'AGENT_AS_TOOL']),
    ('agent_execution_status', ['SUCCESS', 'ERROR', 'TIMEOUT']),
    ('agent_tool_call_type', ['AGENT', 'MCP', 'RETRIEVER']),
    ('agent_tool_call_status', ['SUCCESS', 'ERROR']),
]


def _enum(name):
    values = dict(ENUM_TYPES)[name]
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade():
    bind = op.get_bind()
    for name, values in ENUM_TYPES:
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    existing_tables = set(sa.inspect(bind).get_table_names())

    if 'agent_execution_event' not in existing_tables:
        op.create_table(
            'agent_execution_event',
            sa.Column('event_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('app_id', sa.Integer(), nullable=False),
            sa.Column('agent_id', sa.Integer(), nullable=False),
            sa.Column('conversation_id', sa.Integer(), nullable=True),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('api_key_id', sa.Integer(), nullable=True),
            sa.Column('caller_type', _enum('agent_execution_caller_type'), nullable=False),
            sa.Column('parent_execution_id', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('started_at', sa.DateTime(), nullable=False),
            sa.Column('finished_at', sa.DateTime(), nullable=True),
            sa.Column('duration_ms', sa.Integer(), nullable=True),
            sa.Column('status', _enum('agent_execution_status'), nullable=False),
            sa.Column('error_code', sa.String(64), nullable=True),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('model_name', sa.String(255), nullable=True),
            sa.Column('ai_service_id', sa.Integer(), nullable=True),
            sa.Column('input_tokens', sa.Integer(), nullable=True),
            sa.Column('output_tokens', sa.Integer(), nullable=True),
            sa.Column('total_tokens', sa.Integer(), nullable=True),
            sa.Column('tool_calls', sa.JSON(), nullable=True),
            sa.Column('retrieved_docs', sa.JSON(), nullable=True),
            sa.Column('had_files', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('file_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('had_images', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('output_parser_used', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('parser_succeeded', sa.Boolean(), nullable=True),
            sa.Column('prompt_chars', sa.Integer(), nullable=True),
            sa.Column('response_chars', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['app_id'], ['App.app_id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['agent_id'], ['Agent.agent_id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['conversation_id'], ['Conversation.conversation_id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['user_id'], ['User.user_id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['api_key_id'], ['APIKey.key_id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['ai_service_id'], ['AIService.service_id'], ondelete='SET NULL'),
        )
        op.create_index('ix_aee_app_started', 'agent_execution_event', ['app_id', sa.text('started_at DESC')])
        op.create_index('ix_aee_agent_started', 'agent_execution_event', ['agent_id', sa.text('started_at DESC')])
        op.create_index('ix_aee_parent', 'agent_execution_event', ['parent_execution_id'])
        op.create_index(
            'ix_aee_status_started', 'agent_execution_event', ['app_id', 'status', sa.text('started_at DESC')]
        )

    if 'agent_tool_call' not in existing_tables:
        op.create_table(
            'agent_tool_call',
            sa.Column('tool_call_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('event_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('tool_name', sa.String(255), nullable=False),
            sa.Column('tool_type', _enum('agent_tool_call_type'), nullable=False),
            sa.Column('sub_agent_id', sa.Integer(), nullable=True),
            sa.Column('mcp_config_id', sa.Integer(), nullable=True),
            sa.Column('duration_ms', sa.Integer(), nullable=True),
            sa.Column('status', _enum('agent_tool_call_status'), nullable=False),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('started_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['event_id'], ['agent_execution_event.event_id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['sub_agent_id'], ['Agent.agent_id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['mcp_config_id'], ['MCPConfig.config_id'], ondelete='SET NULL'),
        )
        op.create_index('ix_atc_event', 'agent_tool_call', ['event_id'])
        op.create_index('ix_atc_tool_name', 'agent_tool_call', ['tool_name'])

    # The plugin created a self-referencing FK on parent_execution_id. A
    # sub-agent's event is written before its parent's, so it must go.
    for fk in sa.inspect(bind).get_foreign_keys('agent_execution_event'):
        if fk['constrained_columns'] == ['parent_execution_id'] and fk.get('name'):
            op.drop_constraint(fk['name'], 'agent_execution_event', type_='foreignkey')

    op.execute('DROP TABLE IF EXISTS alembic_version_metrics')


def downgrade():
    op.drop_table('agent_tool_call')
    op.drop_table('agent_execution_event')
    bind = op.get_bind()
    for name, _ in reversed(ENUM_TYPES):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
