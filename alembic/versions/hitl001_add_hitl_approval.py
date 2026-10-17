"""Add hitl_approval: lifecycle, owner and expiry of human-in-the-loop pauses.

Revision ID: hitl001
Revises: mw005
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa

revision = 'hitl001'
down_revision = 'mw005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'hitl_approval',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('app_id', sa.Integer(), sa.ForeignKey('App.app_id', ondelete='CASCADE'), nullable=False),
        sa.Column('agent_id', sa.Integer(), sa.ForeignKey('Agent.agent_id', ondelete='CASCADE'), nullable=False),
        sa.Column(
            'conversation_id', sa.Integer(),
            sa.ForeignKey('Conversation.conversation_id', ondelete='CASCADE'), nullable=False,
        ),
        sa.Column('thread_id', sa.String(255), nullable=False),
        sa.Column('interrupt_id', sa.String(64), nullable=False),
        sa.Column('channel', sa.String(32), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('actions', sa.JSON(), nullable=False),
        sa.Column('decisions', sa.JSON(), nullable=True),
        sa.Column(
            'requested_by_user_id', sa.Integer(), sa.ForeignKey('User.user_id', ondelete='SET NULL'), nullable=True,
        ),
        sa.Column('requested_by_api_key_hash', sa.String(64), nullable=True),
        sa.Column(
            'decided_by_user_id', sa.Integer(), sa.ForeignKey('User.user_id', ondelete='SET NULL'), nullable=True,
        ),
        sa.Column('decided_by_api_key_hash', sa.String(64), nullable=True),
        sa.Column('resolution_reason', sa.String(64), nullable=True),
        sa.Column('last_error', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_hitl_approval_app_id', 'hitl_approval', ['app_id'])
    op.create_index('ix_hitl_approval_agent_id', 'hitl_approval', ['agent_id'])
    op.create_index('ix_hitl_approval_conversation_id', 'hitl_approval', ['conversation_id'])
    op.create_index(
        'ix_hitl_approval_pending_expires_at', 'hitl_approval', ['expires_at'],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        'uq_hitl_approval_pending_conversation', 'hitl_approval', ['conversation_id'], unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index('uq_hitl_approval_pending_conversation', table_name='hitl_approval')
    op.drop_index('ix_hitl_approval_pending_expires_at', table_name='hitl_approval')
    op.drop_index('ix_hitl_approval_conversation_id', table_name='hitl_approval')
    op.drop_index('ix_hitl_approval_agent_id', table_name='hitl_approval')
    op.drop_index('ix_hitl_approval_app_id', table_name='hitl_approval')
    op.drop_table('hitl_approval')
