"""Round-trip test of the real `ichat004` migration ("App".chat_code_interpreter_enabled).

Same ephemeral-database + real `alembic` CLI pattern as test_ichat002_migration.py.

Requires: the `db_test` docker-compose service on port 5433.
"""

from __future__ import annotations

import os
import subprocess
import sys
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
EPHEMERAL_DB_NAME = "mattin_test_ichat004_round_trip"
PARENT_REVISION = "ichat003"


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




def _index_names(conn):
    return {i["name"] for i in inspect(conn).get_indexes("Conversation")}


def test_ichat004_adds_the_conversation_indexes_and_downgrade_drops_them(ephemeral_db):
    _alembic_ok("upgrade", PARENT_REVISION)
    with ephemeral_db.connect() as conn:
        assert "ix_conversation_agent_user_updated" not in _index_names(conn)
    _alembic_ok("upgrade", "ichat004")
    with ephemeral_db.connect() as conn:
        names = _index_names(conn)
        assert {"ix_conversation_agent_user_updated", "ix_conversation_agent_api_key_hash"} <= names
        definition = conn.execute(text(
            "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_conversation_agent_user_updated'")).scalar_one()
        assert "agent_id, user_id, updated_at DESC" in definition
    _alembic_ok("upgrade", "ichat004")  # idempotent
    _alembic_ok("downgrade", PARENT_REVISION)
    with ephemeral_db.connect() as conn:
        assert not {"ix_conversation_agent_user_updated", "ix_conversation_agent_api_key_hash"} & _index_names(conn)


