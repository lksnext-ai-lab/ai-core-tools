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
    # Safety check: refuse to downgrade if any system embedding services exist
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT COUNT(*) FROM embedding_service WHERE app_id IS NULL")
    )
    count = result.scalar()
    if count > 0:
        raise Exception(
            f"Cannot downgrade: {count} system embedding service(s) exist with app_id IS NULL. "
            "Delete them first."
        )

    # Restore NOT NULL on app_id
    op.alter_column(
        'embedding_service',
        'app_id',
        existing_type=sa.Integer(),
        nullable=False,
    )
