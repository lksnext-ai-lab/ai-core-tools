import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from a2a.types import (
    InvalidParamsError,
    Message,
    MessageSendParams,
    Part,
    Role,
    Task,
    TaskIdParams,
    TaskQueryParams,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from a2a.utils.errors import ServerError

from services.a2a_request_handler import MattinA2ARequestHandler


class TestMattinA2ARequestHandler:
    @pytest.mark.asyncio
    async def test_on_message_send_rejects_empty_parts(self):
        handler = MattinA2ARequestHandler(
            agent_executor=MagicMock(),
            task_store=MagicMock(),
        )
        handler._setup_message_execution = AsyncMock()

        params = MessageSendParams(
            message=Message(
                messageId="msg-empty",
                role=Role.user,
                parts=[],
            )
        )

        with pytest.raises(ServerError) as exc_info:
            await handler.on_message_send(params)

        assert isinstance(exc_info.value.error, InvalidParamsError)
        handler._setup_message_execution.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_on_get_task_rejects_negative_history_length(self):
        handler = MattinA2ARequestHandler(
            agent_executor=MagicMock(),
            task_store=MagicMock(),
        )

        with pytest.raises(ServerError) as exc_info:
            await handler.on_get_task(
                TaskQueryParams(id="task-1", historyLength=-1)
            )

        assert isinstance(exc_info.value.error, InvalidParamsError)

    @pytest.mark.asyncio
    async def test_on_message_send_stream_emits_initial_task_before_status_updates(self):
        handler = MattinA2ARequestHandler(
            agent_executor=MagicMock(),
            task_store=MagicMock(),
        )

        params = MagicMock()
        params.message = Message(
            messageId="msg-1",
            contextId="ctx-1",
            role=Role.user,
            parts=[Part(root=TextPart(text="hello"))],
        )

        task_manager = MagicMock()
        task_manager.context_id = "ctx-1"
        task_manager.get_task = AsyncMock(return_value=None)
        task_manager.save_task_event = AsyncMock()

        status_event = TaskStatusUpdateEvent(
            taskId="task-1",
            contextId="ctx-1",
            final=False,
            status=TaskStatus(
                state=TaskState.working,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
        )

        async def consume_and_emit(_consumer):
            yield status_event

        result_aggregator = MagicMock()
        result_aggregator.consume_and_emit = consume_and_emit
        result_aggregator.consume_all = AsyncMock(return_value=None)

        producer_task = MagicMock()
        producer_task.add_done_callback = MagicMock()

        handler._setup_message_execution = AsyncMock(
            return_value=(
                task_manager,
                "task-1",
                MagicMock(),
                result_aggregator,
                producer_task,
            )
        )
        handler._send_push_notification_if_needed = AsyncMock()
        handler._cleanup_producer = AsyncMock()
        handler._track_background_task = MagicMock()

        events = []
        async for event in handler.on_message_send_stream(params):
            events.append(event)

        await asyncio.sleep(0)

        assert len(events) == 2
        assert isinstance(events[0], Task)
        assert events[0].id == "task-1"
        assert events[0].context_id == "ctx-1"
        assert events[0].status.state == TaskState.submitted
        assert events[0].history == [params.message]
        assert events[1] == status_event

        task_manager.save_task_event.assert_awaited_once()
        saved_task = task_manager.save_task_event.await_args.args[0]
        assert isinstance(saved_task, Task)
        assert saved_task.id == "task-1"

    @pytest.mark.asyncio
    async def test_on_resubscribe_to_task_replays_persisted_task_when_queue_missing(self):
        persisted_task = Task(
            id="task-1",
            contextId="ctx-1",
            status=TaskStatus(
                state=TaskState.working,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
        )
        task_store = MagicMock()
        task_store.get = AsyncMock(return_value=persisted_task)

        handler = MattinA2ARequestHandler(
            agent_executor=MagicMock(),
            task_store=task_store,
        )
        handler._queue_manager.tap = AsyncMock(return_value=None)

        events = []
        async for event in handler.on_resubscribe_to_task(TaskIdParams(id="task-1")):
            events.append(event)

        assert events == [persisted_task]
        task_store.get.assert_awaited_once()
        handler._queue_manager.tap.assert_awaited_once_with("task-1")

    @pytest.mark.asyncio
    async def test_on_resubscribe_to_task_emits_persisted_task_before_live_events(self):
        persisted_task = Task(
            id="task-1",
            contextId="ctx-1",
            status=TaskStatus(
                state=TaskState.working,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
        )
        task_store = MagicMock()
        task_store.get = AsyncMock(return_value=persisted_task)

        live_event = TaskStatusUpdateEvent(
            taskId="task-1",
            contextId="ctx-1",
            final=False,
            status=TaskStatus(
                state=TaskState.working,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
        )

        async def consume_and_emit(_consumer):
            yield live_event

        handler = MattinA2ARequestHandler(
            agent_executor=MagicMock(),
            task_store=task_store,
        )
        handler._queue_manager.tap = AsyncMock(return_value=MagicMock())

        result_aggregator = MagicMock()
        result_aggregator.consume_and_emit = consume_and_emit
        task_manager = MagicMock()

        with (
            pytest.MonkeyPatch().context() as mp,
        ):
            mp.setattr(
                "services.a2a_request_handler.TaskManager",
                MagicMock(return_value=task_manager),
            )
            mp.setattr(
                "services.a2a_request_handler.ResultAggregator",
                MagicMock(return_value=result_aggregator),
            )
            events = []
            async for event in handler.on_resubscribe_to_task(TaskIdParams(id="task-1")):
                events.append(event)

        assert events == [persisted_task, live_event]
        task_store.get.assert_awaited_once()
        handler._queue_manager.tap.assert_awaited_once_with("task-1")

    @pytest.mark.asyncio
    async def test_on_resubscribe_to_task_returns_after_terminal_snapshot(self):
        persisted_task = Task(
            id="task-1",
            contextId="ctx-1",
            status=TaskStatus(
                state=TaskState.completed,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
        )
        task_store = MagicMock()
        task_store.get = AsyncMock(return_value=persisted_task)

        handler = MattinA2ARequestHandler(
            agent_executor=MagicMock(),
            task_store=task_store,
        )
        handler._queue_manager.tap = AsyncMock()

        events = []
        async for event in handler.on_resubscribe_to_task(TaskIdParams(id="task-1")):
            events.append(event)

        assert events == [persisted_task]
        handler._queue_manager.tap.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_on_get_task_returns_non_terminal_view_for_new_single_message_task(self):
        persisted_task = Task(
            id="task-1",
            contextId="ctx-1",
            status=TaskStatus(
                state=TaskState.input_required,
                timestamp=datetime.now(timezone.utc).isoformat(),
                message=Message(
                    messageId="agent-msg-1",
                    role=Role.agent,
                    parts=[Part(root=TextPart(text="done"))],
                ),
            ),
            history=[
                Message(
                    messageId="user-msg-1",
                    role=Role.user,
                    parts=[Part(root=TextPart(text="hello"))],
                )
            ],
        )
        task_store = MagicMock()
        task_store.get = AsyncMock(return_value=persisted_task)

        handler = MattinA2ARequestHandler(
            agent_executor=MagicMock(),
            task_store=task_store,
        )

        result = await handler.on_get_task(
            TaskQueryParams(id="task-1", historyLength=1)
        )

        assert result.status.state == TaskState.working
        assert result.status.message is None
        assert result.history == persisted_task.history
