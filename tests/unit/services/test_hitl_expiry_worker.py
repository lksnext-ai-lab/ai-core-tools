"""Unit tests for the human-approval expiry sweeper (DB, lock and agent runs mocked)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.hitl_approval import ApprovalStatus
from services import hitl_expiry_worker as worker


def _lock(acquired: bool) -> MagicMock:
    conn = MagicMock()
    conn.execute.return_value.scalar.return_value = acquired
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    return engine


class TestSweepOnce:
    @pytest.mark.asyncio
    async def test_skips_when_another_process_holds_the_lock(self):
        with patch.object(worker, "engine", _lock(False)), patch.object(worker, "SessionLocal") as session_local:
            assert await worker.sweep_once() == 0
        session_local.assert_not_called()

    @pytest.mark.asyncio
    async def test_expires_due_approvals_and_survives_a_failing_one(self):
        db = MagicMock()
        service = MagicMock()
        service.expire_approval = AsyncMock(side_effect=[True, RuntimeError("boom"), False])
        with patch.object(worker, "engine", _lock(True)), \
                patch.object(worker, "SessionLocal", return_value=db), \
                patch.object(worker, "_recover_stuck", AsyncMock()), \
                patch.object(worker.HITLApprovalRepository, "list_expired_pending_ids", return_value=["a", "b", "c"]), \
                patch("services.agent_execution_service.AgentExecutionService", return_value=service):
            expired = await worker.sweep_once()

        assert expired == 1
        db.rollback.assert_called_once()
        db.close.assert_called_once()


class TestRecoverStuck:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("still_paused, expected", [
        (True, ApprovalStatus.PENDING),
        (False, ApprovalStatus.CANCELLED),
    ])
    async def test_stuck_transition_goes_back_to_pending_or_is_cancelled(self, still_paused, expected):
        approval = SimpleNamespace(
            agent_id=3, thread_id="thread_3_conv_3_x", status=ApprovalStatus.DECIDING.value,
            resolution_reason=None, decided_at=None, last_error=None,
        )
        db = MagicMock()
        pending = [{"id": "call_1"}] if still_paused else []
        with patch.object(worker.HITLApprovalRepository, "list_stuck_ids", return_value=["a"]), \
                patch.object(worker.HITLApprovalRepository, "get", return_value=approval), \
                patch("services.agent_cache_service.CheckpointerCacheService.get_pending_tool_calls_async",
                      AsyncMock(return_value=pending)) as pending_calls:
            await worker._recover_stuck(db)

        pending_calls.assert_awaited_once_with(3, "conv_3_x")
        assert approval.status == expected.value
        assert approval.last_error
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_row_is_skipped(self):
        db = MagicMock()
        with patch.object(worker.HITLApprovalRepository, "list_stuck_ids", return_value=["gone"]), \
                patch.object(worker.HITLApprovalRepository, "get", return_value=None):
            await worker._recover_stuck(db)
        db.commit.assert_not_called()


class TestWorkerLifecycle:
    def test_disabled_sweeper_does_not_start(self):
        with patch.object(worker, "SWEEPER_ENABLED", False):
            assert worker.start_hitl_expiry_worker() is None

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        with patch.object(worker, "SWEEPER_ENABLED", True), \
                patch.object(worker, "sweep_once", AsyncMock(return_value=0)), \
                patch.object(worker, "SWEEP_INTERVAL_SECONDS", 3600):
            task = worker.start_hitl_expiry_worker()
            await asyncio.sleep(0)
            await worker.stop_hitl_expiry_worker(task)
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_stop_without_task_is_a_no_op(self):
        await worker.stop_hitl_expiry_worker(None)

    @pytest.mark.asyncio
    async def test_loop_keeps_running_after_a_failed_sweep(self):
        sweeps = AsyncMock(side_effect=[RuntimeError("db down"), 2, asyncio.CancelledError()])
        with patch.object(worker, "sweep_once", sweeps), \
                patch.object(worker.asyncio, "sleep", AsyncMock()):
            with pytest.raises(asyncio.CancelledError):
                await worker._loop()
        assert sweeps.await_count == 3
