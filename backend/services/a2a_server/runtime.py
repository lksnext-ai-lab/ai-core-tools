"""The single process-wide A2A runtime: store, stream, handler, dispatcher (AD-1, AD-2).

`build_a2a_runtime` is the only place that assembles a `DefaultRequestHandlerV2`
(AD-1: exactly one handler per process, so the in-memory `ActiveTaskRegistry`
it owns is shared by every request a worker serves -- local cancel and the
fast subscribe path both depend on that). It is called once, from the
lifespan (step_017), and the resulting `A2ARuntime` is published through
`set_runtime`/`get_runtime` for the router to read per request.

`agent_card`/`extended_agent_card` here are **not** the real per-agent cards
(those live in `services/a2a_server/card_service.py`, step_011, and are only
ever served through `GetExtendedAgentCard`/`.well-known` discovery, never
through this handler's own `agent_card`). `DefaultRequestHandlerV2` only ever
reads `agent_card` for its three capability gates (`capabilities.streaming`,
`capabilities.push_notifications`, `capabilities.extended_agent_card`), so a
single generic card with those three flags set is all AD-1 needs; per-agent
identity is resolved later, by `_extended_modifier`, from
`ctx.state["a2a"].snapshot`.

**RB-1 (reliability, carried from step_002's review).** `A2ARuntime.in_flight`
is a worker-local `set[(owner, task_id)]` that the step_016 executor bridge
is expected to populate via `track`/`untrack` around each turn it drives.
`close_runtime` uses it on shutdown: before draining the handler, it writes a
FAILED status (message "worker shutdown") through `store.save` for every
task still marked in-flight, under an overall timeout -- so a worker that is
killed mid-turn never leaves a task stuck WORKING/SUBMITTED forever (the
stale-task sweep, step_018, would eventually catch it, but RB-1 asks for an
immediate, graceful mark on a clean shutdown).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional, Set, Tuple

from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.cluster.database_event_stream import DatabaseTaskEventStream
from a2a.server.cluster.task_store import VersionedTaskStore
from a2a.server.context import ServerCallContext
from a2a.server.request_handlers.default_request_handler_v2 import (
    DefaultRequestHandlerV2,
)
from a2a.server.routes.jsonrpc_dispatcher import JsonRpcDispatcher
from a2a.types.a2a_pb2 import AgentCapabilities, AgentCard
from a2a.utils.errors import ExtendedAgentCardNotConfiguredError
from sqlalchemy.ext.asyncio import AsyncEngine

from services.a2a_server.card_service import build_extended_card
from services.a2a_server.context_builders import (
    A2AServerCallContextBuilder,
    A2ARequestContextBuilder,
)
from services.a2a_server.identity import resolve_a2a_owner
from services.a2a_server.storage import build_bound_storage
from services.a2a_server.task_states import fail_task_cas
from utils.a2a_config import get_a2a_config
from utils.logger import get_logger

logger = get_logger(__name__)

_SHUTDOWN_MESSAGE_TEXT = "worker shutdown"

# Default overall timeout for close_runtime(): bounds both the "fail every
# in-flight task" phase and the handler.aclose() drain.
_DEFAULT_CLOSE_TIMEOUT_S = 10.0


@dataclass(frozen=True)
class A2ARuntime:
    """The objects every A2A request needs; built once per process (AD-1).

    `in_flight` (RB-1) is a plain `set` -- mutated in place via `track`/
    `untrack` below, never reassigned, so it stays consistent with this
    dataclass being frozen (the four SDK objects above are never swapped out
    either; only this registry's *contents* change over the runtime's life).
    """

    store: VersionedTaskStore
    event_stream: DatabaseTaskEventStream
    handler: DefaultRequestHandlerV2
    dispatcher: JsonRpcDispatcher
    in_flight: Set[Tuple[str, str]] = field(default_factory=set)

    def track(self, *, owner: str, task_id: str) -> None:
        """Marks `(owner, task_id)` as in-flight (step_016 bridge, at turn start)."""
        self.in_flight.add((owner, task_id))

    def untrack(self, *, owner: str, task_id: str) -> None:
        """Clears `(owner, task_id)` (step_016 bridge, at turn end -- any outcome)."""
        self.in_flight.discard((owner, task_id))


def build_capability_card() -> AgentCard:
    """AD-1's generic card: only the three capability flags the handler gates on matter."""
    return AgentCard(
        name="Mattin AI A2A handler",
        capabilities=AgentCapabilities(
            streaming=True, push_notifications=False, extended_agent_card=True
        ),
    )


def build_placeholder_extended_card() -> AgentCard:
    """AD-1's placeholder extended card.

    `DefaultRequestHandlerV2` raises `ExtendedAgentCardNotConfiguredError` if
    `extended_agent_card` is `None` at construction time, even though every
    real request replaces it via `_extended_modifier`. This placeholder is
    never served: `_extended_modifier` runs on every `GetExtendedAgentCard`
    call that reaches the SDK (it requires `capabilities.extended_agent_card`,
    which both this and the capability card set to `True`).
    """
    return AgentCard(
        name="Mattin AI A2A handler (placeholder, never served)",
        capabilities=AgentCapabilities(
            streaming=True, push_notifications=False, extended_agent_card=True
        ),
    )


