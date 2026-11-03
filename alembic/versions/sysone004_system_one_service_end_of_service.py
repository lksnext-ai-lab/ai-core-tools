"""Planned end of service for System One services.

Same columns as the AI, embedding and sandbox services (svceos001): an optional end_of_service_at date
(timezone-aware) and a free-text deprecation_notice (max 1000 chars). The status is computed at read time.
Both columns are nullable; existing rows stay NULL (no end of service planned).
"""

from alembic import op
import sqlalchemy as sa

revision = "sysone004"
down_revision = "sysone003"
branch_labels = None
depends_on = None

TABLE = "SystemOneService"


def upgrade():
    op.add_column(TABLE, sa.Column("end_of_service_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(TABLE, sa.Column("deprecation_notice", sa.String(1000), nullable=True))


def downgrade():
    op.drop_column(TABLE, "deprecation_notice")
    op.drop_column(TABLE, "end_of_service_at")
