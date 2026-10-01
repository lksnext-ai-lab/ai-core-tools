"""Add agent-level media processing configuration columns.

Moves the playground media upload configuration (transcription/video AI
services, forced language, chunk durations and overlap) to the Agent level so
uploads only require choosing the file or URL.

Revision ID: agtmedia001
Revises: spoint001
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'agtmedia001'
down_revision = 'd3adbeef1234'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'Agent',
        sa.Column('transcription_service_id', sa.Integer(), nullable=True),
    )
    op.add_column(
        'Agent',
        sa.Column('video_ai_service_id', sa.Integer(), nullable=True),
    )
    op.add_column(
        'Agent',
        sa.Column('media_forced_language', sa.String(length=10), nullable=True),
    )
    op.add_column(
        'Agent',
        sa.Column(
            'media_chunk_min_duration',
            sa.Integer(),
            nullable=False,
            server_default='30',
        ),
    )
    op.add_column(
        'Agent',
        sa.Column(
            'media_chunk_max_duration',
            sa.Integer(),
            nullable=False,
            server_default='120',
        ),
    )
    op.add_column(
        'Agent',
        sa.Column(
            'media_chunk_overlap',
            sa.Integer(),
            nullable=False,
            server_default='5',
        ),
    )
    op.create_foreign_key(
        'fk_agent_transcription_service',
        'Agent',
        'AIService',
        ['transcription_service_id'],
        ['service_id'],
        ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_agent_video_ai_service',
        'Agent',
        'AIService',
        ['video_ai_service_id'],
        ['service_id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_agent_video_ai_service', 'Agent', type_='foreignkey')
    op.drop_constraint('fk_agent_transcription_service', 'Agent', type_='foreignkey')
    op.drop_column('Agent', 'media_chunk_overlap')
    op.drop_column('Agent', 'media_chunk_max_duration')
    op.drop_column('Agent', 'media_chunk_min_duration')
    op.drop_column('Agent', 'media_forced_language')
    op.drop_column('Agent', 'video_ai_service_id')
    op.drop_column('Agent', 'transcription_service_id')
