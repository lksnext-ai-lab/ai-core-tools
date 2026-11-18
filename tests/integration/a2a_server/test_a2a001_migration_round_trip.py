"""End-to-end round-trip test of the real `a2a001_agent_server` migration.

Unlike `tests/integration/test_migration_api_key_hash.py` (which runs a
migration's `upgrade`/`downgrade` through an `Operations` context bound to
the shared `db` fixture's connection), `a2a001` cannot use that pattern: the
`db`/`test_engine` fixtures build their schema from the *current* ORM models
via `Base.metadata.create_all`, which already includes every column, table
and enum label `a2a001` adds (the models were updated alongside the
migration). Running `a2a001.upgrade()` against that schema would immediately
fail with "column already exists" / "type already exists".

Instead, this follows the ephemeral-database + real `alembic` CLI pattern of
`tests/integration/test_useremail001_migration_e2e.py` and this package's own
`test_a2a_schema_matches_sdk.py`: a brand-new database, migrated via the
actual Alembic revision chain (so it starts genuinely one revision behind
`a2a001`, with none of this migration's columns/tables/labels), seeded with
rows that use the new `'A2A'` enum labels and the new link table, then
downgraded and re-upgraded for real.

Requires: the `db_test` docker-compose service on port 5433.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import pytest
from sqlalchemy import create_engine, inspect, text

REPO_ROOT = Path(__file__).resolve().parents[3]

DB_HOST = "localhost"
DB_PORT = "5433"
DB_SUPERUSER = "test_user"
DB_SUPERUSER_PASSWORD = "test_pass"  # pragma: allowlist secret
MAINTENANCE_DB = "test_db"
EPHEMERAL_DB_NAME = "mattin_test_a2a001_round_trip"


def _admin_connection() -> psycopg2.extensions.connection:
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
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )


@pytest.fixture
def ephemeral_db():
    """A brand-new, empty ephemeral Postgres database (no migrations applied yet)."""
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


def _seed_a2a_rows(engine) -> dict:
    """Inserts one App/Agent/Conversation/agent_execution_event/a2a_context_link
    row, each using the new `'A2A'` enum label or the new link table, and
    returns their ids for later assertions.
    """
    with engine.begin() as conn:
        app_id = conn.execute(
            text('INSERT INTO "App" (name, slug) VALUES (:name, :slug) RETURNING app_id'),
            {"name": "a2a001 round-trip app", "slug": "a2a001-round-trip"},
        ).scalar_one()
        agent_id = conn.execute(
            text('INSERT INTO "Agent" (name, app_id, type) VALUES (:name, :app_id, :type) RETURNING agent_id'),
            {"name": "a2a001 round-trip agent", "app_id": app_id, "type": "agent"},
        ).scalar_one()
        conversation_id = conn.execute(
            text(
                'INSERT INTO "Conversation" (agent_id, session_id, source) '
                "VALUES (:agent_id, :session_id, 'A2A') RETURNING conversation_id"
            ),
            {"agent_id": agent_id, "session_id": f"a2a001-round-trip-{uuid.uuid4()}"},
        ).scalar_one()
        event_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO agent_execution_event "
                "(event_id, app_id, agent_id, conversation_id, caller_type, started_at, status) "
                "VALUES (:event_id, :app_id, :agent_id, :conversation_id, 'A2A', :started_at, 'SUCCESS')"
            ),
            {
                "event_id": event_id,
                "app_id": app_id,
                "agent_id": agent_id,
                "conversation_id": conversation_id,
                "started_at": datetime.now(timezone.utc).replace(tzinfo=None),
            },
        )
        link_id = conn.execute(
            text(
                "INSERT INTO a2a_context_link "
                "(app_id, agent_id, conversation_id, api_key_hash, context_id, created_at, updated_at) "
                "VALUES (:app_id, :agent_id, :conversation_id, :api_key_hash, :context_id, now(), now()) "
                "RETURNING id"
            ),
            {
                "app_id": app_id,
                "agent_id": agent_id,
                "conversation_id": conversation_id,
                "api_key_hash": "0" * 64,
                "context_id": "round-trip-context",
            },
        ).scalar_one()
    return {
        "app_id": app_id,
        "agent_id": agent_id,
        "conversation_id": conversation_id,
        "event_id": event_id,
        "link_id": link_id,
    }


def test_a2a001_upgrade_seed_downgrade_upgrade_round_trip(ephemeral_db):
    # 1. Upgrade to head (includes a2a001): starts from nothing, so every a2a001
    #    column/table/enum-label is genuinely newly created here, not already
    #    present the way it would be via Base.metadata.create_all.
    result = _run_alembic("upgrade", "head")
    assert result.returncode == 0, (
        f"alembic upgrade head failed (rc={result.returncode}).\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )

    ids = _seed_a2a_rows(ephemeral_db)

    with ephemeral_db.connect() as conn:
        source = conn.execute(
            text('SELECT source FROM "Conversation" WHERE conversation_id = :id'),
            {"id": ids["conversation_id"]},
        ).scalar_one()
        assert source == "A2A"
        caller_type = conn.execute(
            text("SELECT caller_type FROM agent_execution_event WHERE event_id = :id"),
            {"id": ids["event_id"]},
        ).scalar_one()
        assert caller_type == "A2A"

    # 2. Downgrade to a2a001's parent. An explicit target, not "-1": head is
    #    not necessarily a2a001 (later or merge revisions sit on top of it).
    result = _run_alembic("downgrade", "apikeyhash001")
    assert result.returncode == 0, (
        f"alembic downgrade apikeyhash001 failed (rc={result.returncode}).\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )

    with ephemeral_db.connect() as conn:
        # The seeded Conversation/event rows survive (only the enum label changes
        # on them), since downgrade() rewrites 'A2A' -> the nearest legacy label
        # rather than deleting rows.
        source = conn.execute(
            text('SELECT source FROM "Conversation" WHERE conversation_id = :id'),
            {"id": ids["conversation_id"]},
        ).scalar_one()
        assert source == "API", "a2a001 downgrade must relabel Conversation.source A2A -> API"

        caller_type = conn.execute(
            text("SELECT caller_type FROM agent_execution_event WHERE event_id = :id"),
            {"id": ids["event_id"]},
        ).scalar_one()
        assert caller_type == "PUBLIC_API", (
            "a2a001 downgrade must relabel agent_execution_event.caller_type A2A -> PUBLIC_API"
        )

        inspector = inspect(conn)
        for table in ("a2a_tasks", "a2a_task_events", "a2a_task_versions", "a2a_context_link"):
            assert not inspector.has_table(table), f"{table} must not exist after downgrade"

        agent_columns = {c["name"] for c in inspector.get_columns("Agent")}
        assert not (agent_columns & {
            "a2a_enabled", "a2a_card_visibility", "a2a_name_override",
            "a2a_description_override", "a2a_skill_tags", "a2a_examples",
        }), "Agent must have no a2a_* columns after downgrade"

        for enum_name, expected_labels in (
            ("conversationsource", ["PLAYGROUND", "MARKETPLACE", "API", "SCHEDULED_TASK"]),
            (
                "agent_execution_caller_type",
                ["INTERNAL_PLAYGROUND", "PUBLIC_API", "MCP", "AGENT_AS_TOOL", "SCHEDULED_TASK"],
            ),
        ):
            labels = [
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT enumlabel FROM pg_enum "
                        "JOIN pg_type ON pg_type.oid = pg_enum.enumtypid "
                        "WHERE pg_type.typname = :type_name ORDER BY pg_enum.enumsortorder"
                    ),
                    {"type_name": enum_name},
                ).fetchall()
            ]
            assert labels == expected_labels, f"{enum_name} labels not restored: {labels}"

    # 3. Upgrade again: must succeed cleanly (no leftover `_old` type, no
    #    half-applied state from the downgrade).
    result = _run_alembic("upgrade", "head")
    assert result.returncode == 0, (
        f"alembic upgrade head (2nd time) failed (rc={result.returncode}).\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )

    # 4. AC-41: all three a2a_context_link FKs cascade on delete.
    with ephemeral_db.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT conname, confdeltype FROM pg_constraint "
                "WHERE conrelid = 'a2a_context_link'::regclass AND contype = 'f'"
            )
        ).fetchall()
        assert len(rows) == 3, f"expected 3 FKs on a2a_context_link, found {rows}"
        for _conname, confdeltype in rows:
            assert confdeltype == "c", f"a2a_context_link FK {_conname} is not ON DELETE CASCADE"
