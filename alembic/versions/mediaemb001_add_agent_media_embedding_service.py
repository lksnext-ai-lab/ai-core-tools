"""Add agent-level media embedding service.

Adds ``Agent.media_embedding_service_id`` so the playground media/document
vectorization uses an explicitly configured embedding service instead of
falling back to an arbitrary (possibly misconfigured) app-scoped service.

Revision ID: mediaemb001
Revises: agtmedia001
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'mediaemb001'
down_revision = 'agtmedia001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'Agent',
        sa.Column('media_embedding_service_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'fk_agent_media_embedding_service',
        'Agent',
        'embedding_service',
        ['media_embedding_service_id'],
        ['service_id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_agent_media_embedding_service', 'Agent', type_='foreignkey')
    op.drop_column('Agent', 'media_embedding_service_id')
