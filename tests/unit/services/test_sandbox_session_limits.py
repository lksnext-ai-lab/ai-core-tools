"""SandboxSessionService: per-user / per-App limits, switched service, begin_use rollback."""
from __future__ import annotations

import itertools
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services.sandbox_session_service import SandboxCapacityError, SandboxSessionService
from tools.sandbox.provider import SandboxHandle


class Prov:
    PROVIDER_NAME = "fake"
    _ids = itertools.count(1)

    def __init__(self):
        self.created, self.destroyed = [], []

    def create_sandbox(self, working_dir, *, session_key=None, existing_sandbox_id=None):
        sid = f"s{next(self._ids)}"
        self.created.append(session_key)
        return SandboxHandle(sandbox_id=sid, working_dir=working_dir, provider_name="fake", session_key=session_key)

    def touch_sandbox(self, handle, idle_timeout_s):
        pass

    def destroy_sandbox(self, handle):
        self.destroyed.append(handle.session_key)


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setattr("config.SANDBOX_MAX_SESSIONS_PER_USER", 3, raising=False)
    monkeypatch.setattr("config.SANDBOX_MAX_SESSIONS_PER_APP", 10, raising=False)
    monkeypatch.setattr("config.SANDBOX_MAX_CONCURRENT_SESSIONS", 50, raising=False)
    monkeypatch.setattr("config.SANDBOX_EVICT_MIN_IDLE_S", 0, raising=False)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    monkeypatch.setattr("db.database.SessionLocal", lambda: db)


def mk(prov=None):
    svc = SandboxSessionService()
    return svc, prov or Prov()


def open_(svc, prov, key, owner, **kw):
    return svc.get_or_create(key, prov, "/tmp", owner=owner, **kw)


def test_a_users_fourth_session_evicts_their_lru_idle_one_and_never_another_users(monkeypatch):
    svc, prov = mk()
    other = (1, 99)
    open_(svc, prov, "conv_1_100", other)
    for i in (1, 2, 3):
        open_(svc, prov, f"conv_1_{i}", (1, 7))
    svc._sessions["conv_1_2"].last_used -= 100  # least recently used of user 7
    open_(svc, prov, "conv_1_4", (1, 7))
    assert prov.destroyed == ["conv_1_2"]
    assert set(svc._sessions) == {"conv_1_100", "conv_1_1", "conv_1_3", "conv_1_4"}
    # the evicted conversation transparently gets a fresh sandbox on its next turn (its own LRU is evicted)
    open_(svc, prov, "conv_1_2", (1, 7))
    assert prov.created.count("conv_1_2") == 2


def test_all_in_use_raises_for_that_user_only(monkeypatch):
    svc, prov = mk()
    for i in (1, 2, 3):
        open_(svc, prov, f"conv_1_{i}", (1, 7))
        svc._sessions[f"conv_1_{i}"].active_uses = 1
    with pytest.raises(SandboxCapacityError):
        open_(svc, prov, "conv_1_4", (1, 7))
    assert prov.destroyed == []
    open_(svc, prov, "conv_1_50", (1, 8))  # another user still gets one
    assert "conv_1_50" in svc._sessions


def test_app_limit_never_evicts_another_users_session(monkeypatch):
    monkeypatch.setattr("config.SANDBOX_MAX_SESSIONS_PER_APP", 2, raising=False)
    svc, prov = mk()
    open_(svc, prov, "conv_1_1", (1, 1))
    open_(svc, prov, "conv_1_2", (1, 2))
    for e in svc._sessions.values():
        e.last_used -= 1000  # long idle, but not user 3's
    with pytest.raises(SandboxCapacityError):
        open_(svc, prov, "conv_1_3", (1, 3))
    assert prov.destroyed == [] and set(svc._sessions) == {"conv_1_1", "conv_1_2"}
    open_(svc, prov, "conv_2_1", (2, 1))  # another App is not affected


