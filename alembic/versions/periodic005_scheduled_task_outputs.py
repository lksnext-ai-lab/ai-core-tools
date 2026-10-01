"""Scheduled tasks own their conversations and outputs; retention; marketplace visibility.

- Conversation.scheduled_task_id: conversations created by a scheduled task belong to the
  task (user_id stays NULL), so they never show up in a user's playground history.
- scheduled_task_run.output_text / output_files: the run's own result, readable without the
  LangGraph checkpointer (works for memory-less agents too).
- scheduled_task.max_runs_retained (default 10), description, marketplace_visibility.
- New metrics channel SCHEDULED_TASK.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "periodic005"
down_revision = "periodic004"
branch_labels = None
depends_on = None


def upgrade():
    visibility = postgresql.ENUM("UNPUBLISHED", "PRIVATE", "PUBLIC", name="marketplacevisibility", create_type=False)
    op.add_column("scheduled_task", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("scheduled_task", sa.Column("max_runs_retained", sa.Integer(), nullable=False, server_default="10"))
    op.add_column(
        "scheduled_task",
        sa.Column("marketplace_visibility", visibility, nullable=False, server_default="UNPUBLISHED"),
    )
    op.add_column("scheduled_task_run", sa.Column("output_text", sa.Text(), nullable=True))
    op.add_column("scheduled_task_run", sa.Column("output_files", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column(
        "Conversation",
        sa.Column("scheduled_task_id", sa.Integer(), sa.ForeignKey("scheduled_task.id", ondelete="CASCADE"), nullable=True),
    )
    op.create_index("ix_conversation_scheduled_task_id", "Conversation", ["scheduled_task_id"])
    # Runs can outlive their conversation for a moment during pruning/deletion.
    op.drop_constraint("scheduled_task_run_conversation_id_fkey", "scheduled_task_run", type_="foreignkey")
    op.create_foreign_key(
        "scheduled_task_run_conversation_id_fkey", "scheduled_task_run", "Conversation",
        ["conversation_id"], ["conversation_id"], ondelete="SET NULL",
    )
    op.drop_constraint("scheduled_task_persistent_conversation_id_fkey", "scheduled_task", type_="foreignkey")
    op.create_foreign_key(
        "scheduled_task_persistent_conversation_id_fkey", "scheduled_task", "Conversation",
        ["persistent_conversation_id"], ["conversation_id"], ondelete="SET NULL",
    )
    # Deleted tasks are now removed for real.
    op.execute("DELETE FROM scheduled_task WHERE status = 'deleted'")
    op.execute("ALTER TYPE agent_execution_caller_type ADD VALUE IF NOT EXISTS 'SCHEDULED_TASK'")


def downgrade():
    # Postgres cannot drop an enum value; SCHEDULED_TASK stays in agent_execution_caller_type.
    op.execute("UPDATE agent_execution_event SET caller_type = 'INTERNAL_PLAYGROUND' WHERE caller_type = 'SCHEDULED_TASK'")
    op.drop_constraint("scheduled_task_persistent_conversation_id_fkey", "scheduled_task", type_="foreignkey")
    op.create_foreign_key(
        "scheduled_task_persistent_conversation_id_fkey", "scheduled_task", "Conversation",
        ["persistent_conversation_id"], ["conversation_id"],
    )
    op.drop_constraint("scheduled_task_run_conversation_id_fkey", "scheduled_task_run", type_="foreignkey")
    op.create_foreign_key(
        "scheduled_task_run_conversation_id_fkey", "scheduled_task_run", "Conversation",
        ["conversation_id"], ["conversation_id"],
    )
    op.drop_index("ix_conversation_scheduled_task_id", table_name="Conversation")
    op.drop_column("Conversation", "scheduled_task_id")
    op.drop_column("scheduled_task_run", "output_files")
    op.drop_column("scheduled_task_run", "output_text")
    op.drop_column("scheduled_task", "marketplace_visibility")
    op.drop_column("scheduled_task", "max_runs_retained")
    op.drop_column("scheduled_task", "description")
