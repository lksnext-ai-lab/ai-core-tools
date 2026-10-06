"""Generic scheduled-task webhooks, credentials, and durable attachments."""

from alembic import op
import sqlalchemy as sa


revision = "periodic007"
down_revision = "periodic006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("output_destination", sa.Column("credentials", sa.JSON(), nullable=True))
    op.add_column("output_delivery", sa.Column("request_body", sa.LargeBinary(), nullable=True))
    op.add_column("output_delivery", sa.Column("request_body_path", sa.Text(), nullable=True))
    op.add_column("output_delivery", sa.Column("request_body_size", sa.Integer(), nullable=True))
    op.add_column("output_delivery", sa.Column("request_body_sha256", sa.String(length=64), nullable=True))
    op.create_table(
        "output_artifact",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("scheduled_task_run.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", sa.String(length=255), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("run_id", "file_id", name="uq_output_artifact_run_file"),
    )
    op.create_index("ix_output_artifact_run_id", "output_artifact", ["run_id"])


def downgrade():
    op.drop_index("ix_output_artifact_run_id", table_name="output_artifact")
    op.drop_table("output_artifact")
    op.drop_column("output_delivery", "request_body_sha256")
    op.drop_column("output_delivery", "request_body_path")
    op.drop_column("output_delivery", "request_body_size")
    op.drop_column("output_delivery", "request_body")
    op.drop_column("output_destination", "credentials")