def test_app_limit_evicts_only_the_requesters_own_idle_session(monkeypatch):
    monkeypatch.setattr("config.SANDBOX_MAX_SESSIONS_PER_APP", 2, raising=False)
    svc, prov = mk()
    open_(svc, prov, "conv_1_1", (1, 1))
    open_(svc, prov, "conv_1_2", (1, 2))
    svc._sessions["conv_1_2"].last_used -= 100
    open_(svc, prov, "conv_1_3", (1, 2))  # user 2 is at the App limit: its own idle one makes room
    assert prov.destroyed == ["conv_1_2"] and "conv_1_1" in svc._sessions


def test_a_session_must_be_idle_for_the_minimum_time_before_it_can_be_evicted(monkeypatch):
    monkeypatch.setattr("config.SANDBOX_EVICT_MIN_IDLE_S", 60, raising=False)
    svc, prov = mk()
    for i in (1, 2, 3):
        open_(svc, prov, f"conv_1_{i}", (1, 7))  # all just used: "between two tool calls of a running turn"
    with pytest.raises(SandboxCapacityError):
        open_(svc, prov, "conv_1_4", (1, 7))
    assert prov.destroyed == []
    svc._sessions["conv_1_2"].last_used -= 61
    open_(svc, prov, "conv_1_4", (1, 7))
    assert prov.destroyed == ["conv_1_2"]


def test_a_refused_request_destroys_nothing(monkeypatch):
    """Everything is decided before anything is popped: the per-user step could evict, the App step cannot."""
    monkeypatch.setattr("config.SANDBOX_MAX_SESSIONS_PER_USER", 1, raising=False)
    monkeypatch.setattr("config.SANDBOX_MAX_SESSIONS_PER_APP", 2, raising=False)
    svc, prov = mk()
    open_(svc, prov, "conv_1_1", (1, 7))
    open_(svc, prov, "conv_1_2", (1, 8))
    svc._sessions["conv_1_1"].last_used -= 100
    svc._sessions["conv_1_2"].active_uses = 1
    # user 7 at its user limit (1) AND the App is full (2): evicting conv_1_1 frees both -> allowed
    open_(svc, prov, "conv_1_3", (1, 7))
    assert prov.destroyed == ["conv_1_1"]
    # now user 9 asks: the App is full, user 9 owns nothing evictable -> refused, nothing destroyed
    with pytest.raises(SandboxCapacityError):
        open_(svc, prov, "conv_1_4", (1, 9))
    assert prov.destroyed == ["conv_1_1"] and {"conv_1_2", "conv_1_3"} <= set(svc._sessions)


def test_agents_without_an_owner_are_never_limited_per_user_or_app():
    svc, prov = mk()
    for i in range(15):
        open_(svc, prov, f"conv_1_{i}", None)  # what agents pass (owner only for Chat turns)
    assert len(svc._sessions) == 15 and prov.destroyed == []


def test_sessions_without_a_user_count_towards_the_app_only(monkeypatch):
    monkeypatch.setattr("config.SANDBOX_MAX_SESSIONS_PER_USER", 1, raising=False)
    svc, prov = mk()
    for i in (1, 2, 3):
        open_(svc, prov, f"conv_1_{i}", (1, None))  # no user: the per-user limit never applies
    assert len(svc._sessions) == 3
    assert prov.destroyed == []


def test_zero_means_unlimited_and_no_owner_is_unlimited(monkeypatch):
    monkeypatch.setattr("config.SANDBOX_MAX_SESSIONS_PER_USER", 0, raising=False)
    monkeypatch.setattr("config.SANDBOX_MAX_SESSIONS_PER_APP", 0, raising=False)
    svc, prov = mk()
    for i in range(6):
        open_(svc, prov, f"conv_1_{i}", (1, 7))
        open_(svc, prov, f"conv_9_{i}", None)
    assert len(svc._sessions) == 12 and prov.destroyed == []


def test_pending_creations_count_towards_the_owner():
    svc, prov = mk()
    for i in (1, 2, 3):
        svc._pending_creates.add(f"conv_1_{i}")
        svc._pending_owner[f"conv_1_{i}"] = (1, 7)
    with pytest.raises(SandboxCapacityError):
        open_(svc, prov, "conv_1_4", (1, 7))


