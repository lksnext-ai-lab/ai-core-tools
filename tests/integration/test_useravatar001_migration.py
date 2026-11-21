"""Round-trip test of the real `useravatar001` migration ("user_avatar" table, FK CASCADE from "User").

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
EPHEMERAL_DB_NAME = "mattin_test_useravatar001_round_trip"
PARENT_REVISION = "ichat004"


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



def test_useravatar001_creates_the_table_cascading_from_user_and_downgrade_drops_it(ephemeral_db):
    _alembic_ok("upgrade", PARENT_REVISION)
    with ephemeral_db.connect() as conn:
        assert "user_avatar" not in inspect(conn).get_table_names()
    _alembic_ok("upgrade", "useravatar001")
    with ephemeral_db.begin() as conn:
        assert {c["name"] for c in inspect(conn).get_columns("user_avatar")} == {
            "user_id", "content", "content_type", "updated_at"}
        user_id = conn.execute(text(
            "INSERT INTO \"User\" (email, name, is_active, email_verified, platform_role) "
            "VALUES ('a@x.test', 'A', true, true, 'editor') RETURNING user_id")).scalar_one()
        conn.execute(text(
            "INSERT INTO user_avatar (user_id, content, content_type) VALUES (:u, '\\x00', 'image/webp')"),
            {"u": user_id})
        conn.execute(text('DELETE FROM "User" WHERE user_id = :u'), {"u": user_id})
        assert conn.execute(text("SELECT count(*) FROM user_avatar")).scalar_one() == 0
    _alembic_ok("downgrade", PARENT_REVISION)
    with ephemeral_db.connect() as conn:
        assert "user_avatar" not in inspect(conn).get_table_names()
