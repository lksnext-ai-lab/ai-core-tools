"""add a2a agent fields and persisted task table

Revision ID: a2a001
Revises: saas003
Create Date: 2026-04-09 13:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a2a001'
down_revision = 'saas003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('Agent', sa.Column('a2a_enabled', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('Agent', sa.Column('a2a_name_override', sa.String(length=255), nullable=True))
    op.add_column('Agent', sa.Column('a2a_description_override', sa.Text(), nullable=True))
    op.add_column('Agent', sa.Column('a2a_skill_tags', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column('Agent', sa.Column('a2a_examples', sa.JSON(), nullable=False, server_default='[]'))

    op.create_table(
        'A2ATask',
        sa.Column('task_id', sa.String(length=255), nullable=False),
        sa.Column('context_id', sa.String(length=255), nullable=False),
        sa.Column('app_id', sa.Integer(), nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('api_key_id', sa.Integer(), nullable=True),
        sa.Column('conversation_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=64), nullable=False),
        sa.Column('task_payload', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['agent_id'], ['Agent.agent_id']),
        sa.ForeignKeyConstraint(['api_key_id'], ['APIKey.key_id']),
        sa.ForeignKeyConstraint(['app_id'], ['App.app_id']),
        sa.ForeignKeyConstraint(['conversation_id'], ['Conversation.conversation_id']),
        sa.PrimaryKeyConstraint('task_id')
    )
    op.create_index(op.f('ix_A2ATask_agent_id'), 'A2ATask', ['agent_id'], unique=False)
    op.create_index(op.f('ix_A2ATask_api_key_id'), 'A2ATask', ['api_key_id'], unique=False)
    op.create_index(op.f('ix_A2ATask_app_id'), 'A2ATask', ['app_id'], unique=False)
    op.create_index(op.f('ix_A2ATask_context_id'), 'A2ATask', ['context_id'], unique=False)
    op.create_index(op.f('ix_A2ATask_conversation_id'), 'A2ATask', ['conversation_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_A2ATask_conversation_id'), table_name='A2ATask')
    op.drop_index(op.f('ix_A2ATask_context_id'), table_name='A2ATask')
    op.drop_index(op.f('ix_A2ATask_app_id'), table_name='A2ATask')
    op.drop_index(op.f('ix_A2ATask_api_key_id'), table_name='A2ATask')
    op.drop_index(op.f('ix_A2ATask_agent_id'), table_name='A2ATask')
    op.drop_table('A2ATask')

    op.drop_column('Agent', 'a2a_examples')
    op.drop_column('Agent', 'a2a_skill_tags')
    op.drop_column('Agent', 'a2a_description_override')
    op.drop_column('Agent', 'a2a_name_override')
    op.drop_column('Agent', 'a2a_enabled')
