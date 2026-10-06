"""add agent exposed chat filters column

Revision ID: chatfilt001
Revises: bedrock001
Create Date: 2026-07-16
"""
from alembic import op
import sqlalchemy as sa


revision = 'chatfilt001'
down_revision = 'bedrock001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('Agent', sa.Column('exposed_chat_filters', sa.JSON(), nullable=False, server_default='[]'))


def downgrade():
    op.drop_column('Agent', 'exposed_chat_filters')
