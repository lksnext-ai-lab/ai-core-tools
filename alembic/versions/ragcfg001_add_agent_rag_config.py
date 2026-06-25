"""add agent rag config columns

Revision ID: ragcfg001
Revises: platform_role002
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa


revision = 'ragcfg001'
down_revision = 'platform_role002'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('Agent', sa.Column('rag_k', sa.Integer(), nullable=False, server_default='30'))
    op.add_column('Agent', sa.Column('rag_search_type', sa.String(45), nullable=False, server_default='similarity'))
    op.add_column('Agent', sa.Column('rag_score_threshold', sa.Float(), nullable=True))
    op.add_column('Agent', sa.Column('rag_fixed_filters', sa.JSON(), nullable=True))
    op.add_column('Agent', sa.Column('rag_max_retrieval_calls', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('Agent', 'rag_max_retrieval_calls')
    op.drop_column('Agent', 'rag_fixed_filters')
    op.drop_column('Agent', 'rag_score_threshold')
    op.drop_column('Agent', 'rag_search_type')
    op.drop_column('Agent', 'rag_k')
