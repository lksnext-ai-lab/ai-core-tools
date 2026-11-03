"""agent_execution_event: what the summarizing LLM of a System One agent used, apart from the server's tokens.

``input_tokens`` / ``output_tokens`` / ``total_tokens`` of a System One execution are the System One server's. The calls
to the summarizing LLM (and its tokens) get their own columns so the dashboard can show both without mixing them.
"""

from alembic import op
import sqlalchemy as sa

revision = "sysone003"
down_revision = "sysone002"
branch_labels = None
depends_on = None

TABLE = "agent_execution_event"
COLUMNS = ("summarization_calls", "summarization_input_tokens", "summarization_output_tokens")


def upgrade():
    for name in COLUMNS:
        op.add_column(TABLE, sa.Column(name, sa.Integer(), nullable=False, server_default=sa.text("0")))
    # Until now a System One execution counted its summarization as llm_calls = 1 (its tokens were not kept): move
    # those to their own column so the history reads the same as the new rows.
    op.execute(f"UPDATE {TABLE} SET summarization_calls = llm_calls, llm_calls = 0 "
               "WHERE provider = 'system_one' AND llm_calls > 0")


def downgrade():
    op.execute(f"UPDATE {TABLE} SET llm_calls = summarization_calls WHERE provider = 'system_one' AND summarization_calls > 0")
    for name in reversed(COLUMNS):
        op.drop_column(TABLE, name)
