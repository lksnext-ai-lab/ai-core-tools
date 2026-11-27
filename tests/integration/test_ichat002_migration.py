"""Round-trip test of the real `ichat002` migration (Chat busy marker + App default embedding service).

Same ephemeral-database + real `alembic` CLI pattern as
`tests/integration/a2a_server/test_a2a001_migration_round_trip.py`: the shared
`db` fixture builds its schema from the ORM models (which already contain
everything ichat002 adds), so it cannot exercise the migration itself.

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

REPO_ROOT = Path(__file__).resolve().parents[2]

DB_HOST = "localhost"
DB_PORT = "5433"
DB_SUPERUSER = "test_user"
DB_SUPERUSER_PASSWORD = "test_pass"  # pragma: allowlist secret
MAINTENANCE_DB = "test_db"
EPHEMERAL_DB_NAME = "mattin_test_ichat002_round_trip"
PARENT_REVISION = "ichat001"


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


def _fk(inspector, table, name):
    return next((f for f in inspector.get_foreign_keys(table) if f["name"] == name), None)


def test_ichat002_upgrade_downgrade_upgrade(ephemeral_db):
    _alembic_ok("upgrade", PARENT_REVISION)
    with ephemeral_db.begin() as conn:
        app_id = conn.execute(
            text('INSERT INTO "App" (name, slug) VALUES (:n, :s) RETURNING app_id'),
            {"n": "ichat002 app", "s": "ichat002-app"},
        ).scalar_one()
        agent_id = conn.execute(
            text('INSERT INTO "Agent" (name, app_id, type) VALUES (\'a\', :a, \'agent\') RETURNING agent_id'),
            {"a": app_id},
        ).scalar_one()
        conv_id = conn.execute(
            text(
                'INSERT INTO "Conversation" (agent_id, session_id, source) '
                "VALUES (:a, :s, 'PLAYGROUND') RETURNING conversation_id"
            ),
            {"a": agent_id, "s": f"ichat002-{uuid.uuid4()}"},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO chat_conversation_state (conversation_id, app_id, selection, updated_at) "
                "VALUES (:c, :app, '{}', now())"
            ),
            {"c": conv_id, "app": app_id},
        )

    _alembic_ok("upgrade", "ichat002")

    def check_upgraded():
        with ephemeral_db.connect() as conn:
            insp = inspect(conn)
            cols = {c["name"]: c for c in insp.get_columns("chat_conversation_state")}
            assert cols["busy_token"]["nullable"] is True
            assert cols["busy_until"]["nullable"] is True
            assert cols["busy_token"]["type"].__class__.__name__ == "UUID"
            assert cols["busy_until"]["type"].timezone is True
            app_cols = {c["name"]: c for c in insp.get_columns("App")}
            assert app_cols["default_embedding_service_id"]["nullable"] is True
            idx = {i["name"]: i for i in insp.get_indexes("Repository")}
            assert idx["ix_Repository_silo_id_temp"]["column_names"] == ["silo_id"]
            predicate = conn.execute(text(
                "SELECT pg_get_expr(indpred, indrelid) FROM pg_index "
                "WHERE indexrelid = 'public.\"ix_Repository_silo_id_temp\"'::regclass")).scalar_one()
            assert "playground_media" in predicate  # partial: temp repositories only
            fk = _fk(insp, "App", "App_default_embedding_service_id_fkey")
            assert fk is not None
            assert fk["referred_table"] == "embedding_service"
            assert fk["referred_columns"] == ["service_id"]
            assert fk["constrained_columns"] == ["default_embedding_service_id"]
            assert fk["options"].get("ondelete") == "SET NULL"
            # Existing rows keep NULLs.
            row = conn.execute(
                text("SELECT busy_token, busy_until FROM chat_conversation_state WHERE conversation_id = :c"),
                {"c": conv_id},
            ).one()
            assert row == (None, None)
            assert conn.execute(
                text('SELECT default_embedding_service_id FROM "App" WHERE app_id = :a'), {"a": app_id}
            ).scalar_one() is None

    check_upgraded()

    # Deleting the embedding service referenced as App default sets the column to NULL.
    with ephemeral_db.begin() as conn:
        svc_id = conn.execute(
            text(
                "INSERT INTO embedding_service (name, provider, endpoint, api_key, description) "
                "VALUES ('emb', 'OpenAI', 'http://x', 'k', 'd') RETURNING service_id"
            )
        ).scalar_one()
        conn.execute(
            text('UPDATE "App" SET default_embedding_service_id = :s WHERE app_id = :a'),
            {"s": svc_id, "a": app_id},
        )
    with ephemeral_db.begin() as conn:
        conn.execute(text("DELETE FROM embedding_service WHERE service_id = :s"), {"s": svc_id})
        assert conn.execute(
            text('SELECT default_embedding_service_id FROM "App" WHERE app_id = :a'), {"a": app_id}
        ).scalar_one() is None

    _alembic_ok("downgrade", PARENT_REVISION)
    with ephemeral_db.connect() as conn:
        insp = inspect(conn)
        assert not ({"busy_token", "busy_until"} & {c["name"] for c in insp.get_columns("chat_conversation_state")})
        assert "default_embedding_service_id" not in {c["name"] for c in insp.get_columns("App")}
        assert "ix_Repository_silo_id_temp" not in {i["name"] for i in insp.get_indexes("Repository")}
        assert _fk(insp, "App", "App_default_embedding_service_id_fkey") is None
        assert conn.execute(
            text("SELECT count(*) FROM chat_conversation_state WHERE conversation_id = :c"), {"c": conv_id}
        ).scalar_one() == 1

    _alembic_ok("upgrade", "ichat002")
    check_upgraded()
