"""Deletion-hook entry point into the AD-10 maintenance worker (step_018, FR-22).

`schedule_owner_purge` is the only function `AgentService.delete_agent` and `AppService.delete_app`
call: sync, non-blocking and never raising, so a purge-scheduling problem can never fail or block a
deletion. If no worker is running the item is dropped (debug log); the periodic orphan sweep is the
backstop.
"""

from __future__ import annotations

from typing import Optional

from utils.logger import get_logger

logger = get_logger(__name__)


def schedule_owner_purge(app_id: int, agent_id: Optional[int] = None) -> None:
    """Schedules an async cancel + purge of every A2A task under this owner prefix.

    Sync, non-blocking and never raises. Call it after the caller's own commit.

    Args:
        app_id: The app whose agent(s) were deleted.
        agent_id: One agent's prefix (`delete_agent`), or None for the whole app (`delete_app`).
    """
    try:
        from services.a2a_server.maintenance_worker import enqueue_purge

        enqueue_purge(app_id, agent_id)
    except Exception:
        logger.warning(
            "a2a.lifecycle.schedule_purge_failed app_id=%s agent_id=%s",
            app_id, agent_id, exc_info=True,
        )


__all__ = ["schedule_owner_purge"]
