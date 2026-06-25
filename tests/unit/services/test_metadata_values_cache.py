"""Unit tests for MetadataValuesCacheService. No DB or vector-store access — all mocked."""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from services.metadata_values_cache_service import (
    MetadataValuesCacheService,
    _DEFAULT_TTL_SECONDS,
    _SAMPLING_LIMIT,
)


@pytest.fixture(autouse=True)
def reset_cache(monkeypatch):
    """Clean singleton cache and reset TTL before every test."""
    MetadataValuesCacheService._reset_for_testing()
    monkeypatch.delenv("METADATA_VALUES_CACHE_TTL_SECONDS", raising=False)
    yield
    MetadataValuesCacheService._reset_for_testing()


def _patch_silo_service(return_values: list[str] | None = None, side_effect=None):
    """Patch SiloService.get_metadata_field_values via the deferred-import path."""
    mock_fn = MagicMock()
    if side_effect is not None:
        mock_fn.side_effect = side_effect
    else:
        mock_fn.return_value = return_values if return_values is not None else ["a", "b"]

    return patch(
        "services.metadata_values_cache_service.MetadataValuesCacheService._fetch_from_vector_store",
        side_effect=lambda silo_id, field, db: mock_fn(silo_id, field, db),
    ), mock_fn


class TestCacheHit:
    def test_second_call_within_ttl_returns_cached_values(self):
        """AC-18: second call within TTL must not re-query the vector store."""
        db = MagicMock()
        values = ["invoice", "receipt"]

        with patch(
            "services.metadata_values_cache_service.MetadataValuesCacheService._fetch_from_vector_store",
            return_value=values,
        ) as mock_fetch:
            first = MetadataValuesCacheService.get_distinct_values(1, "doc_type", db)
            second = MetadataValuesCacheService.get_distinct_values(1, "doc_type", db)

        assert first == values
        assert second == values
        assert mock_fetch.call_count == 1, (
            f"Expected 1 fetch, got {mock_fetch.call_count} — cache was not used on the second call"
        )

    def test_different_fields_are_cached_independently(self):
        """Different (silo_id, field) keys are fetched and cached independently."""
        db = MagicMock()

        call_log: list[tuple[int, str]] = []

        def fake_fetch(silo_id, field, _db):
            call_log.append((silo_id, field))
            return [f"value_for_{field}"]

        with patch(
            "services.metadata_values_cache_service.MetadataValuesCacheService._fetch_from_vector_store",
            side_effect=fake_fetch,
        ):
            MetadataValuesCacheService.get_distinct_values(1, "doc_type", db)
            MetadataValuesCacheService.get_distinct_values(1, "language", db)
            MetadataValuesCacheService.get_distinct_values(1, "doc_type", db)
            MetadataValuesCacheService.get_distinct_values(1, "language", db)

        assert len(call_log) == 2
        assert (1, "doc_type") in call_log
        assert (1, "language") in call_log

    def test_different_silos_are_cached_independently(self):
        db = MagicMock()
        call_log: list[int] = []

        def fake_fetch(silo_id, field, _db):
            call_log.append(silo_id)
            return ["x"]

        with patch(
            "services.metadata_values_cache_service.MetadataValuesCacheService._fetch_from_vector_store",
            side_effect=fake_fetch,
        ):
            MetadataValuesCacheService.get_distinct_values(1, "doc_type", db)
            MetadataValuesCacheService.get_distinct_values(2, "doc_type", db)
            MetadataValuesCacheService.get_distinct_values(1, "doc_type", db)
            MetadataValuesCacheService.get_distinct_values(2, "doc_type", db)

        assert len(call_log) == 2


class TestInvalidation:
    def test_invalidate_forces_re_query(self):
        """After invalidate(silo_id), the next call must hit the vector store again."""
        db = MagicMock()
        fetch_count = [0]

        def fake_fetch(silo_id, field, _db):
            fetch_count[0] += 1
            return ["v1"]

        with patch(
            "services.metadata_values_cache_service.MetadataValuesCacheService._fetch_from_vector_store",
            side_effect=fake_fetch,
        ):
            MetadataValuesCacheService.get_distinct_values(5, "doc_type", db)
            assert fetch_count[0] == 1

            MetadataValuesCacheService.invalidate(5)

            MetadataValuesCacheService.get_distinct_values(5, "doc_type", db)
            assert fetch_count[0] == 2

    def test_invalidate_only_removes_target_silo(self):
        """invalidate(silo_id=A) must not evict entries for silo_id=B."""
        db = MagicMock()
        fetch_counts: dict[int, int] = {1: 0, 2: 0}

        def fake_fetch(silo_id, field, _db):
            fetch_counts[silo_id] += 1
            return ["x"]

        with patch(
            "services.metadata_values_cache_service.MetadataValuesCacheService._fetch_from_vector_store",
            side_effect=fake_fetch,
        ):
            MetadataValuesCacheService.get_distinct_values(1, "f", db)
            MetadataValuesCacheService.get_distinct_values(2, "f", db)

            MetadataValuesCacheService.invalidate(1)

            MetadataValuesCacheService.get_distinct_values(1, "f", db)  # re-fetch for silo 1
            MetadataValuesCacheService.get_distinct_values(2, "f", db)  # still cached for silo 2

        assert fetch_counts[1] == 2
        assert fetch_counts[2] == 1, "Silo 2 should have remained cached after invalidating silo 1"

    def test_invalidate_unknown_silo_is_a_noop(self):
        """invalidate() on a silo with no cached entries must not raise."""
        MetadataValuesCacheService.invalidate(999)  # should not raise


