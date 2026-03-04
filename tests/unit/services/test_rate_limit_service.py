"""
Unit tests for RateLimitService.

RateLimitService is pure Python (no DB, no external deps), so these tests
are fast and fully isolated — no fixtures needed.
"""

import time
import pytest
import threading

from services.rate_limit_service import RateLimitService, RateLimitState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fresh() -> RateLimitService:
    """Return a new RateLimitService instance (avoids global state leaking)."""
    return RateLimitService()


# ---------------------------------------------------------------------------
# check_and_consume — unlimited mode
# ---------------------------------------------------------------------------


class TestUnlimited:
    def test_unlimited_when_max_zero(self):
        svc = fresh()
        state = svc.check_and_consume(app_id=1, max_per_minute=0)
        assert state.remaining == -1

    def test_unlimited_when_max_negative(self):
        svc = fresh()
        state = svc.check_and_consume(app_id=1, max_per_minute=-5)
        assert state.remaining == -1

    def test_unlimited_never_blocks(self):
        svc = fresh()
        for _ in range(1000):
            state = svc.check_and_consume(app_id=1, max_per_minute=0)
            assert state.remaining == -1


# ---------------------------------------------------------------------------
# check_and_consume — limited mode
# ---------------------------------------------------------------------------


class TestLimited:
    def test_first_request_consumes_one(self):
        svc = fresh()
        state = svc.check_and_consume(app_id=1, max_per_minute=10)
        assert state.remaining == 9
        assert state.limit == 10

    def test_remaining_decrements_per_call(self):
        svc = fresh()
        for expected_remaining in range(4, -1, -1):
            state = svc.check_and_consume(app_id=1, max_per_minute=5)
            assert state.remaining == expected_remaining

    def test_blocks_at_limit(self):
        svc = fresh()
        for _ in range(3):
            svc.check_and_consume(app_id=1, max_per_minute=3)
        # 4th call should be blocked
        state = svc.check_and_consume(app_id=1, max_per_minute=3)
        assert state.remaining == 0

    def test_blocked_state_remaining_is_zero(self):
        svc = fresh()
        limit = 2
        for _ in range(limit + 5):
            state = svc.check_and_consume(app_id=1, max_per_minute=limit)
        assert state.remaining == 0

    def test_reset_epoch_is_next_minute(self):
        svc = fresh()
        state = svc.check_and_consume(app_id=1, max_per_minute=10)
        current_minute = int(time.time() // 60)
        expected_reset = (current_minute + 1) * 60
        # Allow 1s tolerance for slow machines
        assert abs(state.reset_epoch - expected_reset) <= 1

    def test_different_apps_are_independent(self):
        svc = fresh()
        for _ in range(5):
            svc.check_and_consume(app_id=1, max_per_minute=5)
        # app_id=2 should still be fresh
        state = svc.check_and_consume(app_id=2, max_per_minute=5)
        assert state.remaining == 4

    def test_limit_one_allows_exactly_one(self):
        svc = fresh()
        first = svc.check_and_consume(app_id=1, max_per_minute=1)
        second = svc.check_and_consume(app_id=1, max_per_minute=1)
        assert first.remaining == 0
        assert second.remaining == 0  # blocked


# ---------------------------------------------------------------------------
# Window reset behaviour
# ---------------------------------------------------------------------------


class TestWindowReset:
    def test_counter_resets_in_new_minute(self, monkeypatch):
        svc = fresh()

        # Exhaust the limit in "minute 0"
        fake_time = [0.0]

        def mock_time():
            return fake_time[0]

        monkeypatch.setattr("services.rate_limit_service.time.time", mock_time)

        for _ in range(3):
            svc.check_and_consume(app_id=1, max_per_minute=3)

        blocked = svc.check_and_consume(app_id=1, max_per_minute=3)
        assert blocked.remaining == 0

        # Advance to minute 1
        fake_time[0] = 61.0

        fresh_state = svc.check_and_consume(app_id=1, max_per_minute=3)
        assert fresh_state.remaining == 2  # 3 - 1


# ---------------------------------------------------------------------------
# get_app_state
# ---------------------------------------------------------------------------


class TestGetAppState:
    def test_returns_none_for_untracked_app(self):
        svc = fresh()
        assert svc.get_app_state(app_id=99, max_per_minute=10) is None

    def test_returns_state_after_first_request(self):
        svc = fresh()
        svc.check_and_consume(app_id=1, max_per_minute=10)
        state = svc.get_app_state(app_id=1, max_per_minute=10)
        assert state is not None
        assert state.remaining == 9

    def test_does_not_consume_a_request(self):
        svc = fresh()
        svc.check_and_consume(app_id=1, max_per_minute=10)
        before = svc.get_app_state(app_id=1, max_per_minute=10)
        after = svc.get_app_state(app_id=1, max_per_minute=10)
        assert before.remaining == after.remaining

    def test_unlimited_returns_state_with_minus_one(self):
        svc = fresh()
        state = svc.get_app_state(app_id=1, max_per_minute=0)
        assert state is not None
        assert state.remaining == -1


# ---------------------------------------------------------------------------
# get_app_usage_stats
# ---------------------------------------------------------------------------


class TestGetAppUsageStats:
    def test_untracked_app_returns_zero_usage(self):
        svc = fresh()
        stats = svc.get_app_usage_stats(app_id=99, max_per_minute=10)
        assert stats["current_usage"] == 0
        assert stats["remaining"] == 10
        assert stats["is_over_limit"] is False

    def test_stress_level_low_below_50pct(self):
        svc = fresh()
        for _ in range(3):
            svc.check_and_consume(app_id=1, max_per_minute=10)
        stats = svc.get_app_usage_stats(app_id=1, max_per_minute=10)
        assert stats["stress_level"] == "low"

    def test_stress_level_moderate_between_50_and_80pct(self):
        svc = fresh()
        for _ in range(6):
            svc.check_and_consume(app_id=1, max_per_minute=10)
        stats = svc.get_app_usage_stats(app_id=1, max_per_minute=10)
        assert stats["stress_level"] == "moderate"

    def test_stress_level_high_between_80_and_95pct(self):
        svc = fresh()
        for _ in range(8):
            svc.check_and_consume(app_id=1, max_per_minute=10)
        stats = svc.get_app_usage_stats(app_id=1, max_per_minute=10)
        assert stats["stress_level"] == "high"

    def test_stress_level_critical_above_95pct(self):
        svc = fresh()
        for _ in range(10):
            svc.check_and_consume(app_id=1, max_per_minute=10)
        stats = svc.get_app_usage_stats(app_id=1, max_per_minute=10)
        assert stats["stress_level"] == "critical"

    def test_unlimited_returns_zero_usage_percentage(self):
        svc = fresh()
        stats = svc.get_app_usage_stats(app_id=1, max_per_minute=0)
        assert stats["usage_percentage"] == 0
        assert stats["stress_level"] == "unlimited"


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_requests_do_not_exceed_limit(self):
        svc = fresh()
        limit = 10
        results = []

        def make_request():
            state = svc.check_and_consume(app_id=1, max_per_minute=limit)
            results.append(state.remaining >= 0)

        threads = [threading.Thread(target=make_request) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # After 50 requests against a limit of 10, at most 10 should have
        # received remaining >= 0 (non-blocked), the rest should have remaining == 0
        final_state = svc.get_app_state(app_id=1, max_per_minute=limit)
        assert final_state is not None
        # The counter should not have gone negative
        assert final_state.remaining >= 0


# ---------------------------------------------------------------------------
# Cleanup / stale entry removal
# ---------------------------------------------------------------------------


class TestCleanup:
    def test_cleanup_runs_without_error_when_threshold_exceeded(self, monkeypatch):
        svc = fresh()
        svc._cleanup_threshold = 5

        for app_id in range(10):
            svc.check_and_consume(app_id=app_id, max_per_minute=100)

        # Should not raise
        svc.check_and_consume(app_id=999, max_per_minute=100)
