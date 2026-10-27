"""Schedule automatic agent migration when an AI service ends."""

from alembic import op
import sqlalchemy as sa

revision = "svceos002"
down_revision = "siloparser001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "AIService",
        sa.Column("auto_move_to_service_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_AIService_auto_move_to_service_id_AIService",
        "AIService",
        "AIService",
        ["auto_move_to_service_id"],
        ["service_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_AIService_auto_move_to_service_id",
        "AIService",
        ["auto_move_to_service_id"],
    )


def downgrade():
    op.drop_index("ix_AIService_auto_move_to_service_id", table_name="AIService")
    op.drop_constraint(
        "fk_AIService_auto_move_to_service_id_AIService",
        "AIService",
        type_="foreignkey",
    )
    op.drop_column("AIService", "auto_move_to_service_id")
