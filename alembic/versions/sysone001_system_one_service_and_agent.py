"""System One: SystemOneService, SystemOneAgent (STI child of Agent) and per-question answer rows."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "sysone001"
down_revision = "a2a001_agent_server"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "SystemOneService",
        sa.Column("service_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("create_date", sa.DateTime()),
        sa.Column("endpoint", sa.String(255)),
        sa.Column("api_key", sa.Text()),
        sa.Column("description", sa.String(1000)),
        sa.Column("api_version", sa.String(50)),
        sa.Column("extra_config", sa.Text()),
        sa.Column("app_id", sa.Integer(), sa.ForeignKey("App.app_id"), nullable=False),
    )
    op.create_index("ix_SystemOneService_service_id", "SystemOneService", ["service_id"])

    op.create_table(
        "SystemOneAgent",
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("Agent.agent_id"), primary_key=True),
        sa.Column(
            "system_one_service_id", sa.Integer(),
            sa.ForeignKey("SystemOneService.service_id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("questions", sa.JSON(), nullable=False),
        sa.Column(
            "summarization_service_id", sa.Integer(),
            sa.ForeignKey("AIService.service_id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("max_state_chars", sa.Integer(), nullable=False, server_default=sa.text("6000")),
    )

    op.create_table(
        "agent_system_one_answer",
        sa.Column("answer_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "event_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_execution_event.event_id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("question_key", sa.String(40), nullable=False),
        sa.Column("question_type", sa.String(10), nullable=False),
        sa.Column("decision", sa.Text()),
        sa.Column("probability", sa.Float()),
        sa.Column("expected_score", sa.Float()),
        sa.Column("confidence", sa.Float()),
        sa.Column("probabilities", sa.JSON()),
        sa.Column("state_reduction", sa.String(12), nullable=False),
    )
    op.create_index("ix_agent_system_one_answer_event_id", "agent_system_one_answer", ["event_id"])


def downgrade():
    # Older code cannot load an Agent row with a type it does not know (the model is polymorphic on `type`):
    # one leftover row would break every agent query. So the System One agents are removed with their rows
    # (metrics events and answers go with them through their ON DELETE CASCADE foreign keys).
    system_one = "SELECT agent_id FROM \"Agent\" WHERE type = 'system_one_agent'"
    op.execute(f"DELETE FROM agent_tools WHERE agent_id IN ({system_one}) OR tool_id IN ({system_one})")
    op.execute(f"DELETE FROM agent_mcps WHERE agent_id IN ({system_one})")
    op.execute(f"DELETE FROM agent_skills WHERE agent_id IN ({system_one})")
    op.drop_index("ix_agent_system_one_answer_event_id", table_name="agent_system_one_answer")
    op.drop_table("agent_system_one_answer")
    op.drop_table("SystemOneAgent")
    op.execute("DELETE FROM \"Agent\" WHERE type = 'system_one_agent'")
    op.drop_index("ix_SystemOneService_service_id", table_name="SystemOneService")
    op.drop_table("SystemOneService")
