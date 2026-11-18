"""App flexible Chat: Agent.kind marker, INTERNAL_CHAT enum values and Chat tables.

- Agent.kind ('standard' | 'internal_chat') + ck_agent_kind, the DB-level
  "never exposed" CHECK (ck_agent_internal_chat_unexposed) and a partial
  unique index (one internal chat agent per App).
- conversationsource / agent_execution_caller_type gain 'INTERNAL_CHAT'
  (no row written in this migration uses the new label; see a2a001 note on
  ADD VALUE and same-transaction use). ApprovalChannel is a String column:
  Python-only change.
- New tables conversation_turn, chat_user_default, chat_conversation_state.

Downgrade: drops the tables; deletes INTERNAL_CHAT conversations and the
internal chat agents (hitl_approval / agent_execution_event / Conversation FKs
to Agent are ON DELETE CASCADE) -- DATA LOSS for chat history, by design,
since the agent that owns it stops existing; relabels any remaining
agent_execution_event INTERNAL_CHAT -> INTERNAL_PLAYGROUND and recreates both
enum types without the label.

The downgrade also purges what the internal chat agents left behind, so nothing
becomes visible to the old code: their hidden temp repositories
(``_playground_{agent_id}_...``, matched by EXACT prefix), the temp silos, the
metadata output parsers of those silos, the PGVector rows of the ``silo_{id}``
collections and the LangGraph checkpoint rows of the conversations' threads (deleted by exact thread id; a thread whose
conversation row is already gone is left, to avoid scanning the checkpoint tables). If
any of those silos lives in Qdrant the downgrade REFUSES (RuntimeError): delete
those collections first, then downgrade again. The purge is idempotent.

Operational notes: the downgrade rewrites "Conversation" and agent_execution_event
(column type change) under ACCESS EXCLUSIVE locks -- run it in a maintenance
window. It does NOT delete uploaded files on disk that belong to the deleted chat
conversations.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "ichat001"
down_revision = "chatfiltmerge003"
branch_labels = None
depends_on = None


def _assert_no_unexpected_type_users(bind, type_name, expected_table, expected_column):
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
            f"ichat001 downgrade: unexpected column(s) still use type {type_name!r}: {unexpected}"
        )


def _recreate_enum_without_label(bind, *, type_name, original_labels, table, column, has_default):
    """Postgres cannot DROP a single enum value; recreate the type without it."""
    old_type_name = f"{type_name}_old"
    bind.execute(sa.text(f"ALTER TYPE {type_name} RENAME TO {old_type_name}"))
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


def _table_exists(bind, name):
    return bind.execute(sa.text("SELECT to_regclass(:n)"), {"n": name}).scalar() is not None


def _purge_internal_agent_leftovers(bind):
    """Remove the temp repositories / silos / parsers / vectors / checkpoints of every internal chat agent."""
    agent_ids = [r[0] for r in bind.execute(sa.text("SELECT agent_id FROM \"Agent\" WHERE kind = 'internal_chat'"))]
    if not agent_ids:
        return
    # Exact-prefix match: ``_`` is a LIKE wildcard (agent 3 would also match 30-39, 300-399...).
    repos = bind.execute(
        sa.text(
            'SELECT r.repository_id, r.silo_id FROM "Repository" r '
            'JOIN "Agent" a ON a.kind = \'internal_chat\' AND a.app_id = r.app_id '
            "WHERE r.type = 'playground_media' "
            "AND left(r.name, length('_playground_' || a.agent_id || '_')) = '_playground_' || a.agent_id || '_'"
        )
    ).fetchall()
    repo_ids = sorted({r[0] for r in repos})
    silo_ids = sorted({r[1] for r in repos if r[1] is not None})
    if silo_ids:
        qdrant = bind.execute(
            sa.text('SELECT silo_id FROM "Silo" WHERE silo_id = ANY(:ids) AND upper(coalesce(vector_db_type, \'\')) = \'QDRANT\''),
            {"ids": silo_ids},
        ).fetchall()
        if qdrant:
            raise RuntimeError(
                "ichat001 downgrade refused: the chat temp silos "
                f"{sorted(r[0] for r in qdrant)} are stored in Qdrant. Delete their collections "
                "(silo_<id>) first, then run the downgrade again."
            )
        names = [f"silo_{i}" for i in silo_ids]
        if _table_exists(bind, "langchain_pg_collection") and _table_exists(bind, "langchain_pg_embedding"):
            bind.execute(
                sa.text(
                    "DELETE FROM langchain_pg_embedding WHERE collection_id IN "
                    "(SELECT uuid FROM langchain_pg_collection WHERE name = ANY(:n))"
                ),
                {"n": names},
            )
            bind.execute(sa.text("DELETE FROM langchain_pg_collection WHERE name = ANY(:n)"), {"n": names})
    parser_ids = []
    if silo_ids:
        parser_ids = [
            r[0] for r in bind.execute(
                sa.text('SELECT metadata_definition_id FROM "Silo" WHERE silo_id = ANY(:ids) '
                        "AND metadata_definition_id IS NOT NULL"), {"ids": silo_ids})
        ]
    if repo_ids:
        bind.execute(sa.text('DELETE FROM "Media" WHERE repository_id = ANY(:r) OR silo_id = ANY(:s)'),
                     {"r": repo_ids, "s": silo_ids or [0]})
        bind.execute(sa.text('DELETE FROM "Resource" WHERE repository_id = ANY(:r)'), {"r": repo_ids})
        bind.execute(sa.text('DELETE FROM "Folder" WHERE repository_id = ANY(:r)'), {"r": repo_ids})
        bind.execute(sa.text('DELETE FROM "Repository" WHERE repository_id = ANY(:r)'), {"r": repo_ids})
    if silo_ids:
        bind.execute(sa.text('DELETE FROM "Silo" WHERE silo_id = ANY(:ids)'), {"ids": silo_ids})
    if parser_ids:
        bind.execute(sa.text('DELETE FROM "OutputParser" WHERE parser_id = ANY(:ids)'), {"ids": sorted(set(parser_ids))})
    # LangGraph checkpoint rows of the internal agents' threads, by EXACT thread id (``thread_{agent_id}_{session_id}``
    # built from their Conversation rows, plus the agent-wide ``thread_{agent_id}``): equality uses the leading key of
    # the checkpoint primary keys, so there is no scan of the (large) checkpoint tables while ACCESS EXCLUSIVE locks
    # are held. A thread whose Conversation row is already gone is NOT matched by a ``LIKE 'thread\_<id>\_%'`` sweep:
    # that cannot use the index under a non-C collation (it would scan every checkpoint table), so such leftover rows
    # of an internal agent stay behind (they are unreachable for the old code: no agent has that id any more).
    thread_ids = [
        r[0] for r in bind.execute(sa.text(
            "SELECT 'thread_' || c.agent_id || '_' || c.session_id FROM \"Conversation\" c "
            "JOIN \"Agent\" a ON a.agent_id = c.agent_id WHERE a.kind = 'internal_chat'"
        ))
    ] + [f"thread_{agent_id}" for agent_id in agent_ids]
    for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
        if _table_exists(bind, table):
            for start in range(0, len(thread_ids), 1000):
                bind.execute(
                    sa.text(f"DELETE FROM {table} WHERE thread_id = ANY(:ids)"),
                    {"ids": thread_ids[start:start + 1000]},
                )


def upgrade():
    # --- Agent.kind + constraints + partial unique index --------------------
    op.add_column(
        "Agent", sa.Column("kind", sa.String(32), nullable=False, server_default="standard")
    )
    op.create_check_constraint("ck_agent_kind", "Agent", "kind IN ('standard','internal_chat')")
    op.create_check_constraint(
        "ck_agent_internal_chat_unexposed",
        "Agent",
        "kind <> 'internal_chat' OR (is_tool IS NOT TRUE AND a2a_enabled = false "
        "AND marketplace_visibility = 'UNPUBLISHED' AND enable_code_interpreter = false)",
    )
    op.create_check_constraint(
        "ck_agent_internal_chat_has_app", "Agent", "kind <> 'internal_chat' OR app_id IS NOT NULL"
    )
    op.create_index(
        "uq_agent_internal_chat_per_app",
        "Agent",
        ["app_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'internal_chat'"),
    )

    # --- Enum values --------------------------------------------------------
    op.execute("ALTER TYPE conversationsource ADD VALUE IF NOT EXISTS 'INTERNAL_CHAT'")
    op.execute("ALTER TYPE agent_execution_caller_type ADD VALUE IF NOT EXISTS 'INTERNAL_CHAT'")

    # --- Tables ---------------------------------------------------------------
    op.create_table(
        "conversation_turn",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "conversation_id", sa.Integer(),
            sa.ForeignKey("Conversation.conversation_id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("app_id", sa.Integer(), sa.ForeignKey("App.app_id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("User.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("assistant_message_id", sa.String(128), nullable=True),
        sa.Column("execution_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ai_service_id", sa.Integer(), nullable=True),
        sa.Column("ai_service_name", sa.String(255), nullable=False),
        sa.Column("ai_model_name", sa.String(255), nullable=True),
        sa.Column("silo_id", sa.Integer(), nullable=True),
        sa.Column("silo_name", sa.String(255), nullable=True),
        sa.Column("silo_source_type", sa.String(32), nullable=True),
        sa.Column("skills", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("mcp_configs", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("conversation_id", "turn_index", name="uq_conversation_turn_conversation_index"),
    )
    op.create_index("ix_conversation_turn_app_id", "conversation_turn", ["app_id"])
    op.create_index(
        "ix_conversation_turn_user_id", "conversation_turn", ["user_id"],
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )

    op.create_table(
        "chat_user_default",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("User.user_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("app_id", sa.Integer(), sa.ForeignKey("App.app_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("selection", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_chat_user_default_app_id", "chat_user_default", ["app_id"])

    op.create_table(
        "chat_conversation_state",
        sa.Column(
            "conversation_id", sa.Integer(),
            sa.ForeignKey("Conversation.conversation_id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column("app_id", sa.Integer(), sa.ForeignKey("App.app_id", ondelete="CASCADE"), nullable=False),
        sa.Column("selection", sa.JSON(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_chat_conversation_state_app_id", "chat_conversation_state", ["app_id"])


def downgrade():
    bind = op.get_bind()

    op.drop_index("ix_chat_conversation_state_app_id", table_name="chat_conversation_state")
    op.drop_table("chat_conversation_state")
    op.drop_index("ix_chat_user_default_app_id", table_name="chat_user_default")
    op.drop_table("chat_user_default")
    op.drop_index("ix_conversation_turn_user_id", table_name="conversation_turn")
    op.drop_index("ix_conversation_turn_app_id", table_name="conversation_turn")
    op.drop_table("conversation_turn")

    _purge_internal_agent_leftovers(bind)

    # Conversations of the internal chat agent, then the agent itself. Its
    # hitl_approval / agent_execution_event / Conversation rows go by FK cascade.
    op.execute("DELETE FROM \"Conversation\" WHERE source = 'INTERNAL_CHAT'")
    # Association tables whose FKs to Agent have no ON DELETE would abort the delete.
    op.execute(
        "DELETE FROM agent_skills WHERE agent_id IN (SELECT agent_id FROM \"Agent\" WHERE kind = 'internal_chat')"
    )
    op.execute(
        "DELETE FROM agent_mcps WHERE agent_id IN (SELECT agent_id FROM \"Agent\" WHERE kind = 'internal_chat')"
    )
    op.execute(
        "DELETE FROM agent_tools WHERE agent_id IN (SELECT agent_id FROM \"Agent\" WHERE kind = 'internal_chat') "
        "OR tool_id IN (SELECT agent_id FROM \"Agent\" WHERE kind = 'internal_chat')"
    )
    op.execute("DELETE FROM \"Agent\" WHERE kind = 'internal_chat'")

    op.execute(
        "UPDATE agent_execution_event SET caller_type = 'INTERNAL_PLAYGROUND' "
        "WHERE caller_type = 'INTERNAL_CHAT'"
    )
    _recreate_enum_without_label(
        bind,
        type_name="conversationsource",
        original_labels=["PLAYGROUND", "MARKETPLACE", "API", "SCHEDULED_TASK", "A2A"],
        table="Conversation",
        column="source",
        has_default=True,
    )
    _recreate_enum_without_label(
        bind,
        type_name="agent_execution_caller_type",
        original_labels=["INTERNAL_PLAYGROUND", "PUBLIC_API", "MCP", "AGENT_AS_TOOL", "SCHEDULED_TASK", "A2A"],
        table="agent_execution_event",
        column="caller_type",
        has_default=False,
    )

    op.drop_index("uq_agent_internal_chat_per_app", table_name="Agent")
    op.drop_constraint("ck_agent_internal_chat_has_app", "Agent", type_="check")
    op.drop_constraint("ck_agent_internal_chat_unexposed", "Agent", type_="check")
    op.drop_constraint("ck_agent_kind", "Agent", type_="check")
    op.drop_column("Agent", "kind")
