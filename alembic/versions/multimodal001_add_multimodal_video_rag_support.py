"""add multimodal video RAG support

Revision ID: multimodal001
Revises: 881e4ca78388
Create Date: 2026-02-16

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'multimodal001'
down_revision = '881e4ca78388'
branch_labels = None
depends_on = None


def upgrade():
    # Add supports_video to AIService table only (not relevant for EmbeddingService)
    op.add_column('AIService', sa.Column('supports_video', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    
    # Add processing_mode and video_service_id to Media table
    op.add_column('Media', sa.Column('processing_mode', sa.String(length=20), nullable=True, server_default='basic'))
    op.add_column('Media', sa.Column('video_service_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_media_video_service_id',
        'Media', 'AIService',
        ['video_service_id'], ['service_id']
    )


def downgrade():
    op.drop_constraint('fk_media_video_service_id', 'Media', type_='foreignkey')
    op.drop_column('Media', 'video_service_id')
    op.drop_column('Media', 'processing_mode')
    op.drop_column('AIService', 'supports_video')
