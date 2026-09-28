"""Media (video/audio) indexing configuration lives on the silo.

- Silo.transcription_service_id / video_ai_service_id: moved from Repository, so a silo used
  directly (public API) can index video/audio like a repository does. Repositories keep
  configuring them, but the values are stored on the repository's silo.
- Media.silo_id: media now belongs to a silo; repository_id becomes optional (media indexed
  straight into a silo has no repository). Media.custom_metadata: caller metadata to attach to
  every chunk (public API).
"""

from alembic import op
import sqlalchemy as sa

revision = "mediasilo001"
down_revision = "periodic005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("Silo", sa.Column(
        "transcription_service_id", sa.Integer(),
        sa.ForeignKey("AIService.service_id", ondelete="SET NULL"), nullable=True,
    ))
    op.add_column("Silo", sa.Column(
        "video_ai_service_id", sa.Integer(),
        sa.ForeignKey("AIService.service_id", ondelete="SET NULL"), nullable=True,
    ))
    op.execute(
        'UPDATE "Silo" s SET transcription_service_id = r.transcription_service_id, '
        'video_ai_service_id = r.video_ai_service_id '
        'FROM "Repository" r WHERE r.silo_id = s.silo_id'
    )
    op.drop_column("Repository", "video_ai_service_id")
    op.drop_column("Repository", "transcription_service_id")

    op.add_column("Media", sa.Column(
        "silo_id", sa.Integer(), sa.ForeignKey("Silo.silo_id", ondelete="CASCADE"), nullable=True,
    ))
    op.execute('UPDATE "Media" m SET silo_id = r.silo_id FROM "Repository" r WHERE r.repository_id = m.repository_id')
    op.execute('DELETE FROM "Media" WHERE silo_id IS NULL')
    op.alter_column("Media", "silo_id", nullable=False)
    op.create_index("ix_media_silo_id", "Media", ["silo_id"])
    op.alter_column("Media", "repository_id", nullable=True)
    op.add_column("Media", sa.Column("custom_metadata", sa.JSON(), nullable=True))


def downgrade():
    # Media indexed straight into a silo has no repository and cannot be represented before this revision.
    op.execute('DELETE FROM "Media" WHERE repository_id IS NULL')
    op.drop_column("Media", "custom_metadata")
    op.alter_column("Media", "repository_id", nullable=False)
    op.drop_index("ix_media_silo_id", table_name="Media")
    op.drop_column("Media", "silo_id")

    op.add_column("Repository", sa.Column(
        "transcription_service_id", sa.Integer(), sa.ForeignKey("AIService.service_id"), nullable=True,
    ))
    op.add_column("Repository", sa.Column(
        "video_ai_service_id", sa.Integer(), sa.ForeignKey("AIService.service_id"), nullable=True,
    ))
    op.execute(
        'UPDATE "Repository" r SET transcription_service_id = s.transcription_service_id, '
        'video_ai_service_id = s.video_ai_service_id FROM "Silo" s WHERE r.silo_id = s.silo_id'
    )
    op.drop_column("Silo", "video_ai_service_id")
    op.drop_column("Silo", "transcription_service_id")