class TestTTLExpiry:
    def test_expired_entry_is_re_fetched(self, monkeypatch):
        """When the TTL expires, the next call must bypass the cache and re-query."""
        db = MagicMock()
        fetch_count = [0]
        fake_now = [0.0]

        monkeypatch.setattr(
            "services.metadata_values_cache_service.time.monotonic",
            lambda: fake_now[0],
        )

        MetadataValuesCacheService._ttl_seconds = 10

        def fake_fetch(silo_id, field, _db):
            fetch_count[0] += 1
            return ["v"]

        with patch(
            "services.metadata_values_cache_service.MetadataValuesCacheService._fetch_from_vector_store",
            side_effect=fake_fetch,
        ):
            MetadataValuesCacheService.get_distinct_values(3, "lang", db)
            assert fetch_count[0] == 1

            fake_now[0] = 5.0
            MetadataValuesCacheService.get_distinct_values(3, "lang", db)
            assert fetch_count[0] == 1, "Call within TTL should have been a cache hit"

            fake_now[0] = 15.0
            MetadataValuesCacheService.get_distinct_values(3, "lang", db)
            assert fetch_count[0] == 2, "Call after TTL expiry should have triggered a re-fetch"


# ---------------------------------------------------------------------------
# Error handling: exception → empty list, NOT cached
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_vector_store_error_returns_empty_list(self):
        """An exception from the vector store must return [] and not raise."""
        db = MagicMock()

        with patch(
            "services.metadata_values_cache_service.MetadataValuesCacheService._fetch_from_vector_store",
            return_value=None,
        ):
            result = MetadataValuesCacheService.get_distinct_values(7, "doc_type", db)

        assert result == []

    def test_error_result_is_not_cached(self):
        """After an error (returns None), the next call must re-query the vector store."""
        db = MagicMock()
        call_count = [0]

        def fake_fetch(silo_id, field, _db):
            call_count[0] += 1
            if call_count[0] == 1:
                return None
            return ["ok"]

        with patch(
            "services.metadata_values_cache_service.MetadataValuesCacheService._fetch_from_vector_store",
            side_effect=fake_fetch,
        ):
            first = MetadataValuesCacheService.get_distinct_values(7, "doc_type", db)
            second = MetadataValuesCacheService.get_distinct_values(7, "doc_type", db)

        assert first == [], "Error path must return empty list"
        assert second == ["ok"], "Second call should have re-queried after the error"
        assert call_count[0] == 2, "The error result must not have been cached"

    def test_successful_empty_result_is_cached(self):
        """An actual empty list from the vector store (no values) IS a valid result and should be cached."""
        db = MagicMock()
        fetch_count = [0]

        def fake_fetch(silo_id, field, _db):
            fetch_count[0] += 1
            return []

        with patch(
            "services.metadata_values_cache_service.MetadataValuesCacheService._fetch_from_vector_store",
            side_effect=fake_fetch,
        ):
            first = MetadataValuesCacheService.get_distinct_values(8, "rarity", db)
            second = MetadataValuesCacheService.get_distinct_values(8, "rarity", db)

        assert first == []
        assert second == []
        assert fetch_count[0] == 1, "Empty-but-successful result must be cached"


