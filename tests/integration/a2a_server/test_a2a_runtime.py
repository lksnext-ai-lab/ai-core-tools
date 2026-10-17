"""Integration smoke test for `services.a2a_server.runtime` (step_012).

Builds a real `A2ARuntime` (SDK store/stream bound to the `a2a_*` tables,
real test DB) via the committed `a2a_committed_world`/`a2a_runtime_factory`
fixtures, and drives it through `DefaultRequestHandlerV2.on_message_send`
directly -- exactly the call the real JSON-RPC dispatcher makes, minus the
HTTP layer (that is step_017's router).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.context import ServerCallContext
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import a2a_pb2 as pb
from a2a.utils.errors import InvalidParamsError, TaskNotFoundError

from services.a2a_server.identity import A2ACallerUser, owner_for
from services.a2a_server.sdk_models import get_sdk_models
from utils.security import hash_api_key

pytestmark = pytest.mark.integration


class _EchoExecutor(AgentExecutor):
    """Mirrors AD-8: enqueues the initial Task if missing, starts work, completes."""

    async def execute(self, context, event_queue) -> None:
        if context.current_task is None:
            await event_queue.enqueue_event(
                pb.Task(
                    id=context.task_id,
                    context_id=context.context_id,
                    status=pb.TaskStatus(state=pb.TaskState.TASK_STATE_SUBMITTED),
                    history=[context.message] if context.message is not None else [],
                )
            )
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.start_work()
        await updater.complete()

    async def cancel(self, context, event_queue) -> None:  # pragma: no cover - not exercised here
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.cancel()


def _context_for(owner: str) -> ServerCallContext:
    return ServerCallContext(user=A2ACallerUser(owner), state={"headers": {"a2a-version": "1.0"}})


def _send_request(text: str = "hello") -> pb.SendMessageRequest:
    return pb.SendMessageRequest(
        message=pb.Message(message_id=str(uuid.uuid4()), role=pb.ROLE_USER, parts=[pb.Part(text=text)])
    )


class TestA2ARuntimeSmoke:
    def test_message_send_completes_and_is_stored_under_the_expected_owner(
        self, a2a_committed_world, a2a_runtime_factory
    ):
        world = a2a_committed_world
        runtime = a2a_runtime_factory(_EchoExecutor())
        owner = owner_for(world.app_id, world.agent_public_id, hash_api_key(world.key_1_raw))

        result = asyncio.run(
            runtime.handler.on_message_send(_send_request(), _context_for(owner))
        )

        assert isinstance(result, pb.Task)
        assert result.status.state == pb.TaskState.TASK_STATE_COMPLETED

        models = get_sdk_models()
        from db.database import SessionLocal

        session = SessionLocal()
        try:
            stored = session.get(models.task, result.id)
            assert stored is not None
            assert stored.owner == owner
        finally:
            session.close()

    def test_a_malformed_inline_part_is_rejected_before_any_task_is_created(
        self, a2a_committed_world, a2a_runtime_factory
    ):
        world = a2a_committed_world
        runtime = a2a_runtime_factory(_EchoExecutor())
        owner = owner_for(world.app_id, world.agent_public_id, hash_api_key(world.key_1_raw))
        empty_request = pb.SendMessageRequest(
            message=pb.Message(message_id=str(uuid.uuid4()), role=pb.ROLE_USER, parts=[pb.Part(text="   ")])
        )

        with pytest.raises(InvalidParamsError):
            asyncio.run(runtime.handler.on_message_send(empty_request, _context_for(owner)))

        models = get_sdk_models()
        from db.database import SessionLocal

        session = SessionLocal()
        try:
            count = (
                session.query(models.task)
                .filter(models.task.owner == owner)
                .count()
            )
            assert count == 0
        finally:
            session.close()

    def test_a_different_owner_cannot_see_the_task(self, a2a_committed_world, a2a_runtime_factory):
        world = a2a_committed_world
        runtime = a2a_runtime_factory(_EchoExecutor())
        owner = owner_for(world.app_id, world.agent_public_id, hash_api_key(world.key_1_raw))
        other_owner = owner_for(world.other_app_id, world.other_agent_id, hash_api_key(world.other_key_raw))

        result = asyncio.run(
            runtime.handler.on_message_send(_send_request(), _context_for(owner))
        )

        get_request = pb.GetTaskRequest(id=result.id)
        with pytest.raises(TaskNotFoundError):
            asyncio.run(runtime.handler.on_get_task(get_request, _context_for(other_owner)))

    def test_same_app_and_agent_but_a_different_api_key_cannot_see_the_task(
        self, a2a_committed_world, a2a_runtime_factory
    ):
        """Owner scoping is per (app, agent, api_key_hash) -- even a key of the
        *same* app and agent, but a different key, is a different owner (AD-3)."""
        world = a2a_committed_world
        runtime = a2a_runtime_factory(_EchoExecutor())
        owner = owner_for(world.app_id, world.agent_public_id, hash_api_key(world.key_1_raw))
        other_key_owner = owner_for(world.app_id, world.agent_public_id, hash_api_key(world.key_2_raw))

        result = asyncio.run(runtime.handler.on_message_send(_send_request(), _context_for(owner)))

        get_request = pb.GetTaskRequest(id=result.id)
        with pytest.raises(TaskNotFoundError):
            asyncio.run(runtime.handler.on_get_task(get_request, _context_for(other_key_owner)))

        cancel_request = pb.CancelTaskRequest(id=result.id)
        with pytest.raises(TaskNotFoundError):
            asyncio.run(runtime.handler.on_cancel_task(cancel_request, _context_for(other_key_owner)))

    def test_same_app_and_key_but_a_different_agent_cannot_see_the_task(
        self, a2a_committed_world, a2a_runtime_factory
    ):
        """Owner scoping includes `agent_id` too: the same app and the same key,
        but a different agent, is still a different owner (AD-3)."""
        world = a2a_committed_world
        runtime = a2a_runtime_factory(_EchoExecutor())
        owner = owner_for(world.app_id, world.agent_public_id, hash_api_key(world.key_1_raw))
        other_agent_owner = owner_for(world.app_id, world.agent_api_key_id, hash_api_key(world.key_1_raw))

        result = asyncio.run(runtime.handler.on_message_send(_send_request(), _context_for(owner)))

        get_request = pb.GetTaskRequest(id=result.id)
        with pytest.raises(TaskNotFoundError):
            asyncio.run(runtime.handler.on_get_task(get_request, _context_for(other_agent_owner)))

        cancel_request = pb.CancelTaskRequest(id=result.id)
        with pytest.raises(TaskNotFoundError):
            asyncio.run(runtime.handler.on_cancel_task(cancel_request, _context_for(other_agent_owner)))

    def test_a_malformed_task_id_on_send_raises_task_not_found_and_creates_nothing(
        self, a2a_committed_world, a2a_runtime_factory
    ):
        """Pins the real ordering (module docstring of `context_builders.py`,
        item 6 of the step_012 fix round): the SDK's own store lookup for a
        `message.task_id` that names no existing task raises `TaskNotFoundError`
        in `_setup_active_task`, *before* `A2ARequestContextBuilder.build` (and
        its own taskId shape check) ever runs -- so a malformed `taskId` gets
        the same `TaskNotFoundError`, not `InvalidParamsError`, and nothing is
        created either way."""
        world = a2a_committed_world
        runtime = a2a_runtime_factory(_EchoExecutor())
        owner = owner_for(world.app_id, world.agent_public_id, hash_api_key(world.key_1_raw))
        malformed_task_id = "not a valid id / too many chars indeed"
        request = pb.SendMessageRequest(
            message=pb.Message(
                message_id=str(uuid.uuid4()),
                task_id=malformed_task_id,
                role=pb.ROLE_USER,
                parts=[pb.Part(text="hi")],
            )
        )

        with pytest.raises(TaskNotFoundError):
            asyncio.run(runtime.handler.on_message_send(request, _context_for(owner)))

        models = get_sdk_models()
        from db.database import SessionLocal

        session = SessionLocal()
        try:
            assert session.get(models.task, malformed_task_id) is None
            count = session.query(models.task).filter(models.task.owner == owner).count()
            assert count == 0
        finally:
            session.close()
