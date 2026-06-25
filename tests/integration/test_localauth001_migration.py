"""Integration tests for the localauth001 migration schema state — AC-16.

Asserts the schema produced by localauth001 is present after create_all:
- failed_attempts and locked_until columns on user_credentials
- refresh_tokens table with all expected columns and indexes (including the
  UNIQUE index on jti, which enforces refresh-token reuse/replay prevention)

NOTE on migration cycle testing:
  Full alembic upgrade → downgrade → upgrade cycle testing (the literal AC-16
  validation strategy) is not automated here.  The session-scoped test_engine
  uses Base.metadata.create_all without inserting an alembic_version row,
  making it incompatible with alembic running against the same DB (alembic
  would attempt to re-create tables that create_all already made).  This is
  the same constraint established in test_migration_domain_crawling.py and
  test_migration_user_deletion.py.

  The up/down/up cycle was manually validated during localauth001 development:
    - alembic upgrade head: failed_attempts / locked_until added; refresh_tokens created
    - alembic downgrade -1: columns dropped; refresh_tokens dropped
    - Re-upgrade: columns and table restored correctly

Requires: test DB on port 5433 (started by docker compose --profile test).
"""

import pytest
from sqlalchemy import inspect, text


class TestLocalauth001SchemaState:
    """Assert the schema produced by localauth001 is present after create_all."""

    def test_user_credentials_has_failed_attempts_column(self, test_engine):
        """failed_attempts column must exist on user_credentials."""
        inspector = inspect(test_engine)
        cols = {c["name"] for c in inspector.get_columns("user_credentials")}
        assert "failed_attempts" in cols, (
            "user_credentials.failed_attempts missing — localauth001 not applied"
        )

    def test_user_credentials_has_locked_until_column(self, test_engine):
        """locked_until column must exist on user_credentials."""
        inspector = inspect(test_engine)
        cols = {c["name"] for c in inspector.get_columns("user_credentials")}
        assert "locked_until" in cols, (
            "user_credentials.locked_until missing — localauth001 not applied"
        )

    def test_refresh_tokens_table_exists(self, test_engine):
        """refresh_tokens table must be present."""
        inspector = inspect(test_engine)
        assert "refresh_tokens" in inspector.get_table_names(), (
            "refresh_tokens table missing — localauth001 not applied"
        )

    def test_refresh_tokens_has_required_columns(self, test_engine):
        """refresh_tokens must have all columns defined in localauth001."""
        expected = {
            "id", "jti", "user_id", "family_id", "token_hash",
            "expires_at", "revoked_at", "rotated_at", "created_at",
            "user_agent", "ip",
        }
        inspector = inspect(test_engine)
        cols = {c["name"] for c in inspector.get_columns("refresh_tokens")}
        missing = expected - cols
        assert not missing, f"refresh_tokens missing columns: {missing}"

    def test_refresh_tokens_jti_index_exists(self, test_engine):
        """Unique index on refresh_tokens.jti must exist."""
        with test_engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE tablename = 'refresh_tokens' AND indexname = 'ix_refresh_tokens_jti'"
                )
            ).fetchone()
        assert result is not None, "Index ix_refresh_tokens_jti not found on refresh_tokens"

    def test_refresh_tokens_jti_index_is_unique(self, test_engine):
        """ix_refresh_tokens_jti must be a UNIQUE index.

        jti uniqueness is the database-level guarantee that prevents refresh-token
        reuse and replay attacks.  A non-unique index would fail to block duplicate
        JTIs on concurrent requests.
        """
        with test_engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT i.indisunique "
                    "FROM pg_index i "
                    "JOIN pg_class c ON c.oid = i.indexrelid "
                    "WHERE c.relname = 'ix_refresh_tokens_jti'"
                )
            ).fetchone()
        assert result is not None, "Index ix_refresh_tokens_jti not found in pg_index"
        assert result[0] is True, (
            "ix_refresh_tokens_jti must be UNIQUE to prevent refresh-token replay"
        )

    def test_refresh_tokens_user_id_index_exists(self, test_engine):
        """Index on refresh_tokens.user_id must exist."""
        with test_engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE tablename = 'refresh_tokens' AND indexname = 'ix_refresh_tokens_user_id'"
                )
            ).fetchone()
        assert result is not None, "Index ix_refresh_tokens_user_id not found on refresh_tokens"

    def test_refresh_tokens_family_id_index_exists(self, test_engine):
        """Index on refresh_tokens.family_id must exist."""
        with test_engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE tablename = 'refresh_tokens' AND indexname = 'ix_refresh_tokens_family_id'"
                )
            ).fetchone()
        assert result is not None, "Index ix_refresh_tokens_family_id not found on refresh_tokens"

    def test_failed_attempts_is_not_nullable(self, test_engine):
        """failed_attempts must be NOT NULL (server_default='0' backfills existing rows)."""
        inspector = inspect(test_engine)
        cols = {c["name"]: c for c in inspector.get_columns("user_credentials")}
        col = cols.get("failed_attempts")
        assert col is not None
        assert col["nullable"] is False, "failed_attempts must be NOT NULL"

    def test_locked_until_is_nullable(self, test_engine):
        """locked_until must be nullable (no default lockout on existing rows)."""
        inspector = inspect(test_engine)
        cols = {c["name"]: c for c in inspector.get_columns("user_credentials")}
        col = cols.get("locked_until")
        assert col is not None
        assert col["nullable"] is True, "locked_until must be nullable"

    def test_refresh_tokens_user_id_fk_has_on_delete_cascade(self, test_engine):
        """refresh_tokens.user_id FK must be ON DELETE CASCADE per localauth001."""
        query = text("""
            SELECT c.confdeltype
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.conkey)
            WHERE t.relname = 'refresh_tokens'
              AND a.attname = 'user_id'
              AND c.contype = 'f'
        """)
        with test_engine.connect() as conn:
            row = conn.execute(query).first()
        assert row is not None, "No FK found for refresh_tokens.user_id"
        # 'c' = CASCADE
        assert row[0] == "c", (
            f"refresh_tokens.user_id FK should be CASCADE ('c'), got '{row[0]}'"
        )
