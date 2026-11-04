"""Round-trip test of the real `svceos001` migration (service end of service).

Uses an ephemeral database migrated through the real Alembic chain (same pattern as
`tests/integration/a2a_server/test_a2a001_migration_round_trip.py`): start at the parent
revision with seeded service rows, upgrade, downgrade, upgrade again.

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
DB_USER = "test_user"
DB_PASSWORD = "test_pass"  # pragma: allowlist secret
MAINTENANCE_DB = "test_db"
EPHEMERAL_DB_NAME = "mattin_test_svceos001_round_trip"

TABLES = ("AIService", "embedding_service", "SandboxService")
NEW_COLUMNS = ("end_of_service_at", "deprecation_notice")
PARENT_REVISION = "indexerr001"


def _admin_connection():
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, dbname=MAINTENANCE_DB
    )
    conn.autocommit = True
    return conn


def _drop_db() -> None:
    conn = _admin_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{EPHEMERAL_DB_NAME}" WITH (FORCE)')
    finally:
        conn.close()


def _run_alembic(*args: str) -> None:
    env = dict(os.environ)
    env.update(
        DATABASE_USER=DB_USER,
        DATABASE_PASSWORD=DB_PASSWORD,
        DATABASE_HOST=DB_HOST,
        DATABASE_PORT=DB_PORT,
        DATABASE_NAME=EPHEMERAL_DB_NAME,
    )
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, (
        f"alembic {' '.join(args)} failed (rc={result.returncode}).\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )


@pytest.fixture
def ephemeral_db():
    _drop_db()
    conn = _admin_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE DATABASE "{EPHEMERAL_DB_NAME}"')
    finally:
        conn.close()
    engine = create_engine(
        f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{EPHEMERAL_DB_NAME}",
        pool_pre_ping=True,
    )
    try:
        yield engine
    finally:
        engine.dispose()
        _drop_db()


def _columns(engine, table: str) -> dict:
    return {c["name"]: c for c in inspect(engine).get_columns(table)}


def _assert_columns_present(engine) -> None:
    for table in TABLES:
        cols = _columns(engine, table)
        for name in NEW_COLUMNS:
            assert name in cols, f"{table}.{name} missing"
            assert cols[name]["nullable"] is True
        assert cols["deprecation_notice"]["type"].length == 1000
        assert cols["end_of_service_at"]["type"].timezone is True


def _assert_columns_absent(engine) -> None:
    for table in TABLES:
        cols = _columns(engine, table)
        for name in NEW_COLUMNS:
            assert name not in cols, f"{table}.{name} still present"


def test_svceos001_upgrade_downgrade_upgrade(ephemeral_db):
    _run_alembic("upgrade", PARENT_REVISION)
    _assert_columns_absent(ephemeral_db)

    with ephemeral_db.begin() as conn:
        for table in TABLES:
            conn.execute(
                text(f'INSERT INTO "{table}" (name, provider) VALUES (:n, :p)'),
                {"n": f"svceos001 {table}", "p": "test"},
            )

    _run_alembic("upgrade", "svceos001")
    _assert_columns_present(ephemeral_db)
    with ephemeral_db.connect() as conn:
        for table in TABLES:
            row = conn.execute(
                text(f'SELECT end_of_service_at, deprecation_notice FROM "{table}"')
            ).one()
            assert row == (None, None), f"pre-existing {table} row should read NULL"

    _run_alembic("downgrade", PARENT_REVISION)
    _assert_columns_absent(ephemeral_db)
    with ephemeral_db.connect() as conn:
        for table in TABLES:
            assert conn.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one() == 1

    _run_alembic("upgrade", "svceos001")
    _assert_columns_present(ephemeral_db)
