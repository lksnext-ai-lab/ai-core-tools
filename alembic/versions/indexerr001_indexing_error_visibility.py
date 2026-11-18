"""Indexing failures are stored where users see them.

- Resource.error_message: why the last indexing of the document failed (Resource.status,
  which already existed but was never written, now holds indexed / error).
- AIService / embedding_service .last_error + .last_error_at: the last provider failure that
  needs action on the service (rejected key, exhausted quota); cleared on the next success
  or when the service settings are edited.
"""

from alembic import op
import sqlalchemy as sa

revision = "indexerr001"
down_revision = "mediasilo001"
branch_labels = None
depends_on = None

_SERVICE_TABLES = ("AIService", "embedding_service")


def upgrade():
    op.add_column("Resource", sa.Column("error_message", sa.Text(), nullable=True))
    for table in _SERVICE_TABLES:
        op.add_column(table, sa.Column("last_error", sa.Text(), nullable=True))
        op.add_column(table, sa.Column("last_error_at", sa.DateTime(), nullable=True))


def downgrade():
    for table in _SERVICE_TABLES:
        op.drop_column(table, "last_error_at")
        op.drop_column(table, "last_error")
    op.drop_column("Resource", "error_message")
