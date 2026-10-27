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
# check_and_consume_for_agent — unlimited mode
# ---------------------------------------------------------------------------


class TestUnlimited:
    def test_unlimited_when_max_zero(self):
        svc = fresh()
        state = svc.check_and_consume_for_agent(app_id=1, agent_id=11, max_per_minute=0)
        assert state.remaining == -1

    def test_unlimited_when_max_negative(self):
        svc = fresh()
        state = svc.check_and_consume_for_agent(app_id=1, agent_id=11, max_per_minute=-5)
        assert state.remaining == -1

    def test_unlimited_never_blocks(self):
        svc = fresh()
        for _ in range(1000):
            state = svc.check_and_consume_for_agent(app_id=1, agent_id=11, max_per_minute=0)
            assert state.remaining == -1


# ---------------------------------------------------------------------------
# check_and_consume_for_agent — limited mode
# ---------------------------------------------------------------------------


class TestLimited:
    def test_first_request_consumes_one(self):
        svc = fresh()
        state = svc.check_and_consume_for_agent(app_id=1, agent_id=11, max_per_minute=10)
        assert state.remaining == 9
        assert state.limit == 10

    def test_remaining_decrements_per_call(self):
        svc = fresh()
        for expected_remaining in range(4, -1, -1):
            state = svc.check_and_consume_for_agent(app_id=1, agent_id=11, max_per_minute=5)
            assert state.remaining == expected_remaining

    def test_blocks_at_limit(self):
        svc = fresh()
        for _ in range(3):
            svc.check_and_consume_for_agent(app_id=1, agent_id=11, max_per_minute=3)
        # 4th call should be blocked
        state = svc.check_and_consume_for_agent(app_id=1, agent_id=11, max_per_minute=3)
        assert state.remaining == 0

    def test_blocked_state_remaining_is_zero(self):
        svc = fresh()
        limit = 2
        for _ in range(limit + 5):
            state = svc.check_and_consume_for_agent(
                app_id=1, agent_id=11, max_per_minute=limit
            )
        assert state.remaining == 0

    def test_reset_epoch_is_next_minute(self):
        svc = fresh()
        state = svc.check_and_consume_for_agent(app_id=1, agent_id=11, max_per_minute=10)
        current_minute = int(time.time() // 60)
        expected_reset = (current_minute + 1) * 60
        # Allow 1s tolerance for slow machines
        assert abs(state.reset_epoch - expected_reset) <= 1

    def test_different_agents_in_the_same_app_have_independent_limits(self):
        svc = fresh()
        for _ in range(3):
            svc.check_and_consume_for_agent(app_id=1, agent_id=11, max_per_minute=3)

        blocked = svc.check_and_consume_for_agent(
            app_id=1, agent_id=11, max_per_minute=3
        )
        other_agent = svc.check_and_consume_for_agent(
            app_id=1, agent_id=12, max_per_minute=3
        )

        assert blocked.exceeded
        assert other_agent.remaining == 2
        assert not other_agent.exceeded

    def test_same_agent_in_different_apps_has_independent_limits(self):
        svc = fresh()
        for _ in range(3):
            svc.check_and_consume_for_agent(app_id=1, agent_id=11, max_per_minute=3)

        other_app = svc.check_and_consume_for_agent(
            app_id=2, agent_id=11, max_per_minute=3
        )

        assert other_app.remaining == 2
        assert not other_app.exceeded

    def test_limit_one_allows_exactly_one(self):
        svc = fresh()
        first = svc.check_and_consume_for_agent(
            app_id=1, agent_id=11, max_per_minute=1
        )
        second = svc.check_and_consume_for_agent(
            app_id=1, agent_id=11, max_per_minute=1
        )
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
            svc.check_and_consume_for_agent(app_id=1, agent_id=11, max_per_minute=3)

        blocked = svc.check_and_consume_for_agent(app_id=1, agent_id=11, max_per_minute=3)
        assert blocked.remaining == 0

        # Advance to minute 1
        fake_time[0] = 61.0

        fresh_state = svc.check_and_consume_for_agent(app_id=1, agent_id=11, max_per_minute=3)
        assert fresh_state.remaining == 2  # 3 - 1


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

    def test_usage_stats_report_the_busiest_agent_not_app_total(self):
        svc = fresh()
        for _ in range(8):
            svc.check_and_consume_for_agent(app_id=1, agent_id=11, max_per_minute=10)
        for _ in range(2):
            svc.check_and_consume_for_agent(app_id=1, agent_id=12, max_per_minute=10)

        stats = svc.get_app_usage_stats(app_id=1, max_per_minute=10)

        assert stats["current_usage"] == 8
        assert stats["usage_percentage"] == 80

    def test_stress_level_low_below_50pct(self):
        svc = fresh()
        for _ in range(3):
            svc.check_and_consume_for_agent(app_id=1, agent_id=11, max_per_minute=10)
        stats = svc.get_app_usage_stats(app_id=1, max_per_minute=10)
        assert stats["stress_level"] == "low"

    def test_stress_level_moderate_between_50_and_80pct(self):
        svc = fresh()
        for _ in range(6):
            svc.check_and_consume_for_agent(app_id=1, agent_id=11, max_per_minute=10)
        stats = svc.get_app_usage_stats(app_id=1, max_per_minute=10)
        assert stats["stress_level"] == "moderate"

    def test_stress_level_high_between_80_and_95pct(self):
        svc = fresh()
        for _ in range(8):
            svc.check_and_consume_for_agent(app_id=1, agent_id=11, max_per_minute=10)
        stats = svc.get_app_usage_stats(app_id=1, max_per_minute=10)
        assert stats["stress_level"] == "high"

    def test_stress_level_critical_above_95pct(self):
        svc = fresh()
        for _ in range(10):
            svc.check_and_consume_for_agent(app_id=1, agent_id=11, max_per_minute=10)
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
            state = svc.check_and_consume_for_agent(
                app_id=1, agent_id=11, max_per_minute=limit
            )
            results.append(not state.exceeded)

        threads = [threading.Thread(target=make_request) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sum(results) == limit


# ---------------------------------------------------------------------------
# Cleanup / stale entry removal
# ---------------------------------------------------------------------------


class TestCleanup:
    def test_cleanup_runs_without_error_when_threshold_exceeded(self, monkeypatch):
        svc = fresh()
        svc._cleanup_threshold = 5

        for agent_id in range(10):
            svc.check_and_consume_for_agent(
                app_id=1, agent_id=agent_id, max_per_minute=100
            )

        # Should not raise
        svc.check_and_consume_for_agent(app_id=1, agent_id=999, max_per_minute=100)
