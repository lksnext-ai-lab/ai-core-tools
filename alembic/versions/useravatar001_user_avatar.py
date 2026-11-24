"""User profile pictures: table "user_avatar".

One row per user (PK = FK "User".user_id, ON DELETE CASCADE) holding the normalised image bytes
(256x256 WebP produced by ``services/user_avatar_service.py``), its content type and ``updated_at``
(the frontend's cache key). Users without a row show their initials.

Downgrade drops the table: every uploaded picture is lost.

Revision ID: useravatar001
Revises: ichat004
"""

import sqlalchemy as sa

from alembic import op

revision = "useravatar001"
down_revision = "ichat004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_avatar",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("User.user_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("content_type", sa.String(length=50), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        if_not_exists=True,
    )


def downgrade():
    op.drop_table("user_avatar", if_exists=True)
