"""A Chat turn holds a sandbox lease from the first materialisation until the end of the turn."""
from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services.agent_execution_service import AgentExecutionService, _LazySandboxHandle
from services.sandbox_session_service import SandboxSessionService
from tools.sandbox.provider import SandboxHandle


class Prov:
    PROVIDER_NAME = "fake"
    requires_file_sync = False

    def __init__(self):
        self.n = 0
        self.destroyed = []

    def create_sandbox(self, working_dir, *, session_key=None, existing_sandbox_id=None):
        self.n += 1
        return SandboxHandle(f"s{self.n}", working_dir, "fake", session_key=session_key)

    def touch_sandbox(self, handle, idle_timeout_s):
        pass

    def destroy_sandbox(self, handle):
        self.destroyed.append(handle.sandbox_id)


@pytest.fixture
def svc(monkeypatch):
    service = SandboxSessionService()
    monkeypatch.setattr("services.sandbox_session_service.sandbox_session_service", service)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    monkeypatch.setattr("db.database.SessionLocal", lambda: db)
    monkeypatch.setattr("config.SANDBOX_IDLE_TIMEOUT_S", 120, raising=False)
    return service


def lazy(prov, *, chat):
    return _LazySandboxHandle(
        session_key="conv_1_5", provider=prov, working_dir="/tmp", owner=(1, 7) if chat else None, chat=chat
    )


def ctx_for(handle):
    return SimpleNamespace(sandbox_handle=handle, sandbox_session_key="conv_1_5", conversation=None)


def test_chat_lease_is_taken_at_materialisation_and_the_sandbox_is_never_idle_mid_turn(svc):
    h = lazy(Prov(), chat=True)
    assert "conv_1_5" not in svc._sessions  # nothing before first use
    h.get()
    entry = svc._sessions["conv_1_5"]
    assert entry.active_uses == 1
    entry.last_used -= 10_000  # "idle" for ages between two tool calls: still never reaped / evictable
    svc._reap_stale()
    assert "conv_1_5" in svc._sessions
    assert svc._own_idle_sessions((1, 7), set()) == []


def test_agents_take_no_lease(svc):
    h = lazy(Prov(), chat=False)
    h.get()
    assert svc._sessions["conv_1_5"].active_uses == 0


def test_the_lease_is_released_exactly_once_and_the_reaper_can_then_collect_it(svc):
    prov = Prov()
    h = lazy(prov, chat=True)
    h.get()
    ex = AgentExecutionService.__new__(AgentExecutionService)
    ctx = ctx_for(h)
    for _ in range(3):  # every exit path calls it (success, tool error, model error, timeout, cancellation)
        ex._release_turn_lease(ctx)
    entry = svc._sessions["conv_1_5"]
    assert entry.active_uses == 0 and entry.lease_expires_at is None
    entry.last_used -= 10_000
    svc._reap_stale()
    assert "conv_1_5" not in svc._sessions and prov.destroyed == ["s1"]


def test_nothing_is_released_where_nothing_was_taken(svc):
    ex = AgentExecutionService.__new__(AgentExecutionService)
    never = lazy(Prov(), chat=True)  # busy-rejected / never materialised
    ex._release_turn_lease(ctx_for(never))
    other = lazy(Prov(), chat=True)
    other.get()
    ex._release_turn_lease(ctx_for(never))  # must not touch someone else's lease on the same key
    assert svc._sessions["conv_1_5"].active_uses == 1


def test_after_a_recovery_the_new_sandbox_gets_the_lease(svc):
    prov = Prov()
    h = lazy(prov, chat=True)
    h.get()
    h.invalidate()  # evicts the dead entry (and its lease)
    h.get()
    assert prov.n == 2 and svc._sessions["conv_1_5"].active_uses == 1
    assert svc._sessions["conv_1_5"].owner == (1, 7)  # recovery keeps the owner


# ---------------------------------------------------------------- R3: release never waits for get(); no lease after close


class SlowProv(Prov):
    """create_sandbox blocks on ``gate`` (a slow remote creation holding the proxy's lock inside get())."""

    def __init__(self, gate):
        super().__init__()
        self.gate = gate
        self.entered = threading.Event()

    def create_sandbox(self, working_dir, *, session_key=None, existing_sandbox_id=None):
        self.entered.set()
        self.gate.wait(10)
        return super().create_sandbox(working_dir, session_key=session_key, existing_sandbox_id=existing_sandbox_id)


