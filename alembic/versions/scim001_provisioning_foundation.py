"""Add the provider-neutral SCIM provisioning data model."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "scim001"
down_revision = "chatfiltmerge003"
branch_labels = None
depends_on = None


def upgrade():
    access_role = postgresql.ENUM(
        "VIEWER",
        "EDITOR",
        name="group_app_access_role",
        create_type=False,
    )
    access_role.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "provisioning_connection",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_type", sa.String(length=50), nullable=False),
        sa.Column("external_directory_id", sa.String(length=255), nullable=True),
        sa.Column("connection_key", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("auth_mode", sa.String(length=50), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=True),
        sa.Column("credential_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "provider_type",
            "external_directory_id",
            name="uq_provisioning_connection_provider_directory",
        ),
        sa.UniqueConstraint("connection_key", name="uq_provisioning_connection_key"),
    )
    op.create_index(
        "uq_provisioning_connection_client_id",
        "provisioning_connection",
        ["client_id"],
        unique=True,
        postgresql_where=sa.text("client_id IS NOT NULL"),
    )
    op.create_index(
        "ix_provisioning_connection_active",
        "provisioning_connection",
        ["is_active"],
        postgresql_where=sa.text("is_active IS TRUE"),
    )

    op.create_table(
        "user_external_identity",
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
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("scim_id", sa.String(length=255), nullable=False),
        sa.Column("user_name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("manager_external_id", sa.String(length=255), nullable=True),
        sa.Column(
            "manager_identity_id",
            sa.Integer(),
            sa.ForeignKey("user_external_identity.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("department", sa.String(length=255), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_user_external_identity_user_id"),
        sa.UniqueConstraint(
            "connection_id",
            "external_id",
            name="uq_user_external_identity_connection_external_id",
        ),
        sa.UniqueConstraint(
            "connection_id",
            "scim_id",
            name="uq_user_external_identity_connection_scim_id",
        ),
    )
    op.create_index("ix_user_external_identity_connection_id", "user_external_identity", ["connection_id"])
    op.create_index("ix_user_external_identity_manager_identity_id", "user_external_identity", ["manager_identity_id"])
    op.create_index(
        "ix_user_external_identity_active",
        "user_external_identity",
        ["is_active"],
        postgresql_where=sa.text("is_active IS TRUE"),
    )

    op.create_table(
        "external_group",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "connection_id",
            sa.Integer(),
            sa.ForeignKey("provisioning_connection.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("scim_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("connection_id", "external_id", name="uq_external_group_connection_external_id"),
        sa.UniqueConstraint("connection_id", "scim_id", name="uq_external_group_connection_scim_id"),
    )
    op.create_index("ix_external_group_connection_id", "external_group", ["connection_id"])
    op.create_index(
        "ix_external_group_active",
        "external_group",
        ["is_active"],
        postgresql_where=sa.text("is_active IS TRUE"),
    )

    op.create_table(
        "external_group_membership",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("external_group.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_external_identity_id",
            sa.Integer(),
            sa.ForeignKey("user_external_identity.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "group_id",
            "user_external_identity_id",
            name="uq_external_group_membership_group_identity",
        ),
    )
    op.create_index("ix_external_group_membership_group_id", "external_group_membership", ["group_id"])
    op.create_index(
        "ix_external_group_membership_user_external_identity_id",
        "external_group_membership",
        ["user_external_identity_id"],
    )

    op.create_table(
        "group_app_access_rule",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("external_group.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "app_id",
            sa.Integer(),
            sa.ForeignKey("App.app_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", access_role, nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("User.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("group_id", "app_id", name="uq_group_app_access_rule_group_app"),
    )
    op.create_index("ix_group_app_access_rule_group_id", "group_app_access_rule", ["group_id"])
    op.create_index("ix_group_app_access_rule_app_id", "group_app_access_rule", ["app_id"])
    op.create_index(
        "ix_group_app_access_rule_created_by_user_id",
        "group_app_access_rule",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_group_app_access_rule_active",
        "group_app_access_rule",
        ["is_active"],
        postgresql_where=sa.text("is_active IS TRUE"),
    )


def downgrade():
    op.drop_index("ix_group_app_access_rule_active", table_name="group_app_access_rule")
    op.drop_index("ix_group_app_access_rule_created_by_user_id", table_name="group_app_access_rule")
    op.drop_index("ix_group_app_access_rule_app_id", table_name="group_app_access_rule")
    op.drop_index("ix_group_app_access_rule_group_id", table_name="group_app_access_rule")
    op.drop_table("group_app_access_rule")

    op.drop_index("ix_external_group_membership_user_external_identity_id", table_name="external_group_membership")
    op.drop_index("ix_external_group_membership_group_id", table_name="external_group_membership")
    op.drop_table("external_group_membership")

    op.drop_index("ix_external_group_active", table_name="external_group")
    op.drop_index("ix_external_group_connection_id", table_name="external_group")
    op.drop_table("external_group")

    op.drop_index("ix_user_external_identity_active", table_name="user_external_identity")
    op.drop_index("ix_user_external_identity_manager_identity_id", table_name="user_external_identity")
    op.drop_index("ix_user_external_identity_connection_id", table_name="user_external_identity")
    op.drop_table("user_external_identity")

    op.drop_index("ix_provisioning_connection_active", table_name="provisioning_connection")
    op.drop_index("uq_provisioning_connection_client_id", table_name="provisioning_connection")
    op.drop_table("provisioning_connection")

    access_role = postgresql.ENUM("VIEWER", "EDITOR", name="group_app_access_role")
    access_role.drop(op.get_bind(), checkfirst=True)
