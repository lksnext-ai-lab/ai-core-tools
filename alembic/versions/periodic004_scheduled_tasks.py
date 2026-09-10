"""Add first-class scheduled tasks."""

from alembic import op
import sqlalchemy as sa

revision = "periodic004"
down_revision = "1eeb4ba697f8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "scheduled_task",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("Agent.agent_id", ondelete="CASCADE"), nullable=False),
        sa.Column("app_id", sa.Integer(), sa.ForeignKey("App.app_id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("User.user_id"), nullable=False),
        sa.Column("orchestrator_schedule_name", sa.String(255), nullable=False, unique=True),
        sa.Column("input", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("cron_expression", sa.String(120), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("conversation_mode", sa.String(20), nullable=False, server_default="new_per_run"),
        sa.Column("persistent_conversation_id", sa.Integer(), sa.ForeignKey("Conversation.conversation_id")),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("max_concurrent_runs", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "scheduled_task_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scheduled_task_id", sa.Integer(), sa.ForeignKey("scheduled_task.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("Conversation.conversation_id")),
        sa.Column("conversation_anchor_message_id", sa.Integer()),
        sa.Column("orchestrator_run_id", sa.String(255), nullable=False),
        sa.Column("scheduled_time", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("finished_at", sa.DateTime()),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text()),
    )
    op.create_index("ix_scheduled_task_run_task", "scheduled_task_run", ["scheduled_task_id", "scheduled_time"])
    op.execute("ALTER TYPE conversationsource ADD VALUE IF NOT EXISTS 'SCHEDULED_TASK'")


def downgrade():
    op.drop_index("ix_scheduled_task_run_task", table_name="scheduled_task_run")
    op.drop_table("scheduled_task_run")
    op.drop_table("scheduled_task")
