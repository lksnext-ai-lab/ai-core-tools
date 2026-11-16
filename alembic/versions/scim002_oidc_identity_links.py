"""Persist explicit OIDC subject to SCIM identity mappings."""

from alembic import op
import sqlalchemy as sa


revision = "scim002"
down_revision = "scim001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "oidc_identity_link",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("User.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            sa.Integer(),
            sa.ForeignKey("provisioning_connection.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("issuer", sa.String(length=1024), nullable=False),
        sa.Column("subject", sa.String(length=512), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "issuer",
            "subject",
            name="uq_oidc_identity_link_issuer_subject",
        ),
        sa.UniqueConstraint(
            "connection_id",
            "external_id",
            name="uq_oidc_identity_link_connection_external_id",
        ),
    )
    op.create_index(
        "ix_oidc_identity_link_user_id",
        "oidc_identity_link",
        ["user_id"],
    )
    op.create_index(
        "ix_oidc_identity_link_connection_id",
        "oidc_identity_link",
        ["connection_id"],
    )


def downgrade():
    op.drop_index("ix_oidc_identity_link_connection_id", table_name="oidc_identity_link")
    op.drop_index("ix_oidc_identity_link_user_id", table_name="oidc_identity_link")
    op.drop_table("oidc_identity_link")
