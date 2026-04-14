"""add_transcription_and_video_ai_service_to_repository

Revision ID: a3f1b9c2d4e7
Revises: 4d2049cddf25
Create Date: 2026-04-14

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3f1b9c2d4e7'
down_revision = '4d2049cddf25'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('Repository', sa.Column('transcription_service_id', sa.Integer(), nullable=True))
    op.add_column('Repository', sa.Column('video_ai_service_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_repository_transcription_service',
        'Repository', 'AIService',
        ['transcription_service_id'], ['service_id']
    )
    op.create_foreign_key(
        'fk_repository_video_ai_service',
        'Repository', 'AIService',
        ['video_ai_service_id'], ['service_id']
    )


def downgrade():
    op.drop_constraint('fk_repository_video_ai_service', 'Repository', type_='foreignkey')
    op.drop_constraint('fk_repository_transcription_service', 'Repository', type_='foreignkey')
    op.drop_column('Repository', 'video_ai_service_id')
    op.drop_column('Repository', 'transcription_service_id')
