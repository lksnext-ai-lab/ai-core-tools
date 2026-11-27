"""Round-trip test of the real `ichat003` migration ("App".chat_code_interpreter_enabled).

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
EPHEMERAL_DB_NAME = "mattin_test_ichat003_round_trip"
PARENT_REVISION = "ichat002"


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


def test_ichat003_upgrade_downgrade_upgrade(ephemeral_db):
    _alembic_ok("upgrade", PARENT_REVISION)
    with ephemeral_db.begin() as conn:
        app_id = conn.execute(
            text('INSERT INTO "App" (name, slug) VALUES (:n, :s) RETURNING app_id'),
            {"n": "ichat003 app", "s": "ichat003-app"},
        ).scalar_one()

    _alembic_ok("upgrade", "ichat003")

    def check_upgraded():
        with ephemeral_db.connect() as conn:
            cols = {c["name"]: c for c in inspect(conn).get_columns("App")}
            col = cols["chat_code_interpreter_enabled"]
            assert col["nullable"] is False
            assert col["type"].__class__.__name__ == "BOOLEAN"
            assert "false" in str(col["default"]).lower()
            # Existing Apps get false.
            assert conn.execute(
                text('SELECT chat_code_interpreter_enabled FROM "App" WHERE app_id = :a'), {"a": app_id}
            ).scalar_one() is False

    check_upgraded()

    # New rows default to false as well, and NULL is rejected.
    with ephemeral_db.begin() as conn:
        new_id = conn.execute(
            text('INSERT INTO "App" (name, slug) VALUES (\'n2\', \'ichat003-app2\') RETURNING app_id')
        ).scalar_one()
        assert conn.execute(
            text('SELECT chat_code_interpreter_enabled FROM "App" WHERE app_id = :a'), {"a": new_id}
        ).scalar_one() is False
    with pytest.raises(Exception):
        with ephemeral_db.begin() as conn:
            conn.execute(text('UPDATE "App" SET chat_code_interpreter_enabled = NULL WHERE app_id = :a'), {"a": app_id})

    _alembic_ok("downgrade", PARENT_REVISION)
    with ephemeral_db.connect() as conn:
        assert "chat_code_interpreter_enabled" not in {c["name"] for c in inspect(conn).get_columns("App")}
        assert conn.execute(text('SELECT count(*) FROM "App"')).scalar_one() == 2

    _alembic_ok("upgrade", "ichat003")
    check_upgraded()
