"""Unit tests for services.auth.login_throttle.

InProcessLoginThrottle and the helper functions are pure Python with no DB or
external dependencies — all tests are fast and fully isolated.

Covers:
- Per-IP window: allows up to N then blocks.
- Per-account window: independent counter from IP.
- Window reset: counter resets in a new calendar minute.
- reset(): clears a key so a subsequent hit is allowed again.
- Unlimited mode (per_minute=0): always allowed.
- Thread-safety smoke: concurrent hits do not exceed the limit.
- cleanup_if_needed: stale entries are pruned.
- extract_client_ip: respects TRUST_PROXY_HEADERS flag.
"""

import os
import threading

import pytest

# Ensure SECRET_KEY is set before any backend import so the Config module loads
# without failing the startup fail-fast check.
os.environ.setdefault("SECRET_KEY", "test-secret-key-32chars-minimum-ok")


from services.auth.login_throttle import (
    ERR_TOO_MANY_REQUESTS,
    InProcessLoginThrottle,
    ThrottleState,
    extract_client_ip,
    hit_account_throttle,
    reset_account_throttle,
)
from schemas.local_auth_schemas import LoginRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def fresh(per_minute: int = 5) -> InProcessLoginThrottle:
    """Return a new ``InProcessLoginThrottle`` instance to avoid state leakage."""
    return InProcessLoginThrottle(per_minute=per_minute)


# ---------------------------------------------------------------------------
# ThrottleState dataclass
# ---------------------------------------------------------------------------


class TestThrottleState:
    def test_fields_accessible(self):
        s = ThrottleState(allowed=True, remaining=4, retry_after_seconds=0)
        assert s.allowed is True
        assert s.remaining == 4
        assert s.retry_after_seconds == 0

    def test_not_allowed_state(self):
        s = ThrottleState(allowed=False, remaining=0, retry_after_seconds=42)
        assert s.allowed is False
        assert s.retry_after_seconds == 42


# ---------------------------------------------------------------------------
# Unlimited mode (per_minute=0)
# ---------------------------------------------------------------------------


class TestUnlimitedMode:
    def test_unlimited_always_allows(self):
        t = fresh(per_minute=0)
        for _ in range(100):
            state = t.hit("ip:1.2.3.4")
            assert state.allowed is True

    def test_unlimited_remaining_is_minus_one(self):
        t = fresh(per_minute=0)
        state = t.hit("ip:1.2.3.4")
        assert state.remaining == -1

    def test_unlimited_retry_after_is_zero(self):
        t = fresh(per_minute=0)
        state = t.hit("ip:1.2.3.4")
        assert state.retry_after_seconds == 0


# ---------------------------------------------------------------------------
# Per-IP window
# ---------------------------------------------------------------------------


class TestPerIpWindow:
    def test_first_hit_is_allowed(self):
        t = fresh(per_minute=3)
        state = t.hit("ip:10.0.0.1")
        assert state.allowed is True

    def test_remaining_decrements(self):
        t = fresh(per_minute=5)
        for expected_remaining in range(4, -1, -1):
            state = t.hit("ip:10.0.0.1")
            assert state.remaining == expected_remaining

    def test_blocks_after_limit(self):
        t = fresh(per_minute=3)
        for _ in range(3):
            t.hit("ip:10.0.0.1")
        # 4th hit must be blocked
        state = t.hit("ip:10.0.0.1")
        assert state.allowed is False
        assert state.remaining == 0

    def test_blocked_state_remaining_is_zero(self):
        t = fresh(per_minute=2)
        for _ in range(10):
            state = t.hit("ip:10.0.0.1")
        assert state.remaining == 0
        assert state.allowed is False

    def test_limit_one_allows_exactly_one(self):
        t = fresh(per_minute=1)
        first = t.hit("ip:10.0.0.1")
        second = t.hit("ip:10.0.0.1")
        assert first.allowed is True
        assert second.allowed is False

    def test_different_ips_are_independent(self):
        t = fresh(per_minute=3)
        for _ in range(3):
            t.hit("ip:10.0.0.1")
        # ip:10.0.0.2 should be fresh
        state = t.hit("ip:10.0.0.2")
        assert state.allowed is True
        assert state.remaining == 2

    def test_retry_after_is_positive_when_blocked(self):
        t = fresh(per_minute=1)
        t.hit("ip:10.0.0.1")
        blocked = t.hit("ip:10.0.0.1")
        assert blocked.allowed is False
        assert blocked.retry_after_seconds > 0
        assert blocked.retry_after_seconds <= 60


# ---------------------------------------------------------------------------
# Per-account window (independent counter)
# ---------------------------------------------------------------------------


class TestPerAccountWindow:
    def test_account_counter_independent_from_ip(self):
        """Exhausting per-IP does not affect per-account counter."""
        t = fresh(per_minute=2)
        for _ in range(2):
            t.hit("ip:10.0.0.1")
        # IP is now blocked; account key is untouched
        account_state = t.hit("account:user@example.com")
        assert account_state.allowed is True

    def test_two_accounts_are_independent(self):
        t = fresh(per_minute=2)
        for _ in range(2):
            t.hit("account:alice@example.com")
        # alice is blocked; bob is unaffected
        state = t.hit("account:bob@example.com")
        assert state.allowed is True

    def test_account_key_blocks_at_limit(self):
        t = fresh(per_minute=2)
        t.hit("account:carol@example.com")
        t.hit("account:carol@example.com")
        blocked = t.hit("account:carol@example.com")
        assert blocked.allowed is False


