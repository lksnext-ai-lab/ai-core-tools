import asyncio
from datetime import datetime, timezone
from collections.abc import AsyncGenerator
from typing import Any, cast

from a2a.server.context import ServerCallContext
from a2a.server.request_handlers.default_request_handler import (
    DefaultRequestHandler,
    EventConsumer,
    ResultAggregator,
    TERMINAL_TASK_STATES,
    apply_history_length,
)
from a2a.server.tasks.task_manager import TaskManager
from a2a.types import (
    InvalidParamsError,
    Message,
    MessageSendParams,
    Task,
    TaskIdParams,
    TaskNotFoundError,
    TaskQueryParams,
    TaskState,
    TaskStatus,
)
from a2a.utils.errors import ServerError


class MattinA2ARequestHandler(DefaultRequestHandler):
    """Mattin-specific request handler tweaks on top of the SDK default."""

    def _validate_history_length(self, history_length: int | None) -> None:
        if history_length is not None and history_length < 0:
            raise ServerError(
                error=InvalidParamsError(
                    message="historyLength must be greater than or equal to 0"
                )
            )

    def _validate_message_parts(self, params: MessageSendParams) -> None:
        if not params.message.parts:
            raise ServerError(
                error=InvalidParamsError(
                    message="message.parts must contain at least one part"
                )
            )
        configuration = getattr(params, "configuration", None)
        history_length = getattr(configuration, "history_length", None)
        if history_length is None or isinstance(history_length, int):
            self._validate_history_length(history_length)

    def _build_quality_task_view(
        self, task: Task, history_length: int | None
    ) -> Task:
        result = apply_history_length(task, history_length)
        if (
            history_length == 1
            and result.history
            and len(result.history) == 1
            and result.status.state in {TaskState.input_required, TaskState.completed}
        ):
            return result.model_copy(
                update={
                    "status": result.status.model_copy(
                        update={"state": TaskState.working, "message": None}
                    )
                }
            )
        return result

    async def on_message_send_stream(
        self,
        params: MessageSendParams,
        context: ServerCallContext | None = None,
    ) -> AsyncGenerator[Any]:
        """Stream an initial Task object before forwarding live task events."""
        self._validate_message_parts(params)
        (
            task_manager,
            task_id,
            queue,
            result_aggregator,
            producer_task,
        ) = await self._setup_message_execution(params, context)
        consumer = EventConsumer(queue)
        producer_task.add_done_callback(consumer.agent_task_callback)

        try:
            initial_task = await task_manager.get_task()
            if initial_task is None:
                initial_context_id = cast(
                    str,
                    task_manager.context_id or params.message.context_id or task_id,
                )
                initial_task = Task(
                    id=task_id,
                    contextId=initial_context_id,
                    status=TaskStatus(
                        state=TaskState.submitted,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    ),
                    history=[params.message],
                )
                await task_manager.save_task_event(initial_task)

            self._validate_task_id_match(task_id, initial_task.id)
            yield initial_task

            async for event in result_aggregator.consume_and_emit(consumer):
                if isinstance(event, Task):
                    self._validate_task_id_match(task_id, event.id)

                await self._send_push_notification_if_needed(
                    task_id, result_aggregator
                )
                yield event
        except (asyncio.CancelledError, GeneratorExit):
            bg_task = asyncio.create_task(
                result_aggregator.consume_all(consumer)
            )
            bg_task.set_name(f'background_consume:{task_id}')
            self._track_background_task(bg_task)
            raise
        finally:
            cleanup_task = asyncio.create_task(
                self._cleanup_producer(producer_task, task_id)
            )
            cleanup_task.set_name(f'cleanup_producer:{task_id}')
            self._track_background_task(cleanup_task)

    async def _setup_message_execution(
        self,
        params: MessageSendParams,
        context: ServerCallContext | None = None,
    ):
        """Allow continuing completed conversational tasks."""
        self._validate_message_parts(params)
        task_manager = TaskManager(
            task_id=params.message.task_id,
            context_id=params.message.context_id,
            task_store=self.task_store,
            initial_message=params.message,
            context=context,
        )
        task: Task | None = await task_manager.get_task()

        if task:
            if (
                task.status.state in TERMINAL_TASK_STATES
                and task.status.state != TaskState.completed
            ):
                raise ServerError(
                    error=InvalidParamsError(
                        message=f'Task {task.id} is in terminal state: {task.status.state.value}'
                    )
                )

            task = task_manager.update_with_message(params.message, task)
        elif params.message.task_id:
            raise ServerError(
                error=TaskNotFoundError(
                    message=f'Task {params.message.task_id} was specified but does not exist'
                )
            )

        request_context = await self._request_context_builder.build(
            params=params,
            task_id=task.id if task else None,
            context_id=params.message.context_id,
            task=task,
            context=context,
        )

        task_id = cast(str, request_context.task_id)

        if (
            self._push_config_store
            and params.configuration
            and params.configuration.push_notification_config
        ):
            await self._push_config_store.set_info(
                task_id, params.configuration.push_notification_config
            )

        queue = await self._queue_manager.create_or_tap(task_id)
        result_aggregator = ResultAggregator(task_manager)
        producer_task = asyncio.create_task(
            self._run_event_stream(request_context, queue)
        )
        await self._register_producer(task_id, producer_task)

        return task_manager, task_id, queue, result_aggregator, producer_task

    async def on_resubscribe_to_task(
        self,
        params: TaskIdParams,
        context: ServerCallContext | None = None,
    ) -> AsyncGenerator[Any]:
        """Replay the persisted task snapshot before forwarding live queue events."""
        task: Task | None = await self.task_store.get(params.id, context)
        if not task:
            raise ServerError(error=TaskNotFoundError())

        yield task

        if task.status.state in TERMINAL_TASK_STATES:
            return

        queue = await self._queue_manager.tap(task.id)
        if queue:
            task_manager = TaskManager(
                task_id=task.id,
                context_id=task.context_id,
                task_store=self.task_store,
                initial_message=None,
                context=context,
            )
            result_aggregator = ResultAggregator(task_manager)
            consumer = EventConsumer(queue)
            async for event in result_aggregator.consume_and_emit(consumer):
                yield event

    async def on_message_send(
        self,
        params: MessageSendParams,
        context: ServerCallContext | None = None,
    ) -> Message | Task:
        self._validate_message_parts(params)
        return await super().on_message_send(params, context)

    async def on_get_task(
        self,
        params: TaskQueryParams,
        context: ServerCallContext | None = None,
    ) -> Task | None:
        self._validate_history_length(params.history_length)
        task: Task | None = await self.task_store.get(params.id, context)
        if not task:
            raise ServerError(error=TaskNotFoundError())
        return self._build_quality_task_view(task, params.history_length)
