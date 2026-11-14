"""Round-trip test of the real `ichat001` migration (flexible App Chat schema).

Same ephemeral-database + real `alembic` CLI pattern as
`tests/integration/a2a_server/test_a2a001_migration_round_trip.py`: the shared
`db` fixture builds its schema from the ORM models (which already contain
everything ichat001 adds), so it cannot exercise the migration itself.

Requires: the `db_test` docker-compose service on port 5433.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg2
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

REPO_ROOT = Path(__file__).resolve().parents[2]

DB_HOST = "localhost"
DB_PORT = "5433"
DB_SUPERUSER = "test_user"
DB_SUPERUSER_PASSWORD = "test_pass"  # pragma: allowlist secret
MAINTENANCE_DB = "test_db"
EPHEMERAL_DB_NAME = "mattin_test_ichat001_round_trip"
PARENT_REVISION = "chatfiltmerge003"

NEW_TABLES = ("conversation_turn", "chat_user_default", "chat_conversation_state")


def _admin_connection():
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_SUPERUSER, password=DB_SUPERUSER_PASSWORD, dbname=MAINTENANCE_DB
    )
    conn.autocommit = True
    return conn


def _drop_ephemeral_db() -> None:
    conn = _admin_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{EPHEMERAL_DB_NAME}" WITH (FORCE)')
    finally:
        conn.close()


def _create_ephemeral_db() -> None:
    _drop_ephemeral_db()
    conn = _admin_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE DATABASE "{EPHEMERAL_DB_NAME}"')
    finally:
        conn.close()


def _run_alembic(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(
        DATABASE_USER=DB_SUPERUSER,
        DATABASE_PASSWORD=DB_SUPERUSER_PASSWORD,
        DATABASE_HOST=DB_HOST,
        DATABASE_PORT=DB_PORT,
        DATABASE_NAME=EPHEMERAL_DB_NAME,
    )
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=300,
    )


def _alembic_ok(*args: str) -> None:
    result = _run_alembic(*args)
    assert result.returncode == 0, (
        f"alembic {' '.join(args)} failed (rc={result.returncode}).\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )


@pytest.fixture
def ephemeral_db():
    _create_ephemeral_db()
    engine = None
    try:
        url = f"postgresql://{DB_SUPERUSER}:{DB_SUPERUSER_PASSWORD}@{DB_HOST}:{DB_PORT}/{EPHEMERAL_DB_NAME}"
        engine = create_engine(url, pool_pre_ping=True)
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        _drop_ephemeral_db()


def _enum_labels(conn, type_name: str) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
            text(
                "SELECT enumlabel FROM pg_enum JOIN pg_type ON pg_type.oid = pg_enum.enumtypid "
                "WHERE pg_type.typname = :t ORDER BY pg_enum.enumsortorder"
            ),
            {"t": type_name},
        ).fetchall()
    ]


def _insert_agent(conn, app_id: int, name: str, kind: str | None = None, **extra) -> int:
    cols = {"name": name, "app_id": app_id, "type": "agent", **extra}
    if kind is not None:
        cols["kind"] = kind
    names = ", ".join(cols)
    params = ", ".join(f":{c}" for c in cols)
    return conn.execute(
        text(f'INSERT INTO "Agent" ({names}) VALUES ({params}) RETURNING agent_id'), cols
    ).scalar_one()


def test_ichat001_upgrade_constraints_downgrade_upgrade(ephemeral_db):
    # Start one revision behind ichat001, seed a pre-existing agent.
    _alembic_ok("upgrade", PARENT_REVISION)
    with ephemeral_db.begin() as conn:
        app_id = conn.execute(
            text('INSERT INTO "App" (name, slug) VALUES (:n, :s) RETURNING app_id'),
            {"n": "ichat001 app", "s": "ichat001-app"},
        ).scalar_one()
        legacy_agent_id = _insert_agent(conn, app_id, "legacy agent")

    _alembic_ok("upgrade", "ichat001")

    with ephemeral_db.connect() as conn:
        inspector = inspect(conn)
        assert "kind" in {c["name"] for c in inspector.get_columns("Agent")}
        for table in NEW_TABLES:
            assert inspector.has_table(table), f"{table} missing after upgrade"
        assert "uq_agent_internal_chat_per_app" in {i["name"] for i in inspector.get_indexes("Agent")}
        generation = next(c for c in inspector.get_columns("chat_conversation_state") if c["name"] == "generation")
        assert generation["nullable"] is False
        assert conn.execute(
            text('SELECT kind FROM "Agent" WHERE agent_id = :i'), {"i": legacy_agent_id}
        ).scalar_one() == "standard"
        assert "INTERNAL_CHAT" in _enum_labels(conn, "conversationsource")
        assert "INTERNAL_CHAT" in _enum_labels(conn, "agent_execution_caller_type")

    # Constraints: one internal chat agent per App, plus the CHECKs.
    with ephemeral_db.begin() as conn:
        internal_id = _insert_agent(conn, app_id, "__internal_chat__", kind="internal_chat")

    # A second internal chat agent in the same App violates the partial unique index.
    with pytest.raises(IntegrityError):
        with ephemeral_db.begin() as conn:
            _insert_agent(conn, app_id, "__internal_chat_2__", kind="internal_chat")

    # An exposed internal chat agent violates the CHECK (is_tool / a2a_enabled / visibility).
    with ephemeral_db.begin() as conn:
        other_app = conn.execute(
            text('INSERT INTO "App" (name, slug) VALUES (:n, :s) RETURNING app_id'),
            {"n": "ichat001 app 2", "s": "ichat001-app-2"},
        ).scalar_one()
    for column, value in (
        ("is_tool", True), ("a2a_enabled", True), ("marketplace_visibility", "PUBLIC"),
        ("enable_code_interpreter", True),
    ):
        with pytest.raises(IntegrityError):
            with ephemeral_db.begin() as conn:
                _insert_agent(conn, other_app, "exposed", kind="internal_chat", **{column: value})

    # An internal chat agent must belong to an App (NULL app_id would dodge the unique index).
    with pytest.raises(IntegrityError):
        with ephemeral_db.begin() as conn:
            conn.execute(
                text('INSERT INTO "Agent" (name, type, kind) VALUES (\'no app\', \'agent\', \'internal_chat\')')
            )

    # Invalid kind value violates ck_agent_kind.
    with pytest.raises(IntegrityError):
        with ephemeral_db.begin() as conn:
            _insert_agent(conn, other_app, "bad kind", kind="weird")

    # An UPDATE that tries to expose the existing internal agent also fails.
    with pytest.raises(IntegrityError):
        with ephemeral_db.begin() as conn:
            conn.execute(
                text('UPDATE "Agent" SET is_tool = true WHERE agent_id = :i'), {"i": internal_id}
            )

    # Seed an INTERNAL_CHAT conversation, an execution event and Chat rows.
    with ephemeral_db.begin() as conn:
        conv_id = conn.execute(
            text(
                'INSERT INTO "Conversation" (agent_id, session_id, source) '
                "VALUES (:a, :s, 'INTERNAL_CHAT') RETURNING conversation_id"
            ),
            {"a": internal_id, "s": f"ichat001-{uuid.uuid4()}"},
        ).scalar_one()
        std_conv_id = conn.execute(
            text(
                'INSERT INTO "Conversation" (agent_id, session_id, source) '
                "VALUES (:a, :s, 'PLAYGROUND') RETURNING conversation_id"
            ),
            {"a": legacy_agent_id, "s": f"ichat001-{uuid.uuid4()}"},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO agent_execution_event "
                "(event_id, app_id, agent_id, conversation_id, caller_type, started_at, status) "
                "VALUES (:e, :app, :a, :c, 'INTERNAL_CHAT', now(), 'SUCCESS')"
            ),
            {"e": uuid.uuid4(), "app": app_id, "a": legacy_agent_id, "c": std_conv_id},
        )
        conn.execute(
            text(
                "INSERT INTO conversation_turn (conversation_id, app_id, turn_index, ai_service_name, created_at) "
                "VALUES (:c, :app, 1, 'svc', now())"
            ),
            {"c": conv_id, "app": app_id},
        )
        conn.execute(
            text(
                "INSERT INTO chat_conversation_state (conversation_id, app_id, selection, updated_at) "
                "VALUES (:c, :app, '{}', now())"
            ),
            {"c": conv_id, "app": app_id},
        )
    # Rows that downgrade must clear before deleting the internal agent: an association row
    # whose FK to Agent has no ON DELETE, and an execution event of the internal agent.
    with ephemeral_db.begin() as conn:
        skill_id = conn.execute(
            text("INSERT INTO \"Skill\" (name, content) VALUES ('s', 'c') RETURNING skill_id")
        ).scalar_one()
        conn.execute(
            text("INSERT INTO agent_skills (agent_id, skill_id) VALUES (:a, :s)"),
            {"a": internal_id, "s": skill_id},
        )
        internal_event_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO agent_execution_event "
                "(event_id, app_id, agent_id, conversation_id, caller_type, started_at, status) "
                "VALUES (:e, :app, :a, :c, 'INTERNAL_CHAT', now(), 'SUCCESS')"
            ),
            {"e": internal_event_id, "app": app_id, "a": internal_id, "c": conv_id},
        )

    # Cascades: user delete -> defaults row removed, turn.user_id nulled; conversation delete
    # -> turn/state rows removed; app delete -> all three tables' rows removed.
    with ephemeral_db.begin() as conn:
        user_id = conn.execute(
            text("INSERT INTO \"User\" (email) VALUES ('ichat001@example.com') RETURNING user_id")
        ).scalar_one()
        conv_b = conn.execute(
            text(
                'INSERT INTO "Conversation" (agent_id, session_id, source) '
                "VALUES (:a, :s, 'INTERNAL_CHAT') RETURNING conversation_id"
            ),
            {"a": internal_id, "s": f"ichat001-{uuid.uuid4()}"},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO conversation_turn (conversation_id, app_id, user_id, turn_index, ai_service_name, created_at) "
                "VALUES (:c, :app, :u, 1, 'svc', now())"
            ),
            {"c": conv_b, "app": app_id, "u": user_id},
        )
        conn.execute(
            text(
                "INSERT INTO chat_conversation_state (conversation_id, app_id, selection, updated_at) "
                "VALUES (:c, :app, '{}', now())"
            ),
            {"c": conv_b, "app": app_id},
        )
        conn.execute(
            text(
                "INSERT INTO chat_user_default (user_id, app_id, selection, updated_at) "
                "VALUES (:u, :app, '{}', now())"
            ),
            {"u": user_id, "app": app_id},
        )
    with ephemeral_db.begin() as conn:
        conn.execute(text('DELETE FROM "User" WHERE user_id = :u'), {"u": user_id})
        assert conn.execute(
            text("SELECT count(*) FROM chat_user_default WHERE user_id = :u"), {"u": user_id}
        ).scalar_one() == 0
        assert conn.execute(
            text("SELECT user_id FROM conversation_turn WHERE conversation_id = :c"), {"c": conv_b}
        ).scalar_one() is None
        conn.execute(text('DELETE FROM "Conversation" WHERE conversation_id = :c'), {"c": conv_b})
        for table in ("conversation_turn", "chat_conversation_state"):
            assert conn.execute(
                text(f"SELECT count(*) FROM {table} WHERE conversation_id = :c"), {"c": conv_b}
            ).scalar_one() == 0
    with ephemeral_db.begin() as conn:
        # App delete cascades through the chat tables (done on a scratch App, not the seeded one).
        scratch_app = conn.execute(
            text('INSERT INTO "App" (name, slug) VALUES (\'scratch\', \'ichat001-scratch\') RETURNING app_id')
        ).scalar_one()
        scratch_agent = _insert_agent(conn, scratch_app, "__internal_chat__", kind="internal_chat")
        scratch_conv = conn.execute(
            text(
                'INSERT INTO "Conversation" (agent_id, session_id, source) '
                "VALUES (:a, :s, 'INTERNAL_CHAT') RETURNING conversation_id"
            ),
            {"a": scratch_agent, "s": f"ichat001-{uuid.uuid4()}"},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO conversation_turn (conversation_id, app_id, turn_index, ai_service_name, created_at) "
                "VALUES (:c, :app, 1, 'svc', now())"
            ),
            {"c": scratch_conv, "app": scratch_app},
        )
        conn.execute(
            text(
                "INSERT INTO chat_conversation_state (conversation_id, app_id, selection, updated_at) "
                "VALUES (:c, :app, '{}', now())"
            ),
            {"c": scratch_conv, "app": scratch_app},
        )
        # Detach the FK chain the ORM would normally clear: delete conversations/agent first, then the App.
        conn.execute(text("DELETE FROM chat_conversation_state WHERE app_id = :a"), {"a": scratch_app})
        conn.execute(text("DELETE FROM conversation_turn WHERE app_id = :a"), {"a": scratch_app})
        conn.execute(text('DELETE FROM "Conversation" WHERE conversation_id = :c'), {"c": scratch_conv})
        conn.execute(text('DELETE FROM "Agent" WHERE agent_id = :a'), {"a": scratch_agent})
        conn.execute(text('DELETE FROM "App" WHERE app_id = :a'), {"a": scratch_app})

    # (conversation_id, turn_index) is unique.
    with pytest.raises(IntegrityError):
        with ephemeral_db.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO conversation_turn (conversation_id, app_id, turn_index, ai_service_name, created_at) "
                    "VALUES (:c, :app, 1, 'svc', now())"
                ),
                {"c": conv_id, "app": app_id},
            )

    # Downgrade one revision.
    _alembic_ok("downgrade", PARENT_REVISION)

    with ephemeral_db.connect() as conn:
        inspector = inspect(conn)
        assert "kind" not in {c["name"] for c in inspector.get_columns("Agent")}
        for table in NEW_TABLES:
            assert not inspector.has_table(table), f"{table} must not exist after downgrade"
        assert "uq_agent_internal_chat_per_app" not in {i["name"] for i in inspector.get_indexes("Agent")}
        checks = {c["name"] for c in inspector.get_check_constraints("Agent")}
        assert not ({"ck_agent_kind", "ck_agent_internal_chat_unexposed"} & checks)
        assert _enum_labels(conn, "conversationsource") == [
            "PLAYGROUND", "MARKETPLACE", "API", "SCHEDULED_TASK", "A2A",
        ]
        assert _enum_labels(conn, "agent_execution_caller_type") == [
            "INTERNAL_PLAYGROUND", "PUBLIC_API", "MCP", "AGENT_AS_TOOL", "SCHEDULED_TASK", "A2A",
        ]
        # Internal agent + its INTERNAL_CHAT conversation are gone; the standard ones survive.
        assert conn.execute(
            text('SELECT count(*) FROM "Agent" WHERE agent_id = :i'), {"i": internal_id}
        ).scalar_one() == 0
        assert conn.execute(
            text('SELECT count(*) FROM "Conversation" WHERE conversation_id = :i'), {"i": conv_id}
        ).scalar_one() == 0
        assert conn.execute(
            text('SELECT count(*) FROM "Agent" WHERE agent_id = :i'), {"i": legacy_agent_id}
        ).scalar_one() == 1
        assert conn.execute(
            text('SELECT count(*) FROM "Conversation" WHERE conversation_id = :i'), {"i": std_conv_id}
        ).scalar_one() == 1
        assert conn.execute(
            text("SELECT count(*) FROM agent_execution_event WHERE event_id = :e"), {"e": internal_event_id}
        ).scalar_one() == 0
        assert "PLAYGROUND" in conn.execute(
            text(
                "SELECT column_default FROM information_schema.columns "
                "WHERE table_name = 'Conversation' AND column_name = 'source'"
            )
        ).scalar_one()
        assert conn.execute(
            text("SELECT count(*) FROM pg_type WHERE typname LIKE '%\\_old' ESCAPE '\\'")
        ).scalar_one() == 0
        # The surviving event that used INTERNAL_CHAT was relabelled.
        assert conn.execute(
            text("SELECT caller_type FROM agent_execution_event WHERE conversation_id = :c"),
            {"c": std_conv_id},
        ).scalar_one() == "INTERNAL_PLAYGROUND"

    # Upgrade again: clean re-apply (no leftover _old types).
    _alembic_ok("upgrade", "ichat001")
    with ephemeral_db.connect() as conn:
        inspector = inspect(conn)
        assert "kind" in {c["name"] for c in inspector.get_columns("Agent")}
        for table in NEW_TABLES:
            assert inspector.has_table(table)
        assert conn.execute(
            text('SELECT kind FROM "Agent" WHERE agent_id = :i'), {"i": legacy_agent_id}
        ).scalar_one() == "standard"
