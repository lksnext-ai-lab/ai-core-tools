"""Schema-drift test: the a2a001 migration's hard-coded DDL vs the SDK registry.

`alembic/versions/a2a001_agent_server.py` hard-codes the DDL for
`a2a_tasks`/`a2a_task_events`/`a2a_task_versions` rather than importing
`services.a2a_server.sdk_models.get_sdk_metadata()` at runtime (see that
migration's module docstring for why). This test is what actually proves the
two stay in sync: it runs the real `alembic upgrade head` CLI against a
brand-new ephemeral database (same pattern as
`tests/integration/test_useremail001_migration_e2e.py`), reflects the three
tables, and compares columns/indexes/PK against `get_sdk_metadata()`'s
`Table` objects -- the same registry `services/a2a_server/storage.py` binds
the SDK store/stream to at runtime.

Together with `tests/integration/a2a_server/test_sdk_contract.py` (which
fails loudly if the installed a2a-sdk version itself changes the mixins),
this is what catches an SDK bump that changes a column type, nullability or
index without anyone updating the migration.

Requires: the ``db_test`` docker-compose service on port 5433 (see
``test_useremail001_migration_e2e.py``'s module docstring).
"""

from __future__ import annotations

import os
import subprocess
import sys
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
EPHEMERAL_DB_NAME = "mattin_test_a2a001_schema_drift"

