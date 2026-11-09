"""Identity a scheduled task runs with (kept free of service imports to avoid import cycles)."""

from typing import Any

from models.scheduled_task import ScheduledTask


def task_user_context(task: ScheduledTask) -> dict[str, Any]:
    """Identity a scheduled task runs its agent with.

    Its conversations belong to the task (no user), files are scoped by the task's own
    session key, system-LLM usage is billed to the creator and metrics report the
    SCHEDULED_TASK channel.
    """
    return {
        "user_id": f"scheduled_task_{task.id}",
        "app_id": task.app_id,
        "scheduled_task_id": task.id,
        "billing_user_id": task.created_by,
        "caller_type_override": "SCHEDULED_TASK",
        "trigger": "scheduled_task",
    }
