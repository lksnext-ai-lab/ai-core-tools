"""
Integration tests for the domain crawling policies migration state.

These tests verify that the migration has been correctly applied to the test database
by checking that the expected tables and columns exist.

NOTE on migration cycle testing:
  Full alembic upgrade/downgrade cycle testing via alembic.command is complex in this
  project because the alembic env.py reads DB credentials from env vars (DATABASE_USER,
  DATABASE_PASSWORD, etc.) rather than SQLALCHEMY_DATABASE_URI, making it difficult to
  redirect to the test DB without patching the environment.

  The migration was tested manually during Step 01/02 development:
    - alembic upgrade head: creates domain_url, crawl_policy, crawl_job; drops Url
    - alembic downgrade -1: drops the new tables; recreates empty Url table
    - Re-upgrade: works correctly

  These tests verify the CURRENT schema state that the migration produces.
"""

import pytest
from sqlalchemy import inspect, text


class TestMigrationSchemaState:
    """
    Verify the domain crawling policies migration produced the expected schema.
    These tests use the session-scoped test_engine fixture (schema already set up).
    """

    def test_domain_url_table_exists(self, test_engine):
        """The domain_url table must exist in the test schema."""
        inspector = inspect(test_engine)
        table_names = inspector.get_table_names()
        assert "domain_url" in table_names, (
            f"domain_url table not found. Available tables: {table_names}"
        )

    def test_crawl_policy_table_exists(self, test_engine):
        """The crawl_policy table must exist in the test schema."""
        inspector = inspect(test_engine)
        table_names = inspector.get_table_names()
        assert "crawl_policy" in table_names, (
            f"crawl_policy table not found. Available tables: {table_names}"
        )

    def test_crawl_job_table_exists(self, test_engine):
        """The crawl_job table must exist in the test schema."""
        inspector = inspect(test_engine)
        table_names = inspector.get_table_names()
        assert "crawl_job" in table_names, (
            f"crawl_job table not found. Available tables: {table_names}"
        )

    def test_url_table_does_not_exist(self, test_engine):
        """The legacy Url table must NOT exist — it was dropped by the migration."""
        inspector = inspect(test_engine)
        table_names = inspector.get_table_names()
        assert "Url" not in table_names, (
            f"Legacy Url table still present. The migration should have dropped it."
        )

    def test_domain_url_columns(self, test_engine):
        """domain_url table has the expected key columns."""
        inspector = inspect(test_engine)
        columns = {col["name"] for col in inspector.get_columns("domain_url")}
        expected = {
            "id", "domain_id", "url", "normalized_url", "status", "discovered_via",
            "depth", "content_hash", "http_etag", "http_last_modified",
            "sitemap_lastmod", "last_crawled_at", "last_indexed_at", "next_crawl_at",
            "consecutive_skips", "failure_count", "last_error", "created_at", "updated_at",
        }
        missing = expected - columns
        assert not missing, f"domain_url missing columns: {missing}"

    def test_crawl_policy_columns(self, test_engine):
        """crawl_policy table has the expected key columns."""
        inspector = inspect(test_engine)
        columns = {col["name"] for col in inspector.get_columns("crawl_policy")}
        expected = {
            "id", "domain_id", "seed_url", "sitemap_url", "manual_urls",
            "max_depth", "include_globs", "exclude_globs", "rate_limit_rps",
            "refresh_interval_hours", "respect_robots_txt", "is_active",
            "created_at", "updated_at",
        }
        missing = expected - columns
        assert not missing, f"crawl_policy missing columns: {missing}"

    def test_crawl_job_columns(self, test_engine):
        """crawl_job table has the expected key columns."""
        inspector = inspect(test_engine)
        columns = {col["name"] for col in inspector.get_columns("crawl_job")}
        expected = {
            "id", "domain_id", "status", "triggered_by", "triggered_by_user_id",
            "started_at", "finished_at", "discovered_count", "indexed_count",
            "skipped_count", "removed_count", "failed_count", "error_log",
            "created_at", "worker_id", "heartbeat_at",
        }
        missing = expected - columns
        assert not missing, f"crawl_job missing columns: {missing}"

    def test_domain_url_unique_constraint(self, test_engine):
        """domain_url has a unique constraint on (domain_id, normalized_url)."""
        inspector = inspect(test_engine)
        unique_constraints = inspector.get_unique_constraints("domain_url")
        # Find a unique constraint covering domain_id and normalized_url
        has_unique = any(
            set(uc["column_names"]) == {"domain_id", "normalized_url"}
            for uc in unique_constraints
        )
        assert has_unique, (
            f"No unique constraint on (domain_id, normalized_url). "
            f"Constraints: {unique_constraints}"
        )

    def test_crawl_policy_domain_unique(self, test_engine):
        """crawl_policy has a unique constraint on domain_id (1:1 with Domain)."""
        inspector = inspect(test_engine)
        unique_constraints = inspector.get_unique_constraints("crawl_policy")
        has_unique = any(
            "domain_id" in uc["column_names"] for uc in unique_constraints
        )
        assert has_unique, (
            f"No unique constraint on domain_id in crawl_policy. "
            f"Constraints: {unique_constraints}"
        )

    def test_enum_types_exist(self, test_engine):
        """The four PostgreSQL enum types created by the migration exist."""
        with test_engine.connect() as conn:
            result = conn.execute(text(
                "SELECT typname FROM pg_type WHERE typtype = 'e' "
                "AND typname IN ('domain_url_status', 'discovery_source', 'crawl_job_status', 'crawl_trigger')"
            ))
            found_enums = {row[0] for row in result}

        expected_enums = {"domain_url_status", "discovery_source", "crawl_job_status", "crawl_trigger"}
        missing = expected_enums - found_enums
        assert not missing, f"Missing enum types: {missing}"