def test_a_cached_sandbox_of_another_service_is_destroyed_with_its_own_provider_and_recreated():
    svc = SandboxSessionService()
    old, new = Prov(), Prov()
    first = open_(svc, old, "conv_1_1", (1, 7), sandbox_service_id=1)
    second = open_(svc, new, "conv_1_1", (1, 7), sandbox_service_id=2)
    assert old.destroyed == ["conv_1_1"] and new.destroyed == []
    assert second.sandbox_id != first.sandbox_id and new.created == ["conv_1_1"]
    assert svc._sessions["conv_1_1"].service_id == 2 and svc._sessions["conv_1_1"].provider is new
    again = open_(svc, new, "conv_1_1", (1, 7), sandbox_service_id=2)  # same service: reuse
    assert again is second


def test_app_default_and_system_default_are_distinct_in_both_directions():
    svc = SandboxSessionService()
    a, b = Prov(), Prov()
    first = open_(svc, a, "conv_1_1", (1, 7), sandbox_service_id=5)
    second = open_(svc, b, "conv_1_1", (1, 7), sandbox_service_id=None)  # App default -> system default
    assert a.destroyed == ["conv_1_1"] and second.sandbox_id != first.sandbox_id
    c = Prov()
    third = open_(svc, c, "conv_1_1", (1, 7), sandbox_service_id=5)  # system default -> App default
    assert b.destroyed == ["conv_1_1"] and third.sandbox_id != second.sandbox_id


def test_same_service_id_but_another_provider_class_is_a_switch():
    class Other(Prov):
        pass

    svc = SandboxSessionService()
    a, b = Prov(), Other()
    open_(svc, a, "conv_1_1", (1, 7), sandbox_service_id=None)
    open_(svc, b, "conv_1_1", (1, 7), sandbox_service_id=None)
    assert a.destroyed == ["conv_1_1"]


def test_agents_keep_their_previous_reuse_behaviour_even_with_a_different_service_id():
    svc = SandboxSessionService()
    a, b = Prov(), Prov()
    first = open_(svc, a, "conv_1_1", None, sandbox_service_id=1)
    again = open_(svc, b, "conv_1_1", None, sandbox_service_id=2)
    assert again is first and a.destroyed == []


def test_begin_use_undoes_the_increment_when_the_conversation_is_gone(monkeypatch):
    svc, prov = mk()
    open_(svc, prov, "conv_1_5", (1, 7))

    class Gone:  # a deleted / expired ORM row: any attribute access raises
        def __getattribute__(self, name):
            raise RuntimeError("ObjectDeletedError")

    # persistence resolves the id through the key and finds no row: no exception, and the lease is released after use
    with svc.use("conv_1_5", conversation=Gone()):
        assert svc._sessions["conv_1_5"].active_uses == 1
    assert svc._sessions["conv_1_5"].active_uses == 0

    def boom(*a, **k):
        raise RuntimeError("persist failed")

    monkeypatch.setattr("services.sandbox_session_service._persist_sandbox_state", boom)
    with pytest.raises(RuntimeError):
        svc.begin_use("conv_1_5")
    assert svc._sessions["conv_1_5"].active_uses == 0  # never pinned
    assert svc._sessions["conv_1_5"].lease_expires_at is None


def test_a_turn_that_outlives_a_reset_does_not_resurrect_or_write_back_the_sandbox_state(monkeypatch):
    svc, prov = mk()
    open_(svc, prov, "conv_1_9", (1, 7))
    assert svc.begin_use("conv_1_9")
    svc.destroy("conv_1_9")  # the reset / delete
    writes = []
    monkeypatch.setattr("services.sandbox_session_service._persist_sandbox_state", lambda *a, **k: writes.append(1))
    svc.end_use("conv_1_9")  # the stale turn finishes
    assert svc.begin_use("conv_1_9") is False
    assert writes == [] and "conv_1_9" not in svc._sessions


def test_destroy_all_for_agent_matches_the_anonymous_key_exactly():
    svc, prov = mk()
    for key in ("anon_1", "anon_10", "anon_19", "conv_1_5", "conv_10_5", "thread_1_x", "thread_12_x"):
        open_(svc, prov, key, None)
    svc.destroy_all_for_agent(1)
    assert set(svc._sessions) == {"anon_10", "anon_19", "conv_10_5", "thread_12_x"}
