"""conversation_starters

Revision ID: 20260717_conversation_starters
Revises: bedrock001
Create Date: 2026-07-17 09:45:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260717_conversation_starters'
down_revision = 'bedrock001' 
internal_branch = None
branches = []

def upgrade():
    op.create_table(
        'ConversationStarter',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('profile_id', sa.Integer(), nullable=False),
        sa.Column('prompt', sa.String(500), nullable=False),
        sa.Column('order', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['profile_id'], ['AgentMarketplaceProfile.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_conversation_starter_profile_id', 'ConversationStarter', ['profile_id'], unique=False)

def downgrade():
    op.drop_index('ix_conversation_starter_profile_id', table_name='ConversationStarter')
    op.drop_table('ConversationStarter')