# ---------------------------------------------------------------------------
# Window reset behaviour (monkeypatched time)
# ---------------------------------------------------------------------------


class TestWindowReset:
    def test_counter_resets_in_new_minute(self, monkeypatch):
        t = fresh(per_minute=2)
        fake_time = [0.0]

        def mock_time():
            return fake_time[0]

        monkeypatch.setattr("services.auth.login_throttle.time.time", mock_time)

        # Exhaust window in "minute 0"
        t.hit("ip:10.0.0.1")
        t.hit("ip:10.0.0.1")
        blocked = t.hit("ip:10.0.0.1")
        assert blocked.allowed is False

        # Advance to minute 1
        fake_time[0] = 61.0
        fresh_state = t.hit("ip:10.0.0.1")
        assert fresh_state.allowed is True
        assert fresh_state.remaining == 1  # 2 - 1


# ---------------------------------------------------------------------------
# reset()
# ---------------------------------------------------------------------------


class TestReset:
    def test_reset_clears_key(self):
        t = fresh(per_minute=2)
        t.hit("account:dave@example.com")
        t.hit("account:dave@example.com")
        blocked = t.hit("account:dave@example.com")
        assert blocked.allowed is False

        t.reset("account:dave@example.com")

        # Counter cleared — first hit should be allowed again
        state = t.hit("account:dave@example.com")
        assert state.allowed is True

    def test_reset_nonexistent_key_does_not_raise(self):
        t = fresh(per_minute=5)
        # Must not raise
        t.reset("account:ghost@example.com")

    def test_reset_does_not_affect_other_keys(self):
        t = fresh(per_minute=1)
        t.hit("account:alice@example.com")
        t.hit("account:bob@example.com")
        t.reset("account:alice@example.com")
        # Bob's counter is untouched
        state = t.hit("account:bob@example.com")
        assert state.allowed is False


# ---------------------------------------------------------------------------
# Thread-safety smoke test
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_hits_do_not_exceed_limit(self):
        """50 concurrent threads hitting a limit of 10 must not produce a
        counter value below 0 or grant more than ``limit`` allowed responses."""
        limit = 10
        t = fresh(per_minute=limit)
        allowed_count = []
        lock = threading.Lock()

        def make_hit():
            state = t.hit("ip:192.168.1.1")
            if state.allowed:
                with lock:
                    allowed_count.append(1)

        threads = [threading.Thread(target=make_hit) for _ in range(50)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        # At most ``limit`` hits should have been granted.
        assert len(allowed_count) <= limit
        # At least half of the limit must have been granted — a regression that
        # allows zero slots (e.g. a missed increment or broken locking) is caught.
        assert len(allowed_count) >= limit // 2
        # The counter must not be negative.
        with t._lock:
            stored = t._counters.get("ip:192.168.1.1", {}).get("count", 0)
        assert stored >= 0

    def test_reset_is_thread_safe(self):
        """Concurrent resets and hits should not raise."""
        t = fresh(per_minute=5)
        errors = []

        def hit_and_reset():
            try:
                t.hit("account:shared@example.com")
                t.reset("account:shared@example.com")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=hit_and_reset) for _ in range(30)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert not errors, f"Thread-safety errors: {errors}"


# ---------------------------------------------------------------------------
# Cleanup / stale entry pruning
# ---------------------------------------------------------------------------


class TestCleanup:
    def test_cleanup_runs_without_error_when_threshold_exceeded(self, monkeypatch):
        t = InProcessLoginThrottle(per_minute=100, cleanup_threshold=5)

        fake_time = [0.0]

        def mock_time():
            return fake_time[0]

        monkeypatch.setattr("services.auth.login_throttle.time.time", mock_time)

        # Populate 7 keys in minute 0
        for i in range(7):
            t.hit(f"ip:10.0.0.{i}")

        # Advance to minute 2 so all minute-0 entries are stale
        fake_time[0] = 121.0

        # This hit triggers the cleanup path — should not raise
        t.hit("ip:10.0.0.99")
        # Stale entries should have been pruned
        with t._lock:
            count_after = len(t._counters)
        # Only the fresh entry added in minute 2 should remain (or very few)
        assert count_after <= 2


# ---------------------------------------------------------------------------
# extract_client_ip helper
# ---------------------------------------------------------------------------


