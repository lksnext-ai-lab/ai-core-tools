"""App Chat: per-conversation busy marker and App default embedding service.

- chat_conversation_state.busy_token (UUID, NULL) and busy_until (timestamptz,
  NULL): compare-and-set "turn in flight" marker with an expiry, used to reject
  a second concurrent turn on the same conversation with HTTP 409. No index:
  rows are addressed by primary key (conversation_id).
- App.default_embedding_service_id (Integer, NULL) FK to
  embedding_service.service_id ON DELETE SET NULL (named, added as a separate
  step like sandbox001's App_default_sandbox_service_id_fkey). When set, the
  Chat indexes attachments with it. No index (mirrors default_sandbox_service_id).

- Repository: partial index ix_Repository_silo_id_temp on (silo_id) WHERE type = 'playground_media'. The
  visibility rule of conversation temp silos looks a silo up in "Repository" on every silo list / public silo
  request, and temp repositories grow one per conversation. Partial: it stays tiny, and EXPLAIN on the test DB
  showed an index-only scan for the per-silo lookup. Plain CREATE INDEX (the table is small at this point).

All additions are nullable without defaults (metadata-only in PostgreSQL);
existing rows get NULL. No backfill. The FK validation scans "App" (small table).

Downgrade drops the FK and the columns in reverse order; the values stored in
them are lost (busy markers are transient; the App default is configuration).

Revision ID: ichat002
Revises: ichat001
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "ichat002"
down_revision = "ichat001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_Repository_silo_id_temp", "Repository", ["silo_id"], postgresql_where=sa.text("type = 'playground_media'")
    )
    op.add_column(
        "chat_conversation_state", sa.Column("busy_token", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "chat_conversation_state", sa.Column("busy_until", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("App", sa.Column("default_embedding_service_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "App_default_embedding_service_id_fkey",
        "App", "embedding_service", ["default_embedding_service_id"], ["service_id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_index("ix_Repository_silo_id_temp", table_name="Repository")
    op.drop_constraint("App_default_embedding_service_id_fkey", "App", type_="foreignkey")
    op.drop_column("App", "default_embedding_service_id")
    op.drop_column("chat_conversation_state", "busy_until")
    op.drop_column("chat_conversation_state", "busy_token")
