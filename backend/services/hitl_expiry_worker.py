"""Background sweep that resolves expired human-in-the-loop approvals.

An approval nobody answered before ``expires_at`` is resumed with *reject* decisions
(LangChain's documented ``Command(resume=...)`` path), so its conversation is unpaused and
gets the agent's final answer. Approvals are never approved automatically.

Every replica and uvicorn worker runs the loop; each sweep first takes a PostgreSQL
advisory lock on a dedicated connection, so only one sweeps at a time, and every row is
also claimed with a compare-and-set before it is touched.

The sweep also recovers approvals left mid-transition by a crashed process: once a row
in ``deciding``/``expiring`` is older than any run could take, it goes back to
``pending`` if its pause is still in the checkpoint (it then expires normally) or is
closed as ``cancelled`` otherwise.
"""
from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text

from db.database import SessionLocal, engine
from models.hitl_approval import ApprovalStatus
from repositories.hitl_approval_repository import HITLApprovalRepository
from tools.stream_guard import AGENT_RUN_TIMEOUT_SECONDS
from utils.config import Config
from utils.logger import get_logger

logger = get_logger(__name__)

SWEEP_INTERVAL_SECONDS: int = Config.get_int_env_var("HITL_EXPIRY_SWEEP_SECONDS", default=60)
SWEEPER_ENABLED: bool = Config.get_bool_env_var("HITL_EXPIRY_SWEEPER_ENABLED", default=True)
BATCH_SIZE = 20
# Stable 64-bit key for pg_try_advisory_lock: int.from_bytes(b"hitlexp1", "big"). Never change it.
_ADVISORY_LOCK_KEY = 0x6869746C65787031
_STUCK_MARGIN = timedelta(seconds=AGENT_RUN_TIMEOUT_SECONDS + 300)


async def _recover_stuck(db) -> None:
    from services.agent_cache_service import CheckpointerCacheService

    older_than = datetime.now(timezone.utc) - _STUCK_MARGIN
    stuck_ids = HITLApprovalRepository.list_stuck_ids(
        db, (ApprovalStatus.DECIDING, ApprovalStatus.EXPIRING), older_than, BATCH_SIZE
    )
    for approval_id in stuck_ids:
        approval = HITLApprovalRepository.get(db, approval_id)
        if approval is None:
            continue
        session_id = approval.thread_id.removeprefix(f"thread_{approval.agent_id}_")
        still_paused = bool(await CheckpointerCacheService.get_pending_tool_calls_async(approval.agent_id, session_id))
        if still_paused:
            approval.status = ApprovalStatus.PENDING.value
        else:
            approval.status = ApprovalStatus.CANCELLED.value
            approval.resolution_reason = "interrupted"
            approval.decided_at = datetime.now(timezone.utc)
        approval.last_error = "Recovered after the process resolving it stopped"
        db.commit()
        logger.warning("HITL approval %s recovered from a stuck transition -> %s", approval_id, approval.status)


async def sweep_once() -> int:
    """Expire due approvals if this process wins the sweep lock. Returns how many were expired."""
    from services.agent_execution_service import AgentExecutionService

    with engine.connect() as lock_conn:
        if not lock_conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _ADVISORY_LOCK_KEY}).scalar():
            return 0
        db = SessionLocal()
        expired = 0
        try:
            await _recover_stuck(db)
            service = AgentExecutionService()
            for approval_id in HITLApprovalRepository.list_expired_pending_ids(db, BATCH_SIZE):
                try:
                    if await service.expire_approval(db, approval_id):
                        expired += 1
                except Exception as exc:
                    # The row is back to pending (or stuck-recovered later) and retried next sweep.
                    db.rollback()
                    logger.warning("Could not expire HITL approval %s: %s", approval_id, type(exc).__name__)
            return expired
        finally:
            db.close()
            lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _ADVISORY_LOCK_KEY})
            lock_conn.commit()


async def _loop() -> None:
    while True:
        try:
            expired = await sweep_once()
            if expired:
                logger.info("HITL expiry sweep resolved %d approval(s)", expired)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("HITL expiry sweep failed")
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)


def start_hitl_expiry_worker() -> Optional[asyncio.Task]:
    if not SWEEPER_ENABLED:
        logger.info("HITL expiry sweeper disabled (HITL_EXPIRY_SWEEPER_ENABLED=false)")
        return None
    return asyncio.create_task(_loop(), name="hitl-expiry-sweeper")


async def stop_hitl_expiry_worker(task: Optional[asyncio.Task]) -> None:
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
