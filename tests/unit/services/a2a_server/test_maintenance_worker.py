"""Unit coverage for the AD-10 purge queue in `services.a2a_server.maintenance_worker` (no DB)."""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

from repositories.a2a_task_repository import A2ATaskRepository
from services.a2a_server import maintenance_worker as mw

pytestmark = pytest.mark.unit


def _cfg(grace: float) -> SimpleNamespace:
    return SimpleNamespace(
        purge_grace_seconds=grace,
        sweep_interval_seconds=600,
        task_retention_days=30,
        event_retention_minutes=15,
        task_timeout_seconds=900,
    )


@pytest.fixture
def fake_repo(monkeypatch):
    """Records purge_prefix calls; tracks peak concurrency of DB phases."""
    calls: list = []
    state = {"active": 0, "peak": 0}

    async def _list_nonterminal(prefix):
        return []

    async def _purge_prefix(prefix, batch=500):
        state["active"] += 1
        state["peak"] = max(state["peak"], state["active"])
        await asyncio.sleep(0.02)
        state["active"] -= 1
        calls.append(prefix)
        return 1

    monkeypatch.setattr(A2ATaskRepository, "list_nonterminal_by_prefix", staticmethod(_list_nonterminal))
    monkeypatch.setattr(A2ATaskRepository, "purge_prefix", staticmethod(_purge_prefix))
    monkeypatch.setattr(mw, "get_runtime", lambda: None)
    return SimpleNamespace(calls=calls, state=state)


class _Worker:
    async def __aenter__(self):
        self.task = mw.start_a2a_maintenance_worker()
        return self

    async def __aexit__(self, *exc):
        await mw.stop_a2a_maintenance_worker(self.task)


class TestCoalescing:
    async def test_app_item_drops_agent_items_of_the_same_app(self, fake_repo, monkeypatch):
        monkeypatch.setattr(mw, "get_a2a_config", lambda: _cfg(0))
        async with _Worker():
            mw.enqueue_purge(7, 1)
            mw.enqueue_purge(7, 2)
            mw.enqueue_purge(7)
            mw.enqueue_purge(8, 3)
            await mw.wait_idle()
        assert sorted(fake_repo.calls) == ["a2a:7:", "a2a:8:3:"]

    async def test_agent_item_arriving_while_app_item_in_flight_is_dropped(self, fake_repo, monkeypatch):
        monkeypatch.setattr(mw, "get_a2a_config", lambda: _cfg(0.2))
        async with _Worker():
            mw.enqueue_purge(9)
            await asyncio.sleep(0.05)  # let the app item start its grace period
            mw.enqueue_purge(9, 4)
            await mw.wait_idle()
        assert fake_repo.calls == ["a2a:9:"]


class TestConcurrencyBound:
    async def test_purge_db_phases_never_exceed_the_semaphore(self, fake_repo, monkeypatch):
        monkeypatch.setattr(mw, "get_a2a_config", lambda: _cfg(0))
        async with _Worker():
            for app_id in range(10, 18):
                mw.enqueue_purge(app_id)
            await mw.wait_idle()
        assert len(fake_repo.calls) == 8
        assert fake_repo.state["peak"] <= mw._PURGE_CONCURRENCY


class TestShutdown:
    async def test_stop_during_grace_cancels_without_purging(self, fake_repo, monkeypatch):
        monkeypatch.setattr(mw, "get_a2a_config", lambda: _cfg(60))
        worker = _Worker()
        await worker.__aenter__()
        mw.enqueue_purge(20, 5)
        await asyncio.sleep(0.05)
        loop = asyncio.get_running_loop()
        started = loop.time()
        await worker.__aexit__(None, None, None)
        assert loop.time() - started < mw._STOP_WAIT_SECONDS * 2 + 1
        assert fake_repo.calls == []

    async def test_enqueue_without_worker_is_a_noop(self, fake_repo):
        mw.enqueue_purge(21, 6)  # no worker running: must not raise
        assert fake_repo.calls == []


class TestPurgeFailureLogging:
    async def test_purge_failure_logs_a_warning_with_both_ids(self, monkeypatch, caplog):
        monkeypatch.setattr(mw, "get_a2a_config", lambda: _cfg(0))
        monkeypatch.setattr(mw, "get_runtime", lambda: None)

        async def _empty(prefix):
            return []

        async def _boom(prefix, batch=500):
            raise RuntimeError("simulated")

        monkeypatch.setattr(A2ATaskRepository, "list_nonterminal_by_prefix", staticmethod(_empty))
        monkeypatch.setattr(A2ATaskRepository, "purge_prefix", staticmethod(_boom))
        mw.logger.addHandler(caplog.handler)
        caplog.set_level(logging.WARNING)
        try:
            async with _Worker():
                mw.enqueue_purge(31, 32)
                await mw.wait_idle()
        finally:
            mw.logger.removeHandler(caplog.handler)
        warnings = [r for r in caplog.records if "purge_failed" in r.getMessage()]
        assert len(warnings) == 1
        assert "app_id=31" in warnings[0].getMessage()
        assert "agent_id=32" in warnings[0].getMessage()
