"""Planned end of service for AI, embedding and sandbox services.

Each service can carry an optional end_of_service_at date (timezone-aware) and a free-text
deprecation_notice (max 1000 chars) shown to users. The status (active / deprecated / retired)
is computed at read time from the date, so nothing else is stored. Both columns are nullable;
existing rows stay NULL (no end of service planned).
"""

from alembic import op
import sqlalchemy as sa

revision = "svceos001"
down_revision = "indexerr001"
branch_labels = None
depends_on = None

_TABLES = ("AIService", "embedding_service", "SandboxService")


def upgrade():
    for table in _TABLES:
        op.add_column(table, sa.Column("end_of_service_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column(table, sa.Column("deprecation_notice", sa.String(1000), nullable=True))


def downgrade():
    for table in reversed(_TABLES):
        op.drop_column(table, "deprecation_notice")
        op.drop_column(table, "end_of_service_at")
