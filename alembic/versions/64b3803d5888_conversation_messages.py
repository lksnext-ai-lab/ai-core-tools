"""conversation_messages

Revision ID: 64b3803d5888
Revises: useremail001
Create Date: 2026-06-15 19:07:41.554676

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "64b3803d5888"
down_revision = "useremail001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("message_type", sa.String(length=20), nullable=False, server_default="text"),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("audio_file_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["Conversation.conversation_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "idx_conversation_messages_conversation_id",
        "conversation_messages",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        "idx_conversation_messages_created_at",
        "conversation_messages",
        ["created_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("idx_conversation_messages_created_at", table_name="conversation_messages")
    op.drop_index("idx_conversation_messages_conversation_id", table_name="conversation_messages")
    op.drop_table("conversation_messages")