_CONTRACT_MSG = "SDK schema drift: update the migration"


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
def ephemeral_head_db():
    """Ephemeral DB migrated to `head` via the real `alembic upgrade` CLI."""
    _create_ephemeral_db()
    engine = None
    try:
        result = _run_alembic("upgrade", "head")
        assert result.returncode == 0, (
            f"alembic upgrade head failed (rc={result.returncode}).\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )
        url = f"postgresql://{DB_SUPERUSER}:{DB_SUPERUSER_PASSWORD}@{DB_HOST}:{DB_PORT}/{EPHEMERAL_DB_NAME}"
        engine = create_engine(url, pool_pre_ping=True)
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        _drop_ephemeral_db()


def _type_affinity(sqla_type) -> str:
    """Maps a SQLAlchemy type instance to a coarse family, shared across the
    migration's `sa.*` types and whatever Postgres-dialect class the
    inspector reflects back (e.g. `sa.String`/`VARCHAR`, `sa.JSON`/`JSON`,
    `sa.LargeBinary`/`BYTEA`, `sa.BigInteger`/`BIGINT`, `sa.DateTime`/
    `TIMESTAMP`).
    """
    python_type = None
    try:
        python_type = sqla_type.python_type
    except NotImplementedError:
        pass
    name = type(sqla_type).__name__.upper()
    if python_type is bytes or "BINARY" in name or "BYTEA" in name:
        return "BINARY"
    if python_type is dict or python_type is list or "JSON" in name:
        return "JSON"
    if python_type is str or "STRING" in name or "VARCHAR" in name or "CHAR" in name or "TEXT" in name:
        return "STRING"
    if python_type is int or "INT" in name:
        return "INTEGER"
    import datetime as _dt

    if python_type is _dt.datetime or "DATETIME" in name or "TIMESTAMP" in name:
        return "DATETIME"
    return name


def test_a2a_sdk_tables_match_registry_after_migration(ephemeral_head_db):
    """Reflects the three SDK tables post-migration and compares against the registry."""
    from services.a2a_server.sdk_models import get_sdk_metadata

    sdk_metadata = get_sdk_metadata()
    inspector = inspect(ephemeral_head_db)

    for table_name, expected_table in sdk_metadata.tables.items():
        assert inspector.has_table(table_name), f"{_CONTRACT_MSG}: {table_name!r} missing after migration"

        reflected_columns = {c["name"]: c for c in inspector.get_columns(table_name)}
        expected_columns = {c.name: c for c in expected_table.columns}

        # Equal column *sets*, not a subset check: an extra migration-only column the
        # registry doesn't know about is just as much a drift bug as a missing one.
        missing = set(expected_columns) - set(reflected_columns)
        extra = set(reflected_columns) - set(expected_columns)
        assert not missing, f"{_CONTRACT_MSG}: {table_name} missing columns {missing}"
        assert not extra, f"{_CONTRACT_MSG}: {table_name} has unexpected extra columns {extra}"

        for col_name, expected_col in expected_columns.items():
            reflected = reflected_columns[col_name]
            assert reflected["nullable"] == expected_col.nullable, (
                f"{_CONTRACT_MSG}: {table_name}.{col_name} nullability differs "
                f"(migration={reflected['nullable']!r}, sdk={expected_col.nullable!r})"
            )
            expected_length = getattr(expected_col.type, "length", None)
            reflected_length = getattr(reflected["type"], "length", None)
            assert reflected_length == expected_length, (
                f"{_CONTRACT_MSG}: {table_name}.{col_name} length differs "
                f"(migration={reflected_length!r}, sdk={expected_length!r})"
            )
            # Type-family check (string/int/json/binary/datetime), not an exact Python class
            # match -- the migration uses sa.* directly while SQLAlchemy may reflect a
            # Postgres-dialect-specific subclass (e.g. a dialect-level JSON/BYTEA variant).
            expected_affinity = _type_affinity(expected_col.type)
            reflected_affinity = _type_affinity(reflected["type"])
            assert reflected_affinity == expected_affinity, (
                f"{_CONTRACT_MSG}: {table_name}.{col_name} type differs "
                f"(migration={reflected_affinity!r} [{reflected['type']!r}], "
                f"sdk={expected_affinity!r} [{expected_col.type!r}])"
            )

        # Primary key
        reflected_pk = set(inspector.get_pk_constraint(table_name)["constrained_columns"])
        expected_pk = {c.name for c in expected_table.primary_key.columns}
        assert reflected_pk == expected_pk, (
            f"{_CONTRACT_MSG}: {table_name} primary key differs "
            f"(migration={reflected_pk!r}, sdk={expected_pk!r})"
        )

        # Indexes: compared by *name* (not just column set), including uniqueness. The
        # registry's own Mattin-owned addition (ix_a2a_tasks_last_updated, declared on
        # the `task` model in sdk_models.get_sdk_models()) is part of `expected_table`
        # too, so this is now an exact match in both directions -- no "extra index
        # explicitly allowed" escape hatch.
        reflected_indexes = {ix["name"]: ix for ix in inspector.get_indexes(table_name)}
        expected_indexes = {ix.name: ix for ix in expected_table.indexes}

        missing_indexes = set(expected_indexes) - set(reflected_indexes)
        extra_indexes = set(reflected_indexes) - set(expected_indexes)
        assert not missing_indexes, f"{_CONTRACT_MSG}: {table_name} missing index(es) {missing_indexes}"
        assert not extra_indexes, f"{_CONTRACT_MSG}: {table_name} has unexpected extra index(es) {extra_indexes}"

        for index_name, expected_index in expected_indexes.items():
            reflected_index = reflected_indexes[index_name]
            expected_colset = tuple(c.name for c in expected_index.columns)
            reflected_colset = tuple(reflected_index["column_names"])
            assert reflected_colset == expected_colset, (
                f"{_CONTRACT_MSG}: {table_name} index {index_name!r} columns differ "
                f"(migration={reflected_colset!r}, sdk={expected_colset!r})"
            )
            assert bool(reflected_index["unique"]) == bool(expected_index.unique), (
                f"{_CONTRACT_MSG}: {table_name} index {index_name!r} uniqueness differs "
                f"(migration={reflected_index['unique']!r}, sdk={bool(expected_index.unique)!r})"
            )

    # a2a_task_events.seq must auto-increment (BIGSERIAL in the migration, matching
    # what create_all emits for a BigInteger primary_key with autoincrement=True on
    # PG -- see the migration's module docstring). A plain BIGINT with no
    # sequence/identity default would silently break every insert through the SDK,
    # which never supplies `seq` itself.
    seq_column = next(
        c for c in inspector.get_columns("a2a_task_events") if c["name"] == "seq"
    )
    default = (seq_column.get("default") or "") or ""
    with ephemeral_head_db.connect() as conn:
        identity_count = conn.execute(
            text(
                """
                SELECT count(*) FROM information_schema.columns
                WHERE table_name = 'a2a_task_events' AND column_name = 'seq'
                  AND identity_generation IS NOT NULL
                """
            )
        ).scalar_one()
    assert "nextval(" in default or identity_count > 0, (
        f"{_CONTRACT_MSG}: a2a_task_events.seq has no sequence/identity default "
        f"(reflected default={default!r}); inserts through the SDK (which never "
        "supplies seq itself) would fail"
    )
