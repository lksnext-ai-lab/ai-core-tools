"""App Chat: App-level opt-in to run code in the Chat.

- "App".chat_code_interpreter_enabled (Boolean, NOT NULL, server default false).
  The Chat only gets a code interpreter when this is true; it then uses the
  App default sandbox service or, when none, the system default (like agents);
  a retired App default disables it. Existing Apps get false (the server default
  fills them; PostgreSQL 11+ adds a constant default without rewriting the table).

Downgrade drops the column; the stored opt-in values are lost.

Revision ID: ichat003
Revises: ichat002
"""

from alembic import op
import sqlalchemy as sa

revision = "ichat003"
down_revision = "ichat002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "App",
        sa.Column("chat_code_interpreter_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("App", "chat_code_interpreter_enabled")
