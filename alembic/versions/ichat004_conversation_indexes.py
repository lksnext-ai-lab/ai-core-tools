"""App Chat: indexes of "Conversation" for the per-user history listing.

- ix_conversation_agent_user_updated  (agent_id, user_id, updated_at DESC): the Chat lists one user's conversations
  of the shared internal agent, newest first.
- ix_conversation_agent_api_key_hash  (agent_id, api_key_hash): the API-key conversation lookup. The old
  ``idx_conversation_agent_user`` / ``idx_conversation_agent_api`` were dropped by d9c43f453f24 and never came back.

Plain ``CREATE INDEX`` (the repository has no ``CONCURRENTLY`` pattern): it takes a short write lock on "Conversation";
run the upgrade in a quiet moment on a very large table. Both statements are idempotent.

Downgrade drops both indexes.

Revision ID: ichat004
Revises: ichat003
"""

from alembic import op
import sqlalchemy as sa

revision = "ichat004"
down_revision = "ichat003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_conversation_agent_user_updated", "Conversation",
        ["agent_id", "user_id", sa.text("updated_at DESC")], if_not_exists=True,
    )
    op.create_index(
        "ix_conversation_agent_api_key_hash", "Conversation", ["agent_id", "api_key_hash"], if_not_exists=True,
    )


def downgrade():
    op.drop_index("ix_conversation_agent_api_key_hash", table_name="Conversation", if_exists=True)
    op.drop_index("ix_conversation_agent_user_updated", table_name="Conversation", if_exists=True)
