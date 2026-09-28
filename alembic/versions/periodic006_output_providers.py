"""Teams Workflow output destinations, task bindings, and durable delivery outbox."""

from alembic import op
import sqlalchemy as sa

revision = "periodic006"
down_revision = "periodic005"
branch_labels = None
depends_on = None


def upgrade():
    # Historical runs are already complete and must never be backfilled to newly
    # configured destinations. Only the exceptional fallback path sets this false.
    op.add_column("scheduled_task_run", sa.Column("outputs_reconciled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table(
        "output_destination",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("app_id", sa.Integer(), sa.ForeignKey("App.app_id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("provider_key", sa.String(length=80), nullable=False, server_default="teams_workflow"),
        sa.Column("public_config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("webhook_url", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("User.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("app_id", "name", name="uq_output_destination_app_name"),
    )
    op.create_index("ix_output_destination_app_id", "output_destination", ["app_id"])

    op.create_table(
        "scheduled_task_output_binding",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scheduled_task_id", sa.Integer(), sa.ForeignKey("scheduled_task.id", ondelete="CASCADE"), nullable=False),
        sa.Column("destination_id", sa.Integer(), sa.ForeignKey("output_destination.id", ondelete="CASCADE"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("event_types", sa.JSON(), nullable=False, server_default='["succeeded"]'),
        sa.Column("content_mode", sa.String(length=30), nullable=False, server_default="result"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("scheduled_task_id", "destination_id", name="uq_task_output_destination"),
    )
    op.create_index("ix_scheduled_task_output_binding_scheduled_task_id", "scheduled_task_output_binding", ["scheduled_task_id"])
    op.create_index("ix_scheduled_task_output_binding_destination_id", "scheduled_task_output_binding", ["destination_id"])

    op.create_table(
        "output_delivery",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("scheduled_task_run.id", ondelete="CASCADE"), nullable=False),
        sa.Column("binding_id", sa.Integer(), sa.ForeignKey("scheduled_task_output_binding.id", ondelete="CASCADE"), nullable=False),
        sa.Column("destination_id", sa.Integer(), sa.ForeignKey("output_destination.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(length=30), nullable=False, server_default="succeeded"),
        sa.Column("destination_snapshot", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dispatch_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("lease_until", sa.DateTime(), nullable=True),
        sa.Column("receipt", sa.JSON(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("run_id", "binding_id", "event_type", name="uq_output_delivery_run_binding_event"),
    )
    op.create_index("ix_output_delivery_run_id", "output_delivery", ["run_id"])
    op.create_index("ix_output_delivery_binding_id", "output_delivery", ["binding_id"])
    op.create_index("ix_output_delivery_status", "output_delivery", ["status"])
    op.create_index("ix_output_delivery_dispatch", "output_delivery", ["status", "next_attempt_at"])

    op.create_table(
        "output_delivery_attempt",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("delivery_id", sa.Integer(), sa.ForeignKey("output_delivery.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="sending"),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
    )
    op.create_index("ix_output_delivery_attempt_delivery_id", "output_delivery_attempt", ["delivery_id"])


def downgrade():
    op.drop_index("ix_output_delivery_attempt_delivery_id", table_name="output_delivery_attempt")
    op.drop_table("output_delivery_attempt")
    op.drop_index("ix_output_delivery_dispatch", table_name="output_delivery")
    op.drop_index("ix_output_delivery_status", table_name="output_delivery")
    op.drop_index("ix_output_delivery_binding_id", table_name="output_delivery")
    op.drop_index("ix_output_delivery_run_id", table_name="output_delivery")
    op.drop_table("output_delivery")
    op.drop_index("ix_scheduled_task_output_binding_destination_id", table_name="scheduled_task_output_binding")
    op.drop_index("ix_scheduled_task_output_binding_scheduled_task_id", table_name="scheduled_task_output_binding")
    op.drop_table("scheduled_task_output_binding")
    op.drop_index("ix_output_destination_app_id", table_name="output_destination")
    op.drop_table("output_destination")
    op.drop_column("scheduled_task_run", "outputs_reconciled")
