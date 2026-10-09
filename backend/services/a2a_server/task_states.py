"""Single source of truth for the A2A terminal task states and the FAILED-status CAS write.

Used by `runtime.close_runtime` (RB-1 shutdown fail-over), the maintenance worker's stale-task sweep,
`stream_controls`, the router's RB-5 pre-check and the task repository.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import FrozenSet, Optional, Tuple

from a2a.server.cluster.task_store import ConcurrentTaskModificationError, VersionedTaskStore
from a2a.types.a2a_pb2 import Message, Part, Task, TaskState, TaskStatusUpdateEvent

from services.a2a_server.identity import context_for_owner

TERMINAL_TASK_STATES: FrozenSet[int] = frozenset(
    {
        TaskState.TASK_STATE_COMPLETED,
        TaskState.TASK_STATE_CANCELED,
        TaskState.TASK_STATE_FAILED,
        TaskState.TASK_STATE_REJECTED,
    }
)


def failed_status_event(task: Task, message_text: str) -> Tuple[Task, TaskStatusUpdateEvent]:
    """Builds a FAILED copy of `task` and its `TaskStatusUpdateEvent`.

    Always sets `status.timestamp` to now, so a later sweep can tell when the failure was written.

    Args:
        task: The currently stored task.
        message_text: Human-readable status message (never internal error details).

    Returns:
        The updated task and the matching status-update event.
    """
    status_message = Message(
        message_id=str(uuid.uuid4()),
        context_id=task.context_id,
        task_id=task.id,
        parts=[Part(text=message_text)],
    )
    updated = Task()
    updated.CopyFrom(task)
    updated.status.state = TaskState.TASK_STATE_FAILED
    updated.status.message.CopyFrom(status_message)
    updated.status.timestamp.GetCurrentTime()
    event = TaskStatusUpdateEvent(task_id=task.id, context_id=task.context_id, status=updated.status)
    return updated, event


async def fail_task_cas(
    store: VersionedTaskStore,
    task_id: str,
    owner: str,
    message_text: str,
    *,
    stale_before: Optional[datetime] = None,
) -> bool:
    """Reloads `task_id` and, if still non-terminal, CAS-writes it FAILED through `store.save`.

    Args:
        store: The versioned SDK task store.
        task_id: Task to fail.
        owner: The task's AD-3 owner string (scopes the store calls).
        message_text: Status message for the FAILED status.
        stale_before: If given (naive UTC), the write only happens when the *reloaded* task's
            `status.timestamp` is set and older than this cutoff; a task without a timestamp is skipped.

    Returns:
        True if this call wrote the FAILED status; False if the task is missing, terminal, not stale
        (when `stale_before` is given) or the CAS race was lost (`ConcurrentTaskModificationError`).
    """
    ctx = context_for_owner(owner)
    stored = await store.get(task_id, ctx)
    if stored is None or stored.task.status.state in TERMINAL_TASK_STATES:
        return False
    if stale_before is not None:
        if not stored.task.status.HasField("timestamp"):
            return False
        if stored.task.status.timestamp.ToDatetime() >= stale_before:
            return False
    updated, event = failed_status_event(stored.task, message_text)
    try:
        await store.save(updated, event=event, prev=stored.task, prev_version=stored.version, context=ctx)
    except ConcurrentTaskModificationError:
        return False
    return True


__all__ = ["TERMINAL_TASK_STATES", "failed_status_event", "fail_task_cas"]