def _seed_internal_chat_leftovers(engine, qdrant=False):
    """An internal agent (id N) with a temp repo/silo/parser/vectors/checkpoint, plus another agent's repo whose
    name merely STARTS WITH the same digits (agent N0..N9): it must survive the downgrade."""
    with engine.begin() as conn:
        app_id = conn.execute(text(
            'INSERT INTO "App" (name, slug) VALUES (\'purge app\', \'purge-app\') RETURNING app_id')).scalar_one()
        agent_id = conn.execute(text(
            'INSERT INTO "Agent" (name, app_id, type, kind) VALUES (\'hidden\', :a, \'agent\', \'internal_chat\') '
            "RETURNING agent_id"), {"a": app_id}).scalar_one()

        def temp(name, vdb="PGVECTOR"):
            parser = conn.execute(text(
                'INSERT INTO "OutputParser" (name, app_id, fields) VALUES (:n, :a, \'[]\') RETURNING parser_id'
            ), {"n": f"DEFAULT-REPO-FILTER-{name}", "a": app_id}).scalar_one()
            silo = conn.execute(text(
                'INSERT INTO "Silo" (name, app_id, vector_db_type, metadata_definition_id, is_frozen) '
                "VALUES (:n, :a, :v, :p, false) RETURNING silo_id"), {"n": name, "a": app_id, "v": vdb, "p": parser}
            ).scalar_one()
            repo = conn.execute(text(
                'INSERT INTO "Repository" (name, app_id, silo_id, type) VALUES (:n, :a, :s, \'playground_media\') '
                "RETURNING repository_id"), {"n": name, "a": app_id, "s": silo}).scalar_one()
            return parser, silo, repo

        own = temp(f"_playground_{agent_id}_conv_{agent_id}_abc", "QDRANT" if qdrant else "PGVECTOR")
        other = temp(f"_playground_{agent_id}7_another-agents-session")  # agent N7: NOT ours
        conn.execute(text("CREATE TABLE IF NOT EXISTS langchain_pg_collection (uuid uuid PRIMARY KEY, name text)"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS langchain_pg_embedding (id serial PRIMARY KEY, collection_id uuid)"))
        for kind, ids in (("own", own), ("other", other)):
            conn.execute(text("INSERT INTO langchain_pg_collection VALUES (gen_random_uuid(), :n)"),
                         {"n": f"silo_{ids[1]}"})
        conn.execute(text("INSERT INTO langchain_pg_embedding (collection_id) SELECT uuid FROM langchain_pg_collection"))
        conn.execute(text(
            'INSERT INTO "Conversation" (agent_id, session_id, source, created_at, updated_at, message_count) '
            "VALUES (:a, :s, 'INTERNAL_CHAT', now(), now(), 0)"), {"a": agent_id, "s": f"conv_{agent_id}_abc"})
        for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            conn.execute(text(f"CREATE TABLE IF NOT EXISTS {table} (thread_id text)"))
            for thread in (f"thread_{agent_id}_conv_{agent_id}_abc", f"thread_{agent_id}", f"thread_{agent_id}7_other",
                           f"thread_{agent_id}_no-conversation-row"):
                conn.execute(text(f"INSERT INTO {table} VALUES (:t)"), {"t": thread})
    return agent_id, own, other


def _count(conn, sql, **params):
    return conn.execute(text(sql), params).scalar_one()


def test_ichat001_downgrade_purges_the_internal_agents_leftovers_and_only_those(ephemeral_db):
    _alembic_ok("upgrade", "ichat003")
    agent_id, own, other = _seed_internal_chat_leftovers(ephemeral_db)
    _alembic_ok("downgrade", "chatfiltmerge003")
    with ephemeral_db.connect() as conn:
        # ours: gone (repository, silo, parser, vectors, checkpoint rows of our threads)
        assert _count(conn, 'SELECT count(*) FROM "Repository" WHERE repository_id = :r', r=own[2]) == 0
        assert _count(conn, 'SELECT count(*) FROM "Silo" WHERE silo_id = :s', s=own[1]) == 0
        assert _count(conn, 'SELECT count(*) FROM "OutputParser" WHERE parser_id = :p', p=own[0]) == 0
        assert _count(conn, "SELECT count(*) FROM langchain_pg_collection WHERE name = :n", n=f"silo_{own[1]}") == 0
        for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            left = {r[0] for r in conn.execute(text(f"SELECT thread_id FROM {table}"))}
            # exact ids are purged; a standard agent's thread survives; a thread without a Conversation row is a
            # documented leftover (a LIKE sweep would scan the checkpoint tables)
            assert left == {f"thread_{agent_id}7_other", f"thread_{agent_id}_no-conversation-row"}, (table, left)
        # another agent whose id merely starts with ours: untouched
        assert _count(conn, 'SELECT count(*) FROM "Repository" WHERE repository_id = :r', r=other[2]) == 1
        assert _count(conn, 'SELECT count(*) FROM "Silo" WHERE silo_id = :s', s=other[1]) == 1
        assert _count(conn, "SELECT count(*) FROM langchain_pg_collection WHERE name = :n", n=f"silo_{other[1]}") == 1
        assert _count(conn, "SELECT count(*) FROM langchain_pg_embedding") == 1
        assert _count(conn, 'SELECT count(*) FROM "Agent" WHERE agent_id = :a', a=agent_id) == 0
    _alembic_ok("upgrade", "ichat004")  # the chain goes back up


def test_the_downgrade_refuses_when_a_temp_silo_lives_in_qdrant(ephemeral_db):
    _alembic_ok("upgrade", "ichat003")
    agent_id, own, other = _seed_internal_chat_leftovers(ephemeral_db, qdrant=True)
    result = _run_alembic("downgrade", "chatfiltmerge003")
    assert result.returncode != 0
    assert "Qdrant" in result.stderr + result.stdout
    with ephemeral_db.connect() as conn:  # nothing was touched: the agent and the silo are still there
        assert _count(conn, 'SELECT count(*) FROM "Agent" WHERE agent_id = :a', a=agent_id) == 1
        assert _count(conn, 'SELECT count(*) FROM "Silo" WHERE silo_id = :s', s=own[1]) == 1