class TestExtractClientIp:
    def _make_request(self, forwarded_for: str | None = None, host: str | None = None):
        """Build a minimal mock Request object."""

        class FakeClient:
            def __init__(self, h):
                self.host = h

        class FakeHeaders:
            def __init__(self, fwd):
                self._fwd = fwd

            def get(self, name):
                if name.lower() == "x-forwarded-for":
                    return self._fwd
                return None

        class FakeRequest:
            def __init__(self, fwd, h):
                self.headers = FakeHeaders(fwd)
                self.client = FakeClient(h) if h else None

        return FakeRequest(forwarded_for, host)

    def test_uses_first_hop_from_x_forwarded_for_when_trust_proxy_true(self, monkeypatch):
        monkeypatch.setattr("services.auth.login_throttle._TRUST_PROXY", True)
        req = self._make_request(forwarded_for="1.2.3.4, 5.6.7.8", host="10.0.0.1")
        assert extract_client_ip(req) == "1.2.3.4"

    def test_falls_back_to_client_host_when_no_forwarded_for(self, monkeypatch):
        monkeypatch.setattr("services.auth.login_throttle._TRUST_PROXY", True)
        req = self._make_request(forwarded_for=None, host="10.0.0.1")
        assert extract_client_ip(req) == "10.0.0.1"

    def test_ignores_x_forwarded_for_when_trust_proxy_false(self, monkeypatch):
        monkeypatch.setattr("services.auth.login_throttle._TRUST_PROXY", False)
        req = self._make_request(forwarded_for="1.2.3.4", host="10.0.0.1")
        assert extract_client_ip(req) == "10.0.0.1"

    def test_returns_none_when_no_client_and_no_header(self, monkeypatch):
        monkeypatch.setattr("services.auth.login_throttle._TRUST_PROXY", True)
        req = self._make_request(forwarded_for=None, host=None)
        assert extract_client_ip(req) is None

    def test_strips_whitespace_from_forwarded_for(self, monkeypatch):
        monkeypatch.setattr("services.auth.login_throttle._TRUST_PROXY", True)
        req = self._make_request(forwarded_for="  9.9.9.9 , 1.1.1.1", host="10.0.0.1")
        assert extract_client_ip(req) == "9.9.9.9"


# ---------------------------------------------------------------------------
# hit_account_throttle / reset_account_throttle helpers
# ---------------------------------------------------------------------------


class TestAccountThrottleHelpers:
    """Smoke-test the module-level helper functions used by the login route.

    These call the module-level ``_account_throttle`` singleton — we patch it
    to keep tests isolated from each other.
    """

    def test_hit_account_throttle_returns_allowed_state(self, monkeypatch):
        stub = InProcessLoginThrottle(per_minute=10)
        monkeypatch.setattr("services.auth.login_throttle._account_throttle", stub)

        state = hit_account_throttle("user@test.com")
        assert state.allowed is True

    def test_hit_account_throttle_returns_blocked_state_with_retry_after(self, monkeypatch):
        """When the account slot is exhausted the returned state carries retry_after_seconds.

        The ``Retry-After`` header is the caller's responsibility — it passes
        ``headers={"Retry-After": str(state.retry_after_seconds)}`` directly to
        ``HTTPException`` so Starlette's handler carries it onto the response.
        """
        stub = InProcessLoginThrottle(per_minute=1)
        monkeypatch.setattr("services.auth.login_throttle._account_throttle", stub)

        stub.hit("account:user@test.com")  # exhaust the single slot
        state = hit_account_throttle("user@test.com")
        assert state.allowed is False
        assert state.retry_after_seconds > 0

    def test_reset_account_throttle_clears_key(self, monkeypatch):
        stub = InProcessLoginThrottle(per_minute=1)
        monkeypatch.setattr("services.auth.login_throttle._account_throttle", stub)

        stub.hit("account:user@test.com")
        blocked = hit_account_throttle("user@test.com")
        assert blocked.allowed is False

        reset_account_throttle("user@test.com")

        state = hit_account_throttle("user@test.com")
        assert state.allowed is True


# ---------------------------------------------------------------------------
# LoginRequest email normalisation (schema validator)
# ---------------------------------------------------------------------------


class TestLoginRequestEmailNormalisation:
    """Verify that the LoginRequest schema normalises email before it reaches the throttle.

    FR-E2 requires that ``Alice@X.com`` and ``alice@x.com`` map to the same
    throttle bucket.  The canonical place to enforce this is the schema validator
    so that the throttle key, DB lookup, and lockout all operate on the same value.
    """

    def test_email_is_lowercased(self):
        req = LoginRequest(email="Alice@Example.COM", password="ValidPassw0rd!")
        assert req.email == "alice@example.com"

    def test_email_whitespace_is_stripped(self):
        req = LoginRequest(email="  user@example.com  ", password="ValidPassw0rd!")
        assert req.email == "user@example.com"

    def test_mixed_case_and_whitespace_normalised(self):
        """Alice@X.com and alice@x.com must share one throttle bucket."""
        req_upper = LoginRequest(email="Alice@X.com ", password="ValidPassw0rd!")
        req_lower = LoginRequest(email="alice@x.com", password="ValidPassw0rd!")
        assert req_upper.email == req_lower.email == "alice@x.com"

    def test_err_too_many_requests_is_single_canonical_string(self):
        """The public constant must match the string used in the router to avoid drift."""
        assert ERR_TOO_MANY_REQUESTS == "Too many requests. Please try again later."
