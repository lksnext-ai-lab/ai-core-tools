"""Unit coverage for `services.a2a_server.task_states` (step_018 fix round)."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from a2a.server.cluster.task_store import ConcurrentTaskModificationError
from a2a.types.a2a_pb2 import Task, TaskState, TaskStatus

from services.a2a_server.task_states import TERMINAL_TASK_STATES, fail_task_cas, failed_status_event

pytestmark = pytest.mark.unit

_OWNER = "a2a:1:2:" + "a" * 64


def _task(state: int, *, timestamp: datetime | None = None) -> Task:
    task = Task(id="t1", context_id="c1", status=TaskStatus(state=state))
    if timestamp is not None:
        task.status.timestamp.FromDatetime(timestamp)
    return task


class _FakeStore:
    def __init__(self, task: Task | None, *, raise_on_save: Exception | None = None) -> None:
        self._task = task
        self._raise = raise_on_save
        self.saves: list = []

    async def get(self, task_id, ctx):
        assert ctx.user.user_name == _OWNER
        return None if self._task is None else SimpleNamespace(task=self._task, version=3)

    async def save(self, task, *, event, prev, prev_version, context):
        if self._raise is not None:
            raise self._raise
        self.saves.append((task, event, prev_version))


class TestTerminalStates:
    def test_exactly_the_four_terminal_states(self):
        assert TERMINAL_TASK_STATES == {
            TaskState.TASK_STATE_COMPLETED,
            TaskState.TASK_STATE_CANCELED,
            TaskState.TASK_STATE_FAILED,
            TaskState.TASK_STATE_REJECTED,
        }


class TestFailedStatusEvent:
    def test_sets_failed_message_and_timestamp(self):
        updated, event = failed_status_event(_task(TaskState.TASK_STATE_WORKING), "worker shutdown")
        assert updated.status.state == TaskState.TASK_STATE_FAILED
        assert updated.status.message.parts[0].text == "worker shutdown"
        assert updated.status.HasField("timestamp")
        assert event.task_id == "t1"
        assert event.status.state == TaskState.TASK_STATE_FAILED


class TestFailTaskCas:
    async def test_writes_failed_for_a_non_terminal_task(self):
        store = _FakeStore(_task(TaskState.TASK_STATE_WORKING))
        assert await fail_task_cas(store, "t1", _OWNER, "boom") is True
        saved_task, _, prev_version = store.saves[0]
        assert saved_task.status.state == TaskState.TASK_STATE_FAILED
        assert prev_version == 3

    async def test_skips_a_missing_task(self):
        assert await fail_task_cas(_FakeStore(None), "t1", _OWNER, "boom") is False

    async def test_skips_a_terminal_task(self):
        store = _FakeStore(_task(TaskState.TASK_STATE_COMPLETED))
        assert await fail_task_cas(store, "t1", _OWNER, "boom") is False
        assert store.saves == []

    async def test_lost_cas_race_returns_false(self):
        store = _FakeStore(
            _task(TaskState.TASK_STATE_WORKING), raise_on_save=ConcurrentTaskModificationError("raced")
        )
        assert await fail_task_cas(store, "t1", _OWNER, "boom") is False

    async def test_stale_before_skips_a_task_without_timestamp(self):
        store = _FakeStore(_task(TaskState.TASK_STATE_WORKING))
        assert await fail_task_cas(store, "t1", _OWNER, "boom", stale_before=datetime.utcnow()) is False
        assert store.saves == []

    async def test_stale_before_skips_a_task_refreshed_after_the_cutoff(self):
        cutoff = datetime.utcnow() - timedelta(minutes=10)
        store = _FakeStore(_task(TaskState.TASK_STATE_WORKING, timestamp=datetime.utcnow()))
        assert await fail_task_cas(store, "t1", _OWNER, "boom", stale_before=cutoff) is False
        assert store.saves == []

    async def test_stale_before_fails_a_task_older_than_the_cutoff(self):
        cutoff = datetime.utcnow() - timedelta(minutes=10)
        store = _FakeStore(_task(TaskState.TASK_STATE_WORKING, timestamp=cutoff - timedelta(minutes=1)))
        assert await fail_task_cas(store, "t1", _OWNER, "boom", stale_before=cutoff) is True
        assert len(store.saves) == 1
