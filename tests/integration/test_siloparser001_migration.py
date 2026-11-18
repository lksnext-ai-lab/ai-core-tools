"""Data migration `siloparser001`: cross-app / dangling Silo.metadata_definition_id links are cleared."""

from __future__ import annotations

from sqlalchemy import text

from tests.integration.test_svceos001_migration import _run_alembic, ephemeral_db  # noqa: F401


def _one(conn, sql, **params):
    return conn.execute(text(sql), params).scalar_one()


def test_siloparser001_clears_only_bad_links(ephemeral_db):  # noqa: F811
    _run_alembic("upgrade", "svceos001")
    with ephemeral_db.begin() as conn:
        app_a = _one(conn, "INSERT INTO \"App\" (name, slug) VALUES ('A', 'sp001-a') RETURNING app_id")
        app_b = _one(conn, "INSERT INTO \"App\" (name, slug) VALUES ('B', 'sp001-b') RETURNING app_id")
        parser_a = _one(
            conn, 'INSERT INTO "OutputParser" (name, app_id) VALUES (\'pa\', :a) RETURNING parser_id', a=app_a
        )
        parser_b = _one(
            conn, 'INSERT INTO "OutputParser" (name, app_id) VALUES (\'pb\', :a) RETURNING parser_id', a=app_b
        )
        ins = 'INSERT INTO "Silo" (name, app_id, metadata_definition_id) VALUES (:n, :a, :p) RETURNING silo_id'
        own = _one(conn, ins, n="own", a=app_a, p=parser_a)
        foreign = _one(conn, ins, n="foreign", a=app_a, p=parser_b)
        none = _one(conn, ins, n="none", a=app_a, p=None)

    _run_alembic("upgrade", "siloparser001")
    with ephemeral_db.connect() as conn:
        get = 'SELECT metadata_definition_id FROM "Silo" WHERE silo_id = :i'
        assert _one(conn, get, i=own) == parser_a
        assert _one(conn, get, i=foreign) is None
        assert _one(conn, get, i=none) is None
        assert _one(conn, 'SELECT count(*) FROM "OutputParser"') == 2

    _run_alembic("downgrade", "svceos001")
