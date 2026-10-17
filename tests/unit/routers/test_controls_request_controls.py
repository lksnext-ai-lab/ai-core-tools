"""
Unit tests for the step_006 request-control helpers:

- services.rate_limit_service.RateLimitService.check_and_consume_key (separate
  namespace from the per-app check_and_consume counter).
- routers.controls.ip_rate_limit.enforce_ip_rate_limit.
- routers.controls.body_limit.read_body_capped / make_replay_request.
- routers.controls.rate_limit.apply_app_rate_limit and
  routers.controls.origins.check_allowed_origin (the extracted, reusable bodies
  of the existing enforce_* dependencies).

No DB is required; everything here is pure Python / in-memory / ASGI-shaped mocks.
"""
import asyncio
import time
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from services.rate_limit_service import RateLimitService, _OVERFLOW_KEY
from routers.controls.ip_rate_limit import enforce_ip_rate_limit, client_ip_from_request
from routers.controls.body_limit import read_body_capped, make_replay_request, BodyReadAborted
from routers.controls.rate_limit import apply_app_rate_limit
from routers.controls.origins import check_allowed_origin


def fresh_service(**kwargs) -> RateLimitService:
    return RateLimitService(**kwargs)


# ---------------------------------------------------------------------------
# check_and_consume_key — namespace isolation
# ---------------------------------------------------------------------------


class TestCheckAndConsumeKeyNamespaceIsolation:
    def test_blocks_after_n_requests(self):
        svc = fresh_service()
        for _ in range(5):
            state = svc.check_and_consume_key("a2a_discovery:1.2.3.4", 5)
            assert not state.exceeded
        blocked = svc.check_and_consume_key("a2a_discovery:1.2.3.4", 5)
        assert blocked.exceeded
        assert blocked.remaining == 0

    def test_different_keys_are_independent(self):
        svc = fresh_service()
        for _ in range(5):
            svc.check_and_consume_key("a2a_discovery:1.1.1.1", 5)
        other = svc.check_and_consume_key("a2a_discovery:2.2.2.2", 5)
        assert not other.exceeded
        assert other.remaining == 4

    def test_key_namespace_does_not_touch_app_counter(self):
        svc = fresh_service()
        # Exhaust a key-namespace budget that happens to look like an app id.
        for _ in range(3):
            svc.check_and_consume_key("1", 3)
        blocked = svc.check_and_consume_key("1", 3)
        assert blocked.exceeded

        # The app-id counter (separate dict) for app_id=1 must be untouched.
        app_state = svc.check_and_consume(app_id=1, max_per_minute=3)
        assert not app_state.exceeded
        assert app_state.remaining == 2

    def test_unlimited_when_limit_non_positive(self):
        svc = fresh_service()
        state = svc.check_and_consume_key("k", 0)
        assert state.remaining == -1
        state2 = svc.check_and_consume_key("k", -1)
        assert state2.remaining == -1

    def test_key_namespace_has_its_own_lock(self):
        svc = fresh_service()
        assert svc._key_lock is not svc._lock


# ---------------------------------------------------------------------------
# check_and_consume_key — bounded memory via the tracked-key cap / overflow bucket
# ---------------------------------------------------------------------------


