"""App images: table "app_image".

Same shape as "user_avatar" (``models/stored_image.py``): one row per App (PK = FK "App".app_id,
ON DELETE CASCADE) holding the normalised 256x256 WebP, its content type and ``updated_at`` (the
frontend's cache key). Apps without a row show their initials.

Downgrade drops the table: every uploaded App image is lost.

Revision ID: appimage001
Revises: useravatar001
"""

import sqlalchemy as sa

from alembic import op

revision = "appimage001"
down_revision = "useravatar001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "app_image",
        sa.Column("app_id", sa.Integer(), sa.ForeignKey("App.app_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("content_type", sa.String(length=50), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        if_not_exists=True,
    )


def downgrade():
    op.drop_table("app_image", if_exists=True)
