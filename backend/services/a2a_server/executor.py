"""The executor bridge: `MattinAgentExecutor` (step_016, AD-8).

This is the one place that drives an A2A turn end to end: it is the
`a2a.server.agent_execution.AgentExecutor` the process-wide runtime
(`services/a2a_server/runtime.py`, step_012) is built with, and the SDK calls
its `execute`/`cancel` exactly once per request (never concurrently for the
same task -- the SDK's own contract, see `a2a/server/agent_execution/
agent_executor.py`).

Per-turn flow (AD-8), each step reusing an already-committed building block:

1. If this is a brand-new task (`context.current_task is None`), enqueue the
   initial ``Task`` (``SUBMITTED``, ``history=[context.message]``) *before*
   anything else. The SDK's own ``on_message_send``/``on_message_send_stream``
   only return early for ``return_immediately`` on a ``Task``-typed event, not
   a status update -- without this explicit enqueue, a ``return_immediately``
   caller would block until the turn finishes, defeating the task-first
   semantic FR-12 requires (AC-21).
2. ``TaskUpdater.start_work()`` -- the single ``WORKING`` status AC-15's
   streaming-order assertion expects before any artifact update.
3. Open **this turn's own** ``SessionLocal()`` (FR-16/NFR-4: never the
   request session; there is none here, this bridge never runs inside a
   request/response cycle).
4. ``context_binding_service.bind_context`` (step_013) resolves the SDK
   ``contextId`` to exactly one Conversation.
5. ``input_service.build_turn_inputs`` (step_014) turns the inbound
   ``Message`` into chat text + file references.
6. Drive ``AgentStreamingService.stream_agent_events`` (AD-5's canonical
   streaming seam) under ``contextlib.aclosing`` (RB-7) and a hard
   ``asyncio.timeout(A2A_TURN_MAX_SECONDS)`` wall-clock cap (fix round 1,
   item 2 / RB-2 bridge side), translating each typed ``AgentStreamEvent``
   through ``output_mapper.ResponseArtifactMapper`` (step_015) into
   ``TaskUpdater`` calls. A keepalive/coalesce ticker inside ``_drain`` is
   based on the time since this bridge's own *last write*, not on event
   arrival (fix round 1, item 3) -- a run of events this bridge ignores by
   design (e.g. ``thinking`` with ``A2A_STATUS_UPDATES=false``) must not
   starve the keepalive and silently defeat AD-6's remote-cancel bound.
7. End in exactly one terminal state -- ``complete()``, ``failed(...)``, a
   timeout (``"Agent execution timed out."``), or a re-raised
   ``CancelledError`` that lets the SDK itself record ``CANCELED`` (AC-34).
   Never ``input_required`` (AC-16). Never parse SSE (AC-15) -- this module
   and ``output_mapper.py`` never import ``format_sse_event`` or contain a
   ``"data: "`` literal (see the sibling test module's source grep).

Error handling (RB-7, carried from the step_001/step_008 reviews): *every*
exception this bridge raises itself is caught, logged server-side with
``exc_info``, and turned into a fixed, generic failed-task message -- the
SDK's ``JsonRpcDispatcher`` otherwise echoes ``str(e))`` of an unhandled
exception straight to the caller (``jsonrpc_dispatcher.py:350,595``).
Sanitizing an *agent-turn* error (as opposed to a bug in this bridge) is
already ``output_mapper.sanitize_error``'s job, keyed on
``extra["error_kind"]`` -- this module never re-derives that mapping.

In-flight tracking (RB-14): every turn is registered in the process-wide
runtime's worker-local ``in_flight`` set (``A2ARuntime.track``/``untrack``,
step_012) for the whole lifetime of ``execute()``, so ``close_runtime`` can
write a FAILED status for it on a clean shutdown (RB-1, ``runtime.py``).

Cancellation (AD-6/AC-34): the SDK cancels the asyncio Task running
``execute()`` and calls ``cancel()`` in parallel. Cancelling *this* bridge's
own task is not, by itself, enough to stop the underlying LLM stream: the
`AgentStreamEvent` generator's ``__anext__()`` is awaited through a
dedicated, separately created ``asyncio.Task`` (so it can be raced against
the keepalive timeout via ``asyncio.wait`` without losing it across
timeouts) -- cancelling *that* task is what actually delivers
``CancelledError`` into ``stream_agent_events``'s current await point and
stops the astream loop. ``_drain``'s ``finally`` does exactly that for every
exit path (normal, cancelled, or erroring), which is also step_002's
follow-up fix for "GetTask status alone can't prove the producer stopped".
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import List, Optional

from a2a.helpers import new_task
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.events.event_queue import QueueShutDown
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types.a2a_pb2 import Part, TaskState

from db.database import SessionLocal
from services.a2a_server.context_binding_service import (
    A2AContextBindingError,
    A2AInvalidContextIdError,
    bind_context,
)
from services.a2a_server.identity import A2ACallScope, owner_for
from services.a2a_server.input_service import A2AInputError, build_turn_inputs
from services.a2a_server.input_service import cleanup as cleanup_turn_inputs
from services.a2a_server.output_mapper import (
    AppendText,
    DefaultFileResolver,
    Fail,
    Final,
    MapperAction,
    ResponseArtifactMapper,
    StatusMessage,
)
from services.a2a_server.runtime import get_runtime
from services.agent_streaming_service import AgentStreamingService
from services.file_management_service import FileManagementService
from services.public_auth_service import create_api_key_user_context
from utils.a2a_config import get_a2a_config
from utils.logger import get_logger

logger = get_logger(__name__)

# AD-5/output_mapper: the one stable identity for the streamed text artifact.
# Mirrored here (not imported) because output_mapper deliberately has no
# access to the SDK's TaskUpdater/artifact concepts -- this bridge is the only
# place that owns the id<->artifact-kind mapping for `Final.parts` (see its
# docstring: "this mapper does not know about artifact ids").
_RESPONSE_ARTIFACT_ID = "response"
_STRUCTURED_ARTIFACT_ID = "structured"
_FILES_ARTIFACT_ID = "files"

_GENERIC_FAILURE_TEXT = "Agent execution failed."

# Fix round 2, item 1: total wall-clock budget `_await_pending_to_completion`
# will wait for the streamed generator's own teardown before giving up and
# abandoning it (logging an ERROR instead of hanging this turn's teardown
# forever). Deliberately generous -- this is the *last* line of defense
# against a hung `finally` block somewhere downstream, not a normal-path
# timing budget (that is `A2A_TURN_MAX_SECONDS`/`A2A_KEEPALIVE_SECONDS`).
_TEARDOWN_BUDGET_SECONDS = 10.0


class _TurnState:
    """Per-turn mutable state threaded through `_drain`/`_apply_action`/`_apply_final`.

    One instance is created per turn (`execute()`), never shared across
    turns or reused on the executor instance itself (which is a process-wide
    singleton shared by every concurrent turn).

    ``response_created``: the SDK's `TaskManager.append_artifact_to_task`
    raises `InvalidAgentResponseError` if `append=True` is used before any
    chunk of that artifact id has been sent (`a2a/server/tasks/
    task_manager.py`'s `append_artifact_to_task`: "append=True for
    nonexistent artifact_id... The artifact must be created (append=False)
    before appending parts to it."). The very first chunk this bridge sends
    for `"response"` -- whether it is a coalesced token flush or, for a
    structured-only turn with no tokens at all, the `Final` text part itself
    -- must therefore be sent with `append=False`; every later chunk uses
    `append=True`.

    ``last_save``: the monotonic time of the most recent `TaskUpdater` write
    (`add_artifact`/`update_status`/`complete`/`failed`) -- deliberately
    *not* "the last time an event arrived from the stream" (fix round 1,
    item 3). A burst of events this bridge ignores by design (e.g.
    `thinking`/`tool_start` with the default `A2A_STATUS_UPDATES=false`)
    would otherwise keep `_drain`'s event-arrival branch busy indefinitely
    without this bridge ever actually writing anything, starving the
    keepalive and silently defeating AD-6's remote-cancel-latency bound
    (the owning worker only re-checks the task's version on its *own* next
    save).
    """

    def __init__(self) -> None:
        self.response_created = False
        self.last_save = time.monotonic()
        # Set as soon as `_apply_action` starts applying a terminal
        # (`Final`/`Fail`) action -- i.e. right before the `TaskUpdater` call
        # that may flip the SDK's own `_terminal_state_reached` flag can
        # itself still raise partway through (e.g. `QueueShutDown` while
        # enqueueing, or an `asyncio.timeout` cancellation landing in that
        # exact await). `execute()`'s outer handlers check this (fix round 2,
        # item 4) to avoid a second `updater.failed(...)` call that would
        # otherwise raise `RuntimeError("... already in a terminal state")`
        # and mask the real error.
        self.terminal_write_started = False

    def next_append_flag(self) -> bool:
        """Returns the `append` value for the next `"response"` chunk, and
        marks the artifact as created for every subsequent call."""
        append = self.response_created
        self.response_created = True
        return append

    def note_save(self) -> None:
        """Call after every successful `TaskUpdater` write."""
        self.last_save = time.monotonic()


class MattinAgentExecutor(AgentExecutor):
    """Bridges one A2A turn to `AgentStreamingService` (AD-8). Stateless across turns."""

    # ------------------------------------------------------------------
    # AgentExecutor interface
    # ------------------------------------------------------------------

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)

        outcome = "failed"
        db = None
        inputs = None
        fms = FileManagementService()
        scope: Optional[A2ACallScope] = None
        owner: Optional[str] = None
        runtime = None
        turn_state: Optional[_TurnState] = None

        try:
            # Fix round 1, item 8: scope extraction, `owner_for`, config and
            # `runtime.track` all moved inside this `try` (previously they ran
            # before it) so that *any* failure among them -- including a
            # defensive `scope is None` bailout -- still reaches the single
            # `finally` below that pairs `track`/`untrack` and sets the
            # outcome. Nothing here can observably fail before `track` runs,
            # but keeping them in the same `try` means a future change to
            # this preamble can never reopen an unpaired-untrack bug.
            cfg = get_a2a_config()
            scope = context.call_context.state["a2a"] if context.call_context.state else None
            if scope is None:
                # Defense in depth only: `A2AServerCallContextBuilder.build` (step_012)
                # always sets `state["a2a"]` or raises before dispatch ever reaches
                # here, so this should be unreachable in production.
                logger.error("a2a.executor.missing_scope task_id=%s", context.task_id)
                await self._fail_generic(updater)
                outcome = "failed"
                return

            owner = owner_for(scope.app_id, scope.agent_id, scope.api_key_hash)
            runtime = get_runtime()
            if runtime is not None:
                runtime.track(owner=owner, task_id=context.task_id)

            if context.current_task is None:
                history = [context.message] if context.message is not None else []
                initial_task = new_task(
                    context.task_id, context.context_id, TaskState.TASK_STATE_SUBMITTED, history=history
                )
                await event_queue.enqueue_event(initial_task)

            await updater.start_work()

            db = SessionLocal()
            user_context = create_api_key_user_context(scope.app_id, scope.api_key.get_secret_value())
            # FR-20: the public-API-style context plus the override metrics/
            # conversation-source resolution reads to attribute this turn to A2A.
            user_context["caller_type_override"] = "A2A"

            try:
                binding = bind_context(
                    db,
                    app_id=scope.app_id,
                    agent_id=scope.agent_id,
                    api_key_raw=scope.api_key.get_secret_value(),
                    context_id=context.context_id,
                    user_context=user_context,
                )
            except (A2AInvalidContextIdError, A2AContextBindingError) as exc:
                # Both exceptions already carry a generic, caller-safe message
                # (see their docstrings); details were logged at the raise site.
                logger.warning(
                    "a2a.executor.bind_context_failed task_id=%s error=%s",
                    context.task_id, type(exc).__name__,
                )
                await updater.failed(updater.new_agent_message([Part(text=_GENERIC_FAILURE_TEXT)]))
                outcome = "failed"
                return

            # AC-14: never None for an A2A turn.
            scope.request_log.conversation_id = binding.conversation_id

            try:
                inputs = await build_turn_inputs(
                    context.message,
                    snapshot=scope.snapshot,
                    user_context=user_context,
                    conversation_id=binding.conversation_id,
                    fms=fms,
                )
            except A2AInputError as exc:
                # A2AInputError's message is already client-safe (it names the
                # part, never content/URLs/raw exception text) -- see its
                # docstring. Logged at INFO, without exc_info (it is routine
                # client input, not a bug).
                logger.info(
                    "a2a.executor.input_error task_id=%s part_index=%s reason=%s",
                    context.task_id, exc.part_index, exc.reason,
                )
                await updater.failed(updater.new_agent_message([Part(text=str(exc))]))
                outcome = "input_error"
                return

            mapper = ResponseArtifactMapper(
                coalesce_ms=cfg.stream_coalesce_ms,
                status_updates=cfg.status_updates,
                file_resolver=DefaultFileResolver(
                    scope.agent_id, user_context, binding.conversation_id, fms=fms
                ),
                base_url=scope.base_url,
                identity=f"a2a-{scope.api_key_id}",
                file_url_ttl_seconds=cfg.file_url_ttl_seconds,
                inline_file_max_bytes=cfg.inline_file_max_bytes,
            )

            streaming_service = AgentStreamingService(db)
            # Fix round 2, item 3: keep a handle on the timeout context
            # manager itself. `asyncio.timeout.__aexit__` converts *any*
            # `CancelledError` propagating out of its block into a bare
            # `TimeoutError` when its own deadline fired -- but a
            # `TimeoutError` can also legitimately originate from somewhere
            # else inside the block (it is a plain builtin exception, not
            # exclusive to `asyncio.timeout`). Only `timeout_cm.expired()`
            # tells the two apart; a `TimeoutError` that is *not* ours must
            # fall through to the generic failure path below, not be
            # mislabeled as a turn timeout.
            timeout_cm = asyncio.timeout(cfg.turn_max_seconds)
            try:
                # Fix round 1, item 2 (RB-2 bridge side): a hard wall-clock cap
                # on the whole streaming section, independent of how (or
                # whether) the keepalive/coalesce ticker inside `_drain` would
                # otherwise keep this turn alive forever against a stuck
                # agent chain. `asyncio.timeout` cancels the `_drain` await
                # below exactly like an external cancellation would (same
                # `CancelledError`-based mechanism `_drain`'s own `finally`
                # already handles), so the streamed generator is still torn
                # down correctly -- this is not a second, parallel cancel path.
                async with timeout_cm, contextlib.aclosing(
                    streaming_service.stream_agent_events(
                        agent_id=scope.agent_id,
                        message=inputs.text,
                        file_references=inputs.file_refs,
                        user_context=user_context,
                        conversation_id=binding.conversation_id,
                        db=db,
                    )
                ) as events:
                    turn_state = _TurnState()
                    terminal = await self._drain(
                        events, updater, mapper, cfg.keepalive_seconds,
                        cfg.stream_coalesce_ms / 1000.0, turn_state,
                    )
            except TimeoutError:
                if not timeout_cm.expired():
                    # Not our deadline -- some other builtin TimeoutError
                    # from inside the block. Let the generic exception
                    # handler below sanitize and report it like any other
                    # unexpected error.
                    raise
                logger.warning(
                    "a2a.executor.turn_timeout task_id=%s turn_max_seconds=%s",
                    context.task_id, cfg.turn_max_seconds,
                )
                # Fix round 2, item 4: don't attempt a second terminal write
                # if `_apply_action` already started one (e.g. the timeout's
                # own cancellation landed inside `updater.complete()`/
                # `failed()` itself, after it already flipped the SDK's
                # `_terminal_state_reached` flag) -- that would just raise
                # `RuntimeError` and mask the real outcome.
                if turn_state is None or not turn_state.terminal_write_started:
                    await updater.failed(
                        updater.new_agent_message([Part(text="Agent execution timed out.")])
                    )
                outcome = "timeout"
                return

            if terminal is None:
                # AgentStreamingService's own contract guarantees exactly one
                # terminal AgentStreamEvent per turn (done/error) outside of
                # cancellation -- reaching this means that contract broke, not
                # a normal outcome. Fail loudly rather than leave the task
                # stuck non-terminal.
                logger.error("a2a.executor.stream_ended_without_terminal task_id=%s", context.task_id)
                await updater.failed(updater.new_agent_message([Part(text=_GENERIC_FAILURE_TEXT)]))
                outcome = "failed"
            else:
                outcome = terminal

        except asyncio.CancelledError:
            outcome = "canceled"
            raise
        except QueueShutDown:
            # The SDK closed this task's event queue (producer.cancel() already
            # ran, or the queue is tearing down) -- treat exactly like a
            # cancellation: stop immediately, never emit afterwards, and let
            # the SDK's own CANCELED write stand.
            outcome = "canceled"
            raise asyncio.CancelledError() from None
        except Exception:
            logger.exception("a2a.executor.unexpected_error task_id=%s", context.task_id)
            # Fix round 2, item 4: same duplicate-terminal-write guard as the
            # timeout branch above -- `_fail_generic` already swallows the
            # resulting `RuntimeError` on its own, but skipping the attempt
            # entirely avoids the noisy, misleading log line altogether.
            if turn_state is None or not turn_state.terminal_write_started:
                await self._fail_generic(updater)
            outcome = "failed"
        finally:
            # Fix round 1, item 5: outcome + untrack first (cheap, in-memory,
            # must never be skipped), then `db.close()` and the file cleanup,
            # each independently try/except-logged so one failing cleanup step
            # never prevents the next from running; the file cleanup is
            # `asyncio.shield`ed so a cancellation landing *during* this
            # `finally` (e.g. a second cancel request) cannot abandon it
            # half-done and leak an ephemeral upload.
            if scope is not None and scope.request_log is not None:
                scope.request_log.outcome = outcome
            if runtime is not None and owner is not None:
                try:
                    runtime.untrack(owner=owner, task_id=context.task_id)
                except Exception:
                    logger.exception("a2a.executor.untrack_error task_id=%s", context.task_id)
            if db is not None:
                try:
                    db.close()
                except Exception:
                    logger.exception("a2a.executor.db_close_error task_id=%s", context.task_id)
            if inputs is not None:
                try:
                    await asyncio.shield(cleanup_turn_inputs(fms, inputs.file_refs))
                except Exception:
                    logger.exception("a2a.executor.input_cleanup_error task_id=%s", context.task_id)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Best-effort cancel (AD-8): the SDK cancels the producer task regardless.

        Only ``QueueShutDown`` is swallowed here -- the queue may already be
        closing by the time this runs. Any other exception is left to
        propagate: ``ActiveTask.cancel`` (the SDK caller) already catches a
        generic ``Exception`` from this method and marks the task FAILED
        itself, so there is nothing this bridge needs to add.
        """
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        try:
            await updater.cancel()
        except QueueShutDown:
            pass

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _drain(
        self,
        events,
        updater: TaskUpdater,
        mapper: ResponseArtifactMapper,
        keepalive_seconds: float,
        coalesce_seconds: float,
        turn_state: "_TurnState",
    ) -> Optional[str]:
        """Consumes `events`, applying mapper actions through `updater`.

        Returns ``"completed"``/``"failed"`` once a terminal `MapperAction`
        (`Final`/`Fail`) was applied, or `None` if the generator ended on its
        own (`StopAsyncIteration`) without ever producing one.

        The next event is always awaited through a dedicated `asyncio.Task`
        (`pending`) so it survives being raced against the keepalive timeout
        via `asyncio.wait` across multiple iterations without being
        abandoned. The `finally` waits for it to actually finish on every
        exit path (including this coroutine's own cancellation, possibly
        more than once -- see `_await_pending_to_completion`) -- that is what
        actually stops `stream_agent_events`' astream loop, and it is also
        what makes it safe for `execute()`'s `contextlib.aclosing` to call
        `events.aclose()` right after this returns/raises (fix round 1, item
        6): the SDK/CPython's async-generator machinery forbids closing a
        generator that is still suspended inside a *different* in-flight
        `asend`/`athrow`/`aclose` call on it.

        Keepalive/coalesce ticking (fix round 1, item 3) is based on
        `turn_state.last_save` -- the last actual `TaskUpdater` write -- not
        on whether an event happened to arrive within the poll window. Every
        iteration, regardless of whether `pending` was done, checks
        `mapper.flush_due` and whether `keepalive_seconds` have elapsed since
        `last_save`; the poll timeout itself is capped at `min(keepalive_seconds,
        coalesce_seconds)` (floored to avoid a zero/negative timeout) so
        neither check is ever starved by a long run of ignored events.
        """
        poll_interval = keepalive_seconds if coalesce_seconds <= 0 else min(keepalive_seconds, coalesce_seconds)
        poll_interval = max(poll_interval, 0.01)

        pending = asyncio.ensure_future(events.__anext__())
        try:
            while True:
                now = time.monotonic()
                remaining_to_keepalive = max(0.0, (turn_state.last_save + keepalive_seconds) - now)
                wait_timeout = min(poll_interval, remaining_to_keepalive)
                done, _ = await asyncio.wait({pending}, timeout=wait_timeout)

                now = time.monotonic()
                flush = mapper.flush_due(now)
                if flush is not None:
                    await updater.add_artifact(
                        [Part(text=flush.text)],
                        artifact_id=_RESPONSE_ARTIFACT_ID,
                        name=_RESPONSE_ARTIFACT_ID,
                        append=turn_state.next_append_flag(),
                    )
                    turn_state.note_save()

                if now - turn_state.last_save >= keepalive_seconds:
                    # AD-6 keepalive: no message, just refreshes `last_updated`
                    # and bounds remote-cancel latency.
                    await updater.update_status(TaskState.TASK_STATE_WORKING)
                    turn_state.note_save()

                if pending in done:
                    try:
                        event = pending.result()
                    except StopAsyncIteration:
                        return None
                    now = time.monotonic()
                    for action in await mapper.apply(event, now):
                        terminal = await self._apply_action(updater, action, turn_state)
                        if terminal is not None:
                            return terminal
                    pending = asyncio.ensure_future(events.__anext__())
        finally:
            if not pending.done():
                pending.cancel()
            await self._await_pending_to_completion(pending, task_id=updater.task_id)

    async def _await_pending_to_completion(
        self, pending: "asyncio.Task", *, task_id: str, deadline: Optional[float] = None
    ) -> None:
        """Waits for `pending` to actually finish, no matter how many times
        this wait itself is cancelled in the meantime (fix round 1, item 6).

        `asyncio.wait` never raises `pending`'s own outcome (including its own
        `CancelledError`, from the `cancel()` call in `_drain`'s `finally`), so
        a `CancelledError` here is always a cancellation of *this* wait. It
        never abandons `pending` mid-flight -- which is what would let
        `execute()`'s `contextlib.aclosing` call `aclose()` on a generator
        that is still actually running a frame: the wait carries on (through
        further cancellations too, by recursing) and the cancellation is
        re-raised once `pending` is done.

        Bounded by `_TEARDOWN_BUDGET_SECONDS` (fix round 2, item 1): if the
        generator's own cancellation handling itself hangs (a bug in
        whatever `stream_agent_events` is actually running, e.g. a `finally`
        block awaiting something that never completes), this gives up
        waiting after that total budget, logs an ERROR (`task_id` only --
        never message/exception text), and returns, leaving `pending`
        abandoned rather than blocking this turn's teardown forever.
        """
        if deadline is None:
            deadline = time.monotonic() + _TEARDOWN_BUDGET_SECONDS
        while not pending.done():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                logger.error("a2a.executor.drain_teardown_timeout task_id=%s", task_id)
                return
            try:
                await asyncio.wait({pending}, timeout=remaining)
            except asyncio.CancelledError:
                await self._await_pending_to_completion(pending, task_id=task_id, deadline=deadline)
                raise
        if pending.cancelled():
            return
        exc = pending.exception()
        if exc is not None and not isinstance(exc, StopAsyncIteration):
            logger.error("a2a.executor.drain_cleanup_error task_id=%s", task_id, exc_info=exc)

    async def _apply_action(
        self, updater: TaskUpdater, action: MapperAction, turn_state: "_TurnState"
    ) -> Optional[str]:
        """Applies one `MapperAction` through `updater`; returns the terminal outcome, if any."""
        if isinstance(action, AppendText):
            await updater.add_artifact(
                [Part(text=action.text)],
                artifact_id=_RESPONSE_ARTIFACT_ID,
                name=_RESPONSE_ARTIFACT_ID,
                append=turn_state.next_append_flag(),
            )
            turn_state.note_save()
            return None

        if isinstance(action, StatusMessage):
            # `ResponseArtifactMapper.apply` only ever produces a `StatusMessage`
            # when `status_updates` is enabled -- no need to re-check the flag here.
            await updater.update_status(
                TaskState.TASK_STATE_WORKING,
                message=updater.new_agent_message([Part(text=action.text)]),
            )
            turn_state.note_save()
            return None

        if isinstance(action, Final):
            await self._apply_final(updater, action.parts, turn_state)
            turn_state.terminal_write_started = True
            await updater.complete()
            turn_state.note_save()
            return "completed"

        if isinstance(action, Fail):
            turn_state.terminal_write_started = True
            await updater.failed(updater.new_agent_message([Part(text=action.message)]))
            turn_state.note_save()
            return "failed"

        logger.warning("a2a.executor.unknown_mapper_action type=%s", type(action).__name__)
        return None

    async def _apply_final(
        self, updater: TaskUpdater, parts: List[Part], turn_state: "_TurnState"
    ) -> None:
        """Groups `Final.parts` into the `response`/`structured`/`files` artifacts.

        `parts[0]` is always the remaining response text (``output_mapper``'s
        contract: "always present, even when empty") -- sent as the
        `"response"` artifact's last, ``append=True, last_chunk=True`` chunk.
        Everything after it is grouped by which `Part` oneof field is set:
        a `data` part becomes the `"structured"` artifact (AC-22); a `raw`/
        `url` part becomes one entry in the `"files"` artifact (AC-23).
        """
        text_part = parts[0] if parts else Part(text="")
        structured_parts: List[Part] = []
        file_parts: List[Part] = []
        for part in parts[1:]:
            which = part.WhichOneof("content")
            if which == "data":
                structured_parts.append(part)
            elif which in ("raw", "url"):
                file_parts.append(part)

        await updater.add_artifact(
            [text_part],
            artifact_id=_RESPONSE_ARTIFACT_ID,
            name=_RESPONSE_ARTIFACT_ID,
            append=turn_state.next_append_flag(),
            last_chunk=True,
        )
        if structured_parts:
            await updater.add_artifact(
                structured_parts, artifact_id=_STRUCTURED_ARTIFACT_ID, name=_STRUCTURED_ARTIFACT_ID
            )
        if file_parts:
            await updater.add_artifact(file_parts, artifact_id=_FILES_ARTIFACT_ID, name=_FILES_ARTIFACT_ID)

    async def _fail_generic(self, updater: TaskUpdater) -> None:
        """Best-effort generic failure (RB-7): never raises, never reveals internals."""
        try:
            await updater.failed(updater.new_agent_message([Part(text=_GENERIC_FAILURE_TEXT)]))
        except Exception:
            logger.exception("a2a.executor.fail_generic_error")


__all__ = ["MattinAgentExecutor"]
