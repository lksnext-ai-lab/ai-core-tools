"""system_embedding_services: make EmbeddingService.app_id nullable

Revision ID: saas003
Revises: saas002
Create Date: 2026-03-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'saas003'
down_revision = 'saas002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make app_id nullable in EmbeddingService — NULL means platform-level (system) service
    op.alter_column(
        'embedding_service',
        'app_id',
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    # Delete system embedding services (app_id IS NULL) so NOT NULL can be restored.
    # These have no app to migrate back to — deleting is the only safe reversal.
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM embedding_service WHERE app_id IS NULL"))

    # Restore NOT NULL on app_id (safe — no NULL rows remain)
    op.alter_column(
        'embedding_service',
        'app_id',
        existing_type=sa.Integer(),
        nullable=False,
    )