async def _extended_modifier(card: AgentCard, ctx: ServerCallContext) -> AgentCard:  # NOSONAR - the SDK awaits extended_card_modifier
    """Builds the real, per-agent extended card (AD-1) from `ctx.state["a2a"].snapshot`.

    No DB access here -- the snapshot was already resolved by the router
    before dispatch (AD-4). `services.a2a_server.card_service` (step_011) is a
    top-level import in this module (RB-13; step_011 has landed), not a
    lazy/call-time one.
    """
    scope = ctx.state.get("a2a") if ctx.state else None
    if scope is None:
        raise ExtendedAgentCardNotConfiguredError(
            "no A2A call scope on this context; the router must set request.state.a2a_scope "
            "before dispatch (AD-4)"
        )
    return build_extended_card(scope.snapshot, scope.base_url)


def configure_sdk_logging() -> None:
    """Pins the `a2a` logger to INFO unless `A2A_SDK_DEBUG=true` (AD-4, NFR-5).

    The dispatcher logs the whole request body at DEBUG, which would leak
    message text/file contents into logs if left at the library default.
    """
    cfg = get_a2a_config()
    logging.getLogger("a2a").setLevel(logging.DEBUG if cfg.sdk_debug else logging.INFO)


def build_a2a_runtime(executor: AgentExecutor, *, engine: Optional[AsyncEngine] = None) -> A2ARuntime:
    """Builds the one-per-process `A2ARuntime` (AD-1).

    `engine` defaults to the shared `db.database.async_engine` (via
    `storage.build_bound_storage`) -- never a second engine/pool (NFR-4).
    Tests that want an isolated engine (e.g. pointed at the test DB) pass one
    explicitly.
    """
    cfg = get_a2a_config()
    store, event_stream = build_bound_storage(
        owner_resolver=resolve_a2a_owner, engine=engine, poll_interval_s=cfg.event_poll_seconds
    )
    handler = DefaultRequestHandlerV2(
        agent_executor=executor,
        task_store=store,
        agent_card=build_capability_card(),
        extended_agent_card=build_placeholder_extended_card(),
        extended_card_modifier=_extended_modifier,
        request_context_builder=A2ARequestContextBuilder(),
        event_stream=event_stream,
    )
    dispatcher = JsonRpcDispatcher(
        handler,
        context_builder=A2AServerCallContextBuilder(),
        enable_v0_3_compat=cfg.enable_v0_3_compat,
    )
    logger.info("a2a.runtime.built enable_v0_3_compat=%s", cfg.enable_v0_3_compat)
    return A2ARuntime(store=store, event_stream=event_stream, handler=handler, dispatcher=dispatcher)


_runtime: Optional[A2ARuntime] = None


def set_runtime(rt: Optional[A2ARuntime]) -> None:
    """Publishes (or clears, with `None`) the process-wide runtime (step_017 lifespan).

    Warns (does not raise -- a hard failure here would be worse than a noisy
    log during an already-unusual lifespan sequence) if this replaces a
    *different*, still-live runtime that was not cleared via `close_runtime`
    first: that runtime's `in_flight` tasks and background event-stream
    polling would simply be dropped on the floor, unobserved.
    """
    global _runtime
    if rt is not None and _runtime is not None and _runtime is not rt:
        logger.warning(
            "a2a.runtime.replaced_without_close: set_runtime() replaced a live runtime "
            "(in_flight=%d) that was not drained via close_runtime() first",
            len(_runtime.in_flight),
        )
    _runtime = rt


def get_runtime() -> Optional[A2ARuntime]:
    """Returns the current runtime, or `None` before the lifespan has built one."""
    return _runtime


async def _fail_in_flight_tasks(rt: A2ARuntime, *, timeout_s: float) -> None:
    """Writes a FAILED status for every task in `rt.in_flight` (RB-1).

    Best-effort and bounded: delegates the reload-check-CAS-write sequence to
    `task_states.fail_task_cas` (architecture M2: the single place that does
    this, shared with the maintenance worker's stale-task sweep), which
    itself swallows a missing/already-terminal task and a lost
    `ConcurrentTaskModificationError` race. Every exception is caught and
    logged; this function itself never raises, so `close_runtime`'s `finally`
    always reaches `handler.aclose()`.
    """
    if not rt.in_flight:
        return

    async def _fail_one(owner: str, task_id: str) -> None:
        try:
            if await fail_task_cas(rt.store, task_id, owner, _SHUTDOWN_MESSAGE_TEXT):
                logger.info("a2a.runtime.shutdown_failed_task task_id=%s", task_id)
        except Exception:
            logger.exception("a2a.runtime.shutdown_fail_task_error task_id=%s", task_id)

    pending = list(rt.in_flight)
    try:
        await asyncio.wait_for(
            asyncio.gather(*(_fail_one(owner, task_id) for owner, task_id in pending)),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "a2a.runtime.shutdown_fail_in_flight_timeout count=%s timeout_s=%s",
            len(pending),
            timeout_s,
        )


async def close_runtime(timeout_s: float = _DEFAULT_CLOSE_TIMEOUT_S) -> None:
    """Drains and clears the process-wide runtime (step_017 lifespan shutdown, RB-1).

    Order: atomically swap `_runtime` to `None` first (so a concurrent
    `get_runtime()` never observes a runtime that is mid-shutdown), then
    best-effort fail every in-flight task, then -- in `finally`, so it always
    runs even if the fail-in-flight phase raised or timed out -- drain the
    handler via `handler.aclose()`, itself bounded by the same `timeout_s`.
    """
    global _runtime
    rt, _runtime = _runtime, None
    if rt is None:
        return
    try:
        await _fail_in_flight_tasks(rt, timeout_s=timeout_s)
    finally:
        await asyncio.wait_for(rt.handler.aclose(), timeout=timeout_s)


__all__ = [
    "A2ARuntime",
    "build_capability_card",
    "build_placeholder_extended_card",
    "configure_sdk_logging",
    "build_a2a_runtime",
    "set_runtime",
    "get_runtime",
    "close_runtime",
]
