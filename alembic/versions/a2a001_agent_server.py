"""A2A (Agent2Agent protocol) server: Agent exposure columns, enum values,
the pinned a2a-sdk tables, and the Mattin contextId<->Conversation link table.

- Agent gains a2a_enabled, a2a_card_visibility (CHECK 'public'|'api_key'),
  a2a_name_override, a2a_description_override, a2a_skill_tags, a2a_examples,
  plus a partial index for the "which agents in this app are A2A-enabled"
  catalog query (FR-3).
- ConversationSource gains 'A2A' (new conversations created for an A2A
  contextId get source=A2A, per DEV-3) and AgentExecutionCallerType gains
  'A2A' (metrics channel for A2A-triggered executions).
- a2a_context_link (AD-9): the race-safe join between
  (app_id, agent_id, api_key_hash, context_id) and the Conversation created
  for it. All three FKs are ON DELETE CASCADE (AC-41): deleting the app,
  agent or conversation removes the link without the app ever having to
  load it. app_id has no dedicated single-column index: it is already the
  leftmost column of uq_a2a_context_link_owner_ctx, so a separate index
  would be redundant. agent_id and conversation_id each get their own.
- a2a_tasks / a2a_task_events / a2a_task_versions: the pinned
  a2a-sdk==1.2.2 store/stream tables (AD-2), created here -- and only here --
  in the plain `public` schema (DEV-1: the user rejected a dedicated `a2a`
  schema). Their DDL is hard-coded below to exactly mirror what
  `backend/services/a2a_server/sdk_models.get_sdk_metadata()` (the schema
  source of truth; step_002) emits for the SDK's own mixins -- this
  migration deliberately does NOT import that module at runtime, so that a
  broken import can never block a migration run. The schema-drift test
  (`tests/integration/a2a_server/test_a2a_schema_matches_sdk.py`) is what
  catches drift between this hard-coded DDL and the registry after an SDK
  bump. No FKs on these three tables: the SDK does not declare any, and
  owner-prefix lifecycle (app/agent purge, retention) is handled by
  step_018's maintenance worker, not by the database.
- `ix_a2a_tasks_last_updated` is a Mattin-owned addition (not part of the SDK
  mixins) for the retention and stale-task sweeps. It is declared once, as
  the single source of truth, on the registry's own `a2a_tasks` model in
  `services.a2a_server.sdk_models.get_sdk_models()` -- this migration's
  `op.create_index` call for it below must stay in sync with that.

Downgrade notes:
- The two enum additions are undone with Postgres's "rename -> recreate ->
  cast -> drop" dance (NFR-6): Postgres cannot DROP a single enum value.
  Rows using the 'A2A' label are first rewritten to the nearest legacy
  equivalent (Conversation.source='API', agent_execution_event.caller_type=
  'PUBLIC_API'). An assertion query runs before each DROP TYPE to fail
  loudly if any column other than the one known at the time this migration
  was written still references the renamed-away type.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a2a001_agent_server"
down_revision = "apikeyhash001"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Enum downgrade helpers
# ---------------------------------------------------------------------------

def _assert_no_unexpected_type_users(bind, type_name, expected_table, expected_column):
    """Fails loudly if any column other than the expected one still uses `type_name`.

    Called before every `DROP TYPE ... _old`: Postgres itself would refuse the
    drop if a column still depended on it, but this gives a clear, named
    error instead of a generic dependency error, and catches the case where
    some *other* (expected_table, expected_column) pair silently grew a new
    user of the type between when this migration was written and when it
    runs.
    """
    rows = bind.execute(
        sa.text(
            """
            SELECT c.relname, a.attname
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_type t ON t.oid = a.atttypid
            WHERE t.typname = :type_name AND a.attnum > 0 AND NOT a.attisdropped
            """
        ),
        {"type_name": type_name},
    ).fetchall()
    unexpected = [(r[0], r[1]) for r in rows if (r[0], r[1]) != (expected_table, expected_column)]
    if unexpected:
        raise RuntimeError(
            f"a2a001 downgrade: unexpected column(s) still use type {type_name!r}: {unexpected}"
        )


def _recreate_enum_without_a2a(bind, *, type_name, original_labels, table, column, has_default):
    """Postgres cannot DROP a single enum value; recreate the type without it.

    `original_labels` is the exact label list (in original order) the type
    had immediately before this migration's upgrade() ran.
    """
    old_type_name = f"{type_name}_old"
    bind.execute(sa.text(f'ALTER TYPE {type_name} RENAME TO {old_type_name}'))

    labels_sql = ", ".join(f"'{label}'" for label in original_labels)
    bind.execute(sa.text(f"CREATE TYPE {type_name} AS ENUM ({labels_sql})"))

    _assert_no_unexpected_type_users(bind, old_type_name, table, column)

    if has_default:
        bind.execute(sa.text(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" DROP DEFAULT'))
    bind.execute(
        sa.text(
            f'ALTER TABLE "{table}" ALTER COLUMN "{column}" '
            f'TYPE {type_name} USING "{column}"::text::{type_name}'
        )
    )
    if has_default:
        bind.execute(
            sa.text(
                f'ALTER TABLE "{table}" ALTER COLUMN "{column}" '
                f"SET DEFAULT '{original_labels[0]}'::{type_name}"
            )
        )

    bind.execute(sa.text(f"DROP TYPE {old_type_name}"))


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------

def upgrade():
    bind = op.get_bind()

    # --- Agent A2A exposure columns (FR-3) ---------------------------------
    op.add_column("Agent", sa.Column("a2a_enabled", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column(
        "Agent",
        sa.Column("a2a_card_visibility", sa.String(16), nullable=False, server_default="public"),
    )
    op.create_check_constraint(
        "ck_agent_a2a_card_visibility", "Agent", "a2a_card_visibility IN ('public','api_key')"
    )
    op.add_column("Agent", sa.Column("a2a_name_override", sa.String(255), nullable=True))
    op.add_column("Agent", sa.Column("a2a_description_override", sa.Text(), nullable=True))
    op.add_column("Agent", sa.Column("a2a_skill_tags", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("Agent", sa.Column("a2a_examples", sa.JSON(), nullable=False, server_default="[]"))
    op.create_index(
        "ix_agent_a2a_enabled_app",
        "Agent",
        ["app_id"],
        postgresql_where=sa.text("a2a_enabled"),
    )

    # --- Enum values (FR-20, NFR-6) -----------------------------------------
    # IMPORTANT for any future migration: Postgres only lets a session see/use a
    # value added by `ALTER TYPE ... ADD VALUE` once the adding transaction has
    # committed. Any later migration that both adds the 'A2A' label (if it were
    # ever re-added after a downgrade) AND writes rows using it in the SAME
    # transaction would fail with "unsafe use of new value of enum type" on
    # Postgres < 12, and is fragile even on newer versions if Alembic batches
    # multiple migrations into one transaction. Keep `ADD VALUE` and any
    # subsequent data write that uses the new label in separate migrations (or at
    # minimum ensure the `ADD VALUE` statement's transaction commits first).
    op.execute("ALTER TYPE conversationsource ADD VALUE IF NOT EXISTS 'A2A'")
    op.execute("ALTER TYPE agent_execution_caller_type ADD VALUE IF NOT EXISTS 'A2A'")

    # --- a2a_context_link (AD-9, AC-41) -------------------------------------
    op.create_table(
        "a2a_context_link",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "app_id",
            sa.Integer(),
            sa.ForeignKey("App.app_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.Integer(),
            sa.ForeignKey("Agent.agent_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            sa.Integer(),
            sa.ForeignKey("Conversation.conversation_id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("api_key_hash", sa.String(64), nullable=False),
        sa.Column("context_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "app_id", "agent_id", "api_key_hash", "context_id", name="uq_a2a_context_link_owner_ctx"
        ),
    )
    # No separate index on app_id: it is already the leftmost column of
    # uq_a2a_context_link_owner_ctx, so a dedicated single-column index would
    # be redundant (Postgres can serve an app_id-only lookup from that
    # constraint's index too). agent_id and conversation_id are not leftmost
    # in that constraint, so each needs its own index.
    op.create_index("ix_a2a_context_link_agent_id", "a2a_context_link", ["agent_id"])
    op.create_index("ix_a2a_context_link_conversation_id", "a2a_context_link", ["conversation_id"])
    op.create_index("ix_a2a_context_link_updated_at", "a2a_context_link", ["updated_at"])

    # --- a2a-sdk 1.2.2 tables (AD-2) -----------------------------------------
    # DDL hard-coded to exactly mirror services.a2a_server.sdk_models.get_sdk_metadata();
    # see the module docstring for why this migration does not import it at runtime.
    op.create_table(
        "a2a_tasks",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("context_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("owner", sa.String(255), nullable=True),
        sa.Column("last_updated", sa.DateTime(), nullable=True),
        sa.Column("status", sa.JSON(), nullable=False),
        sa.Column("artifacts", sa.JSON(), nullable=True),
        sa.Column("history", sa.JSON(), nullable=True),
        sa.Column("protocol_version", sa.String(16), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_a2a_tasks_id", "a2a_tasks", ["id"])
    op.create_index("idx_a2a_tasks_owner_last_updated", "a2a_tasks", ["owner", "last_updated"])
    # Mattin-owned extra (not part of the SDK mixins): retention + stale-task sweeps (step_018).
    op.create_index("ix_a2a_tasks_last_updated", "a2a_tasks", ["last_updated"])

    op.create_table(
        "a2a_task_events",
        sa.Column("seq", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("owner", sa.String(255), nullable=True),
        sa.Column("task_version", sa.BigInteger(), nullable=False),
        sa.Column("event_data", sa.LargeBinary(), nullable=False),
        sa.PrimaryKeyConstraint("seq"),
    )
    op.create_index("ix_a2a_task_events_task_id", "a2a_task_events", ["task_id"])

    op.create_table(
        "a2a_task_versions",
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("owner", sa.String(255), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("task_id"),
    )


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------

def downgrade():
    bind = op.get_bind()

    # --- a2a-sdk tables ------------------------------------------------------
    op.drop_table("a2a_task_versions")
    op.drop_index("ix_a2a_task_events_task_id", table_name="a2a_task_events")
    op.drop_table("a2a_task_events")
    op.drop_index("ix_a2a_tasks_last_updated", table_name="a2a_tasks")
    op.drop_index("idx_a2a_tasks_owner_last_updated", table_name="a2a_tasks")
    op.drop_index("ix_a2a_tasks_id", table_name="a2a_tasks")
    op.drop_table("a2a_tasks")

    # --- a2a_context_link ----------------------------------------------------
    op.drop_index("ix_a2a_context_link_updated_at", table_name="a2a_context_link")
    op.drop_index("ix_a2a_context_link_conversation_id", table_name="a2a_context_link")
    op.drop_index("ix_a2a_context_link_agent_id", table_name="a2a_context_link")
    op.drop_table("a2a_context_link")

    # --- Enum values (NFR-6): rewrite rows away from 'A2A', then recreate the
    # type without it. Original label lists taken from the migrations that
    # created/last touched each type (cb4e00ec0e72, periodic004, metrics002,
    # periodic005) -- no earlier migration touches them again before this one.
    op.execute('UPDATE "Conversation" SET source = \'API\' WHERE source = \'A2A\'')
    _recreate_enum_without_a2a(
        bind,
        type_name="conversationsource",
        original_labels=["PLAYGROUND", "MARKETPLACE", "API", "SCHEDULED_TASK"],
        table="Conversation",
        column="source",
        has_default=True,
    )

    op.execute(
        "UPDATE agent_execution_event SET caller_type = 'PUBLIC_API' WHERE caller_type = 'A2A'"
    )
    _recreate_enum_without_a2a(
        bind,
        type_name="agent_execution_caller_type",
        original_labels=["INTERNAL_PLAYGROUND", "PUBLIC_API", "MCP", "AGENT_AS_TOOL", "SCHEDULED_TASK"],
        table="agent_execution_event",
        column="caller_type",
        has_default=False,
    )

    # --- Agent A2A exposure columns ------------------------------------------
    op.drop_index("ix_agent_a2a_enabled_app", table_name="Agent")
    op.drop_column("Agent", "a2a_examples")
    op.drop_column("Agent", "a2a_skill_tags")
    op.drop_column("Agent", "a2a_description_override")
    op.drop_column("Agent", "a2a_name_override")
    op.drop_constraint("ck_agent_a2a_card_visibility", "Agent", type_="check")
    op.drop_column("Agent", "a2a_card_visibility")
    op.drop_column("Agent", "a2a_enabled")