class TestConcurrency:
    def test_concurrent_misses_do_not_corrupt_cache(self):
        """Two threads hitting a cache miss simultaneously must both get valid results.

        Per the documented allow-duplicate-fetch policy, both threads may query
        the vector store. The test only checks that both receive the correct values
        and that the cache is in a consistent (non-corrupted) state afterward.
        """
        db = MagicMock()
        barrier = threading.Barrier(2)
        results: list[list[str]] = []
        errors: list[Exception] = []

        def slow_fetch(silo_id, field, _db):
            barrier.wait()
            time.sleep(0.005)
            return ["concurrent_value"]

        def thread_task():
            try:
                val = MetadataValuesCacheService.get_distinct_values(42, "field", db)
                results.append(val)
            except Exception as exc:
                errors.append(exc)

        with patch.object(
            MetadataValuesCacheService,
            "_fetch_from_vector_store",
            side_effect=slow_fetch,
        ):
            threads = [threading.Thread(target=thread_task) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert not errors, f"Unexpected exceptions in threads: {errors}"
        assert len(results) == 2
        for result in results:
            assert result == ["concurrent_value"], f"Unexpected result: {result}"

    def test_concurrent_reads_after_cache_warm_are_consistent(self):
        """After the cache is warm, many concurrent readers must all get the same values."""
        db = MagicMock()

        with patch(
            "services.metadata_values_cache_service.MetadataValuesCacheService._fetch_from_vector_store",
            return_value=["alpha", "beta", "gamma"],
        ):
            MetadataValuesCacheService.get_distinct_values(10, "category", db)

        results: list[list[str]] = []

        def reader():
            results.append(
                MetadataValuesCacheService.get_distinct_values(10, "category", db)
            )

        threads = [threading.Thread(target=reader) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 20
        for r in results:
            assert r == ["alpha", "beta", "gamma"]


class TestEnvVarTTL:
    def test_invalid_ttl_env_var_uses_default(self, monkeypatch):
        """A non-integer METADATA_VALUES_CACHE_TTL_SECONDS must fall back to the default."""
        monkeypatch.setenv("METADATA_VALUES_CACHE_TTL_SECONDS", "not_a_number")

        from services.metadata_values_cache_service import _parse_ttl_from_env

        result = _parse_ttl_from_env()
        assert result == _DEFAULT_TTL_SECONDS

    def test_zero_ttl_env_var_uses_default(self, monkeypatch):
        """A zero or negative value for the TTL env var must fall back to the default."""
        monkeypatch.setenv("METADATA_VALUES_CACHE_TTL_SECONDS", "0")

        from services.metadata_values_cache_service import _parse_ttl_from_env

        result = _parse_ttl_from_env()
        assert result == _DEFAULT_TTL_SECONDS

    def test_negative_ttl_env_var_uses_default(self, monkeypatch):
        """A negative TTL env var must fall back to the default."""
        monkeypatch.setenv("METADATA_VALUES_CACHE_TTL_SECONDS", "-1")

        from services.metadata_values_cache_service import _parse_ttl_from_env

        result = _parse_ttl_from_env()
        assert result == _DEFAULT_TTL_SECONDS

    def test_valid_ttl_env_var_is_respected(self, monkeypatch):
        """A valid positive integer TTL env var must be used directly."""
        monkeypatch.setenv("METADATA_VALUES_CACHE_TTL_SECONDS", "300")

        from services.metadata_values_cache_service import _parse_ttl_from_env

        result = _parse_ttl_from_env()
        assert result == 300

    def test_missing_ttl_env_var_uses_default(self, monkeypatch):
        """When the env var is not set at all, the default TTL must be used."""
        monkeypatch.delenv("METADATA_VALUES_CACHE_TTL_SECONDS", raising=False)

        from services.metadata_values_cache_service import _parse_ttl_from_env

        result = _parse_ttl_from_env()
        assert result == _DEFAULT_TTL_SECONDS


class TestSamplingLimit:
    def test_fetch_passes_correct_sampling_limit(self):
        """_fetch_from_vector_store must call SiloService with the fixed _SAMPLING_LIMIT."""
        db = MagicMock()

        captured_limit: list[int] = []

        def mock_get_values(silo_id, field, prefix, limit, db):
            captured_limit.append(limit)
            return ["x"]

        with patch(
            "services.silo_service.SiloService.get_metadata_field_values",
            side_effect=mock_get_values,
        ):
            MetadataValuesCacheService._fetch_from_vector_store(1, "doc_type", db)

        assert captured_limit == [_SAMPLING_LIMIT], (
            f"Expected sampling limit {_SAMPLING_LIMIT}, got {captured_limit}"
        )

    def test_fetch_returns_none_on_silo_service_exception(self):
        """_fetch_from_vector_store must return None (not raise) when SiloService raises."""
        db = MagicMock()

        with patch(
            "services.silo_service.SiloService.get_metadata_field_values",
            side_effect=RuntimeError("vector store unavailable"),
        ):
            result = MetadataValuesCacheService._fetch_from_vector_store(1, "doc_type", db)

        assert result is None