class TestCheckAndConsumeKeyBoundedMemory:
    def test_memory_is_capped_at_max_tracked_keys(self):
        svc = fresh_service(key_namespace_max_tracked_keys=10)
        for i in range(1000):
            svc.check_and_consume_key(f"ip-{i}", 1_000_000)
        # 10 distinct keys + 1 shared overflow bucket, never unbounded growth.
        assert len(svc._key_counts) <= 11

    def test_keys_beyond_cap_share_a_single_overflow_bucket_and_are_still_limited(self):
        # multiplier=1 keeps the overflow bucket's budget equal to a single
        # caller's limit, so this test can exercise "still limited" without
        # looping limit*multiplier times. The multiplier itself is covered by
        # test_overflow_bucket_budget_scales_with_multiplier below.
        svc = fresh_service(key_namespace_max_tracked_keys=2, key_namespace_overflow_multiplier=1)
        svc.check_and_consume_key("a", 5)
        svc.check_and_consume_key("b", 5)
        # Cap reached; every subsequent distinct key folds into the overflow bucket.
        for _ in range(5):
            svc.check_and_consume_key("c", 5)
        blocked = svc.check_and_consume_key("d", 5)
        assert blocked.exceeded
        assert _OVERFLOW_KEY in svc._key_counts

    def test_overflow_bucket_budget_scales_with_multiplier(self):
        svc = fresh_service(key_namespace_max_tracked_keys=1, key_namespace_overflow_multiplier=3)
        svc.check_and_consume_key("a", 5)  # fills the only normal slot

        # Overflow budget = max_per_minute (5) * multiplier (3) = 15.
        for i in range(15):
            state = svc.check_and_consume_key(f"overflow-{i}", 5)
            assert not state.exceeded
            assert state.limit == 15

        blocked = svc.check_and_consume_key("overflow-final", 5)
        assert blocked.exceeded
        assert blocked.limit == 15

    def test_overflow_denied_count_is_logged_once_at_the_next_rollover(self, monkeypatch):
        fake_time = [0.0]
        monkeypatch.setattr("services.rate_limit_service.time.monotonic", lambda: fake_time[0])
        svc = fresh_service(key_namespace_max_tracked_keys=1, key_namespace_overflow_multiplier=1)

        svc.check_and_consume_key("a", 1)  # fills the only normal slot (limit=1)
        svc.check_and_consume_key("b", 1)  # overflow; consumes the overflow budget (1)
        for _ in range(3):
            svc.check_and_consume_key("c", 1)  # overflow budget exhausted -> 3 denials

        import services.rate_limit_service as mod
        with patch.object(mod.logger, "warning") as warning_mock:
            fake_time[0] = 61.0  # advance to the next window -> triggers the rollover log
            svc.check_and_consume_key("new-window-key", 1)

        messages = [call.args[0] for call in warning_mock.call_args_list]
        assert any("denied 3 request" in m for m in messages)

    def test_keys_already_tracked_before_the_cap_keep_their_own_budget(self):
        svc = fresh_service(key_namespace_max_tracked_keys=1)
        svc.check_and_consume_key("a", 5)
        # Cap (1) is now reached; "a" was tracked before the cap, so it keeps its
        # own slot and is not folded into the overflow bucket.
        for _ in range(10):
            svc.check_and_consume_key("overflow-trigger", 5)
        state = svc.check_and_consume_key("a", 5)
        assert not state.exceeded
        assert state.remaining == 3  # 5 - 2 consumed ("a" called twice)

    def test_rollover_resets_the_whole_window_in_one_assignment(self, monkeypatch):
        # Patch time.monotonic() BEFORE constructing the service: __init__ seeds
        # `_key_window_start` from the monotonic clock (deliberately NOT the wall
        # clock, so a wall-clock jump can never skip or repeat a rollover), and
        # patching afterwards would leave window_start far ahead of the fake clock,
        # so the rollover would never be detected.
        fake_time = [0.0]
        monkeypatch.setattr("services.rate_limit_service.time.monotonic", lambda: fake_time[0])
        svc = fresh_service()

        for i in range(5):
            svc.check_and_consume_key(f"ip-{i}", 10)
        assert len(svc._key_counts) == 5

        fake_time[0] = 61.0  # advance to the next minute
        svc.check_and_consume_key("ip-new", 10)
        # The old window's keys are gone in one O(1) swap, not individually evicted.
        assert len(svc._key_counts) == 1

    def test_reset_epoch_still_uses_the_wall_clock_even_though_window_tracking_uses_monotonic(self, monkeypatch):
        # Window rollover must use the monotonic clock (see above), but the
        # reset_epoch/Retry-After shown to callers is a wall-clock value they
        # compare against, so it must keep coming from time.time().
        monkeypatch.setattr("services.rate_limit_service.time.monotonic", lambda: 0.0)
        svc = fresh_service()

        real_wall_minute = int(time.time() // 60)
        expected_reset_epoch = (real_wall_minute + 1) * 60

        state = svc.check_and_consume_key("a", 10)
        assert abs(state.reset_epoch - expected_reset_epoch) <= 1

    def test_overflow_warning_logged_at_most_once_per_window(self, monkeypatch):
        # services.rate_limit_service's logger has propagate=False (by design, see
        # utils/logger.py), so pytest's `caplog` fixture (which attaches to the
        # root logger) cannot observe it. Assert on the call count instead.
        import services.rate_limit_service as mod

        svc = fresh_service(key_namespace_max_tracked_keys=1)
        svc.check_and_consume_key("a", 100)

        with patch.object(mod.logger, "warning") as warning_mock:
            for i in range(20):
                svc.check_and_consume_key(f"overflow-{i}", 100)

        assert warning_mock.call_count == 1


# ---------------------------------------------------------------------------
# enforce_ip_rate_limit
# ---------------------------------------------------------------------------


class TestEnforceIpRateLimit:
    def test_allows_under_limit(self, monkeypatch):
        from routers.controls import ip_rate_limit as mod
        fresh = fresh_service()
        monkeypatch.setattr(mod, "rate_limit_service", fresh)

        state = enforce_ip_rate_limit("a2a_discovery", "9.9.9.9", 60)
        assert not state.exceeded

    def test_raises_429_with_headers_when_exceeded(self, monkeypatch):
        from routers.controls import ip_rate_limit as mod
        fresh = fresh_service()
        monkeypatch.setattr(mod, "rate_limit_service", fresh)

        for _ in range(2):
            enforce_ip_rate_limit("a2a_discovery", "9.9.9.9", 2)

        with pytest.raises(HTTPException) as exc_info:
            enforce_ip_rate_limit("a2a_discovery", "9.9.9.9", 2)

        exc = exc_info.value
        assert exc.status_code == 429
        assert "Retry-After" in exc.headers
        assert exc.headers["X-RateLimit-Remaining"] == "0"

    def test_namespace_isolation_between_callers(self, monkeypatch):
        from routers.controls import ip_rate_limit as mod
        fresh = fresh_service()
        monkeypatch.setattr(mod, "rate_limit_service", fresh)

        for _ in range(2):
            enforce_ip_rate_limit("a2a_discovery", "1.1.1.1", 2)

        # A different namespace for the same IP is unaffected.
        state = enforce_ip_rate_limit("other_namespace", "1.1.1.1", 2)
        assert not state.exceeded

    def test_client_ip_from_request_falls_back_to_unknown(self):
        class FakeRequest:
            client = None

        assert client_ip_from_request(FakeRequest()) == "unknown"

    def test_client_ip_from_request_reads_host(self):
        class FakeClient:
            host = "203.0.113.5"

        class FakeRequest:
            client = FakeClient()

        assert client_ip_from_request(FakeRequest()) == "203.0.113.5"

    def test_ipv4_is_not_bucketed(self):
        class FakeClient:
            host = "198.51.100.42"

        class FakeRequest:
            client = FakeClient()

        assert client_ip_from_request(FakeRequest()) == "198.51.100.42"

    def test_ipv6_is_bucketed_by_slash_64(self):
        class FakeClient:
            host = "2001:db8:abcd:1234:ffff:ffff:ffff:ffff"

        class FakeRequest:
            client = FakeClient()

        bucket = client_ip_from_request(FakeRequest())
        assert bucket == "2001:db8:abcd:1234::/64"

    def test_ipv6_addresses_in_the_same_slash_64_share_a_bucket(self):
        class FakeClient1:
            host = "2001:db8:abcd:1234::1"

        class FakeClient2:
            host = "2001:db8:abcd:1234:ffff::2"

        class FakeRequest1:
            client = FakeClient1()

        class FakeRequest2:
            client = FakeClient2()

        assert client_ip_from_request(FakeRequest1()) == client_ip_from_request(FakeRequest2())

    def test_non_ip_host_passes_through_unchanged(self):
        class FakeClient:
            host = "/tmp/some.sock"

        class FakeRequest:
            client = FakeClient()

        assert client_ip_from_request(FakeRequest()) == "/tmp/some.sock"


# ---------------------------------------------------------------------------
# read_body_capped
# ---------------------------------------------------------------------------


class _ScriptedReceive:
    """
    A scripted ASGI receive channel that counts how many times it is actually
    called, so tests can prove reading stops as soon as it should (e.g. right
    after the cap is exceeded, or never at all when a Content-Length pre-check
    already rejects the request).
    """

    def __init__(self, messages: list[dict]):
        self._messages = list(messages)
        self.call_count = 0

    async def __call__(self) -> dict:
        self.call_count += 1
        if self._messages:
            return self._messages.pop(0)
        return {"type": "http.disconnect"}


def _chunks_to_messages(chunks: list[bytes]) -> list[dict]:
    messages = []
    for i, chunk in enumerate(chunks):
        more = i < len(chunks) - 1
        messages.append({"type": "http.request", "body": chunk, "more_body": more})
    return messages


def _make_asgi_request(body_chunks: list[bytes], content_length: int | None = None):
    """Build a minimal Starlette Request over a scripted, call-counting ASGI receive."""
    from starlette.requests import Request

    headers = []
    if content_length is not None:
        headers.append((b"content-length", str(content_length).encode()))

    scope = {
        "type": "http",
        "method": "POST",
        "headers": headers,
        "path": "/x",
        "query_string": b"",
        "client": ("127.0.0.1", 1234),
    }

    receive = _ScriptedReceive(_chunks_to_messages(body_chunks))
    request = Request(scope, receive=receive)
    request.state._test_receive = receive  # keep a handle for assertions
    return request


class TestReadBodyCapped:
    async def test_under_cap_returns_bytes(self):
        request = _make_asgi_request([b"hello ", b"world"])
        body = await read_body_capped(request, max_bytes=100)
        assert body == b"hello world"

    async def test_chunked_over_cap_raises_413_without_content_length(self):
        # No Content-Length header at all (simulates a chunked transfer).
        request = _make_asgi_request([b"a" * 10, b"b" * 10, b"c" * 10], content_length=None)
        receive = request.state._test_receive
        with pytest.raises(HTTPException) as exc_info:
            await read_body_capped(request, max_bytes=15)
        assert exc_info.value.status_code == 413
        assert exc_info.value.detail == "Request body too large"
        # Must stop reading as soon as the cap is exceeded (after the 2nd chunk:
        # 10 + 10 = 20 > 15), never consuming the 3rd scripted chunk.
        assert receive.call_count == 2

    async def test_content_length_over_cap_rejected_before_streaming(self):
        request = _make_asgi_request([b"x" * 50], content_length=50)
        receive = request.state._test_receive
        with pytest.raises(HTTPException) as exc_info:
            await read_body_capped(request, max_bytes=10)
        assert exc_info.value.status_code == 413
        # The Content-Length pre-check must reject before any streaming read.
        assert receive.call_count == 0

    async def test_client_disconnect_mid_read_raises_body_read_aborted(self):
        from starlette.requests import Request

        scope = {
            "type": "http",
            "method": "POST",
            "headers": [],
            "path": "/x",
            "query_string": b"",
            "client": ("127.0.0.1", 1234),
        }
        receive = _ScriptedReceive([
            {"type": "http.request", "body": b"partial", "more_body": True},
            {"type": "http.disconnect"},
        ])
        request = Request(scope, receive=receive)

        with pytest.raises(BodyReadAborted):
            await read_body_capped(request, max_bytes=1000)

    async def test_stalled_read_times_out_with_408(self):
        from starlette.requests import Request

        scope = {
            "type": "http",
            "method": "POST",
            "headers": [],
            "path": "/x",
            "query_string": b"",
            "client": ("127.0.0.1", 1234),
        }

        async def never_resolves() -> dict:
            await asyncio.sleep(10)
            return {"type": "http.disconnect"}

        request = Request(scope, receive=never_resolves)

        with pytest.raises(HTTPException) as exc_info:
            await read_body_capped(request, max_bytes=1000, read_timeout_s=0.05)
        assert exc_info.value.status_code == 408

    async def test_malformed_content_length_falls_back_to_streaming_check(self):
        from starlette.requests import Request

        scope = {
            "type": "http",
            "method": "POST",
            "headers": [(b"content-length", b"not-a-number")],
            "path": "/x",
            "query_string": b"",
            "client": ("127.0.0.1", 1234),
        }
        chunks = [b"short"]

        async def receive():
            if chunks:
                chunk = chunks.pop(0)
                return {"type": "http.request", "body": chunk, "more_body": bool(chunks)}
            return {"type": "http.disconnect"}

        request = Request(scope, receive=receive)
        body = await read_body_capped(request, max_bytes=100)
        assert body == b"short"


# ---------------------------------------------------------------------------
# make_replay_request
# ---------------------------------------------------------------------------


def _bare_scope() -> dict:
    return {
        "type": "http",
        "method": "POST",
        "headers": [],
        "path": "/x",
        "query_string": b"",
        "client": ("127.0.0.1", 1234),
    }


class TestMakeReplayRequest:
    async def test_json_body_is_replayed(self):
        request = _make_asgi_request([b'{"method": "SendMessage"}'])
        body = await read_body_capped(request, max_bytes=1000)
        replay = make_replay_request(request, body)

        data = await replay.json()
        assert data == {"method": "SendMessage"}

    def test_request_state_is_shared(self):
        request = _make_asgi_request([b"{}"])
        request.state.a2a_scope = "sentinel"

        replay = make_replay_request(request, b"{}")
        assert replay.state.a2a_scope == "sentinel"

    async def test_body_is_served_from_the_buffer_without_touching_receive(self):
        from starlette.requests import Request

        receive = _ScriptedReceive([{"type": "http.disconnect"}])
        request = Request(_bare_scope(), receive=receive)
        replay = make_replay_request(request, b"abc")

        body = await replay.body()
        assert body == b"abc"
        assert receive.call_count == 0

    async def test_receive_is_not_wrapped_and_delegates_straight_to_the_real_channel(self):
        from starlette.requests import Request

        receive = _ScriptedReceive([{"type": "http.disconnect"}])
        request = Request(_bare_scope(), receive=receive)
        replay = make_replay_request(request, b"abc")

        message = await replay.receive()
        assert message == {"type": "http.disconnect"}
        assert receive.call_count == 1

    async def test_replay_is_not_disconnected_while_the_real_connection_is_alive(self):
        from starlette.requests import Request

        # The real channel reports "still connected" if asked; the old
        # receive()-wrapping replay would have discarded the buffered body right
        # here (is_disconnected() calls receive() too) and later body() calls
        # would have hung on the real channel instead of returning the buffer.
        receive = _ScriptedReceive([
            {"type": "http.request", "body": b"", "more_body": False},
        ])
        request = Request(_bare_scope(), receive=receive)
        replay = make_replay_request(request, b"abc")

        assert await replay.is_disconnected() is False

    async def test_is_disconnected_called_before_body_does_not_lose_the_buffered_body(self):
        """
        Regression guard (step_006 review, round 2): in Starlette 1.7.0,
        `HTTPConnection.is_disconnected()` calls `receive()` inside an
        immediately-cancelled `anyio.CancelScope`. A replay implementation that
        intercepts `receive()` to hand out a one-shot synthetic body message would
        have that message consumed (and discarded) right there if
        `is_disconnected()` is called first, leaving a later `.body()` call to hang
        on the real channel. `make_replay_request` avoids this by setting `_body`
        directly, which Starlette's `stream()`/`body()`/`json()` serve without ever
        calling `receive()`.
        """
        from starlette.requests import Request

        receive = _ScriptedReceive([
            {"type": "http.request", "body": b"", "more_body": False},
        ])
        request = Request(_bare_scope(), receive=receive)
        replay = make_replay_request(request, b"abc")

        assert await replay.is_disconnected() is False  # consumes the real channel's only message

        body = await replay.body()
        assert body == b"abc"  # still served from the buffer, not lost

    async def test_real_disconnect_propagates_through_is_disconnected_deterministically(self):
        """Deterministic real-disconnect propagation (step_006 review, round 2)."""
        from starlette.requests import Request

        receive = _ScriptedReceive([
            {"type": "http.request", "body": b"abc", "more_body": False},
            {"type": "http.disconnect"},
        ])
        request = Request(_bare_scope(), receive=receive)
        body = await read_body_capped(request, max_bytes=1000)
        replay = make_replay_request(request, body)

        assert await replay.body() == body
        assert await replay.is_disconnected() is True


# ---------------------------------------------------------------------------
# apply_app_rate_limit / check_allowed_origin — extracted reusable bodies
# ---------------------------------------------------------------------------


class _FakeApp:
    def __init__(self, app_id=1, agent_rate_limit=0, agent_cors_origins=""):
        self.app_id = app_id
        self.agent_rate_limit = agent_rate_limit
        self.agent_cors_origins = agent_cors_origins


class TestApplyAppRateLimit:
    def test_unlimited_sets_headers_without_raising(self, monkeypatch):
        import routers.controls.rate_limit as mod
        fresh = fresh_service()
        monkeypatch.setattr(mod, "rate_limit_service", fresh)

        headers: dict = {}
        app = _FakeApp(app_id=1, agent_rate_limit=0)
        apply_app_rate_limit(app, headers)
        assert headers["X-RateLimit-Limit"] == "0"
        assert headers["X-RateLimit-Remaining"] == "-1"

    def test_exceeded_raises_429(self, monkeypatch):
        import routers.controls.rate_limit as mod
        fresh = fresh_service()
        monkeypatch.setattr(mod, "rate_limit_service", fresh)

        app = _FakeApp(app_id=7, agent_rate_limit=1)
        apply_app_rate_limit(app, {})
        with pytest.raises(HTTPException) as exc_info:
            apply_app_rate_limit(app, {})
        assert exc_info.value.status_code == 429


class TestCheckAllowedOrigin:
    def test_allowed_origin_does_not_raise(self):
        app = _FakeApp(agent_cors_origins="https://good.example.com")
        check_allowed_origin(app, "https://good.example.com")

    def test_disallowed_origin_raises_403(self):
        app = _FakeApp(agent_cors_origins="https://good.example.com")
        with pytest.raises(HTTPException) as exc_info:
            check_allowed_origin(app, "https://evil.example.com")
        assert exc_info.value.status_code == 403

    def test_missing_origin_header_is_allowed_for_direct_api_calls(self):
        # origins_service.validate_origin treats a missing Origin header (e.g. a
        # direct, non-browser API call) as allowed, regardless of the allow-list.
        app = _FakeApp(agent_cors_origins="https://good.example.com")
        check_allowed_origin(app, None)

    def test_x_app_id_header_defaults_to_app_id_when_no_app_ref_given(self):
        app = _FakeApp(app_id=42, agent_cors_origins="https://good.example.com")
        with pytest.raises(HTTPException) as exc_info:
            check_allowed_origin(app, "https://evil.example.com")
        assert exc_info.value.headers["X-App-ID"] == "42"

    def test_x_app_id_header_echoes_the_slug_app_ref_when_given(self):
        # Regression guard: the public-API wire contract must be byte-identical to
        # before the apply_*/check_* extraction, including when the caller reached
        # this app via a slug in the URL path rather than its numeric id.
        app = _FakeApp(app_id=42, agent_cors_origins="https://good.example.com")
        with pytest.raises(HTTPException) as exc_info:
            check_allowed_origin(app, "https://evil.example.com", app_ref="my-app-slug")
        assert exc_info.value.headers["X-App-ID"] == "my-app-slug"