async def test_cancelling_the_turn_while_get_is_creating_never_blocks_the_event_loop(svc):
    gate = threading.Event()
    prov = SlowProv(gate)
    h = lazy(prov, chat=True)
    ex = AgentExecutionService.__new__(AgentExecutionService)
    worker = threading.Thread(target=h.get, daemon=True)
    worker.start()
    assert await asyncio.to_thread(prov.entered.wait, 5)  # get() now holds the proxy lock inside create_sandbox
    ticks = 0
    for _ in range(50):
        await asyncio.sleep(0)
        ticks += 1
    assert ticks == 50
    # a safety valve so a regression fails (instead of hanging): it frees the creation after 3 s
    rescue = threading.Timer(3, gate.set)
    rescue.start()
    try:
        ex._release_turn_lease(ctx_for(h))  # what the turn's finally does ON the event loop
        assert not gate.is_set(), "release waited for get() (took the proxy lock)"
    finally:
        rescue.cancel()
        gate.set()
        await asyncio.to_thread(worker.join, 5)
    # the turn was closed before the lease was taken: the lease taken by get() afterwards is released at once
    assert svc._sessions["conv_1_5"].active_uses == 0


def test_a_lease_taken_after_the_turn_released_is_never_held(svc):
    prov = Prov()
    h = lazy(prov, chat=True)
    ex = AgentExecutionService.__new__(AgentExecutionService)
    ex._release_turn_lease(ctx_for(h))  # the turn's finally ran first (nothing to release)
    results = []

    def late():  # an abandoned tool thread: first use, then recovery
        h.get()
        h.invalidate()
        h.get()
        results.append(svc._sessions["conv_1_5"].active_uses)

    t = threading.Thread(target=late)
    t.start()
    t.join(5)
    assert results == [0]
    assert h.release_turn_lease() is False


def test_the_reaper_collects_a_long_expired_lease_even_with_an_active_use(svc):
    prov = Prov()
    h = lazy(prov, chat=True)
    h.get()
    entry = svc._sessions["conv_1_5"]
    assert entry.active_uses == 1
    entry.lease_expires_at = time.monotonic() - 10_000  # an abandoned lease long past
    entry.last_used -= 10_000
    svc._reap_stale()
    assert "conv_1_5" not in svc._sessions and prov.destroyed == ["s1"]
    # a live lease is respected
    h2 = lazy(Prov(), chat=True)
    h2.get()
    svc._sessions["conv_1_5"].last_used -= 10_000
    svc._reap_stale()
    assert "conv_1_5" in svc._sessions


# ---------------------------------------------------------------- a short per-call lease never shortens the turn lease


class _Clock:
    def __init__(self):
        self.now = 10_000.0

    def __call__(self):
        return self.now


def test_a_per_call_use_does_not_shorten_the_turn_lease_so_a_running_turn_is_not_reaped(svc, monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(time, "monotonic", clock)  # the module's time source (reaper, begin_use)
    prov = Prov()
    h = lazy(prov, chat=True)
    h.get()  # turn lease: expiry = now + idle ttl + the run timeout (long)
    entry = svc._sessions["conv_1_5"]
    turn_expiry = entry.lease_expires_at
    with svc.use("conv_1_5", expected_seconds=30):  # one short per-call lease (what each tool call takes)
        assert entry.lease_expires_at == turn_expiry  # not replaced by the shorter one
    assert entry.active_uses == 1 and entry.lease_expires_at == turn_expiry  # turn lease still held
    clock.now += 300  # past the per-call expiry + one idle timeout, still inside the turn
    svc._reap_stale()
    assert "conv_1_5" in svc._sessions and prov.destroyed == []


def test_after_the_turn_lease_is_released_an_expired_entry_is_collected(svc, monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(time, "monotonic", clock)
    prov = Prov()
    h = lazy(prov, chat=True)
    h.get()
    with svc.use("conv_1_5", expected_seconds=30):
        pass
    ex = AgentExecutionService.__new__(AgentExecutionService)
    ex._release_turn_lease(ctx_for(h))  # end of turn: count back to 0, expiry cleared
    entry = svc._sessions["conv_1_5"]
    assert entry.active_uses == 0 and entry.lease_expires_at is None
    clock.now += 10_000  # long past every lease
    svc._reap_stale()
    assert "conv_1_5" not in svc._sessions and prov.destroyed == ["s1"]
