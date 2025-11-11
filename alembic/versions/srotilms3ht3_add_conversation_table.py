"""add_conversation_table

Revision ID: srotilms3ht3
Revises: lcpcww5nvhwp
Create Date: 2025-11-09

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'srotilms3ht3'
down_revision = 'lcpcww5nvhwp'
branch_labels = None
depends_on = None


def upgrade():
    # Create Conversation table
    op.create_table(
        'Conversation',
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=True),
        sa.Column('session_id', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('last_message', sa.Text(), nullable=True),
        sa.Column('message_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('api_key_hash', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['Agent.agent_id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['User.user_id'], ),
        sa.PrimaryKeyConstraint('conversation_id'),
        sa.UniqueConstraint('session_id')
    )
    
    # Create indexes for better query performance
    op.create_index('idx_conversation_agent_user', 'Conversation', ['agent_id', 'user_id'])
    op.create_index('idx_conversation_agent_api', 'Conversation', ['agent_id', 'api_key_hash'])
    op.create_index('idx_conversation_updated_at', 'Conversation', ['updated_at'])


def downgrade():
    # Drop indexes
    op.drop_index('idx_conversation_updated_at', table_name='Conversation')
    op.drop_index('idx_conversation_agent_api', table_name='Conversation')
    op.drop_index('idx_conversation_agent_user', table_name='Conversation')
    
    # Drop table
    op.drop_table('Conversation')

