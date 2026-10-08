"""The A2A HTTP surface: cards, catalog, JSON-RPC dispatch, root card (step_017, AD-4).

Three discovery `GET` routes (card, catalog, root) and one JSON-RPC `POST`
route. Every not-found path returns the byte-identical `not_found()` body
(AD-13); every discovery route is gated by a per-IP limiter that never
touches an app's execution budget (AC-12); the RPC route resolves visibility
through a short-lived `SessionLocal()` that it closes *before* dispatch
(NFR-4), validates the API key before the origin check (RB-8), reads the
body only through `read_body_capped` (never a FastAPI body param, RB-8), and
applies the app's `agent_rate_limit` budget only to `SendMessage`/
`SendStreamingMessage` (DEV-2).

Review-board carryovers (RB-2/3/4/5/8/12) are implemented in
`services/a2a_server/stream_controls.py` (RB-2/RB-3) and
`services/a2a_server/response_sanitizer.py` (RB-4), imported here; RB-5/RB-12
are implemented directly below, since they gate the SDK dispatch call itself.

Fix round 1 (step_017 review board) additionally hardens this module against:
- CRITICAL-1/2: see `stream_controls.py`/`response_sanitizer.py`.
- a per-IP, pre-auth limiter on the RPC route itself (MEDIUM-7);
- a snake_case/camelCase `task_id`/`context_id` bypass of RB-5/RB-12
  (MEDIUM-5: the SDK's protobuf JSON parsing accepts *both* spellings for
  the same field, last-one-in-the-document wins -- `_last_matching_value`
  mirrors that so the value this router validates/pre-checks is the exact
  one the SDK will actually use, never a decoy);
- log forging via an unvalidated `method`/`task_id`/`context_id`/`app_slug`
  (MEDIUM-6);
- a 64 KiB body cap on everything but `SendMessage`/`SendStreamingMessage`
  (MEDIUM-8);
- a single extra `App` query only for `SendMessage`/`SendStreamingMessage`
  rate limiting, never for the origin check (MEDIUM-11: the origin check now
  reads `agent_cors_origins` straight off the snapshot);
- running every blocking `SessionLocal()` DB call in the threadpool, never
  directly on the event loop (MEDIUM-13).
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from starlette.background import BackgroundTask

from a2a.server.request_handlers.response_helpers import build_error_response
from a2a.utils.errors import InternalError, InvalidParamsError, UnsupportedOperationError

from db.database import SessionLocal
from models.app import App
from routers.controls.body_limit import BodyReadAborted, make_replay_request, read_body_capped
from routers.controls.ip_rate_limit import client_ip_from_request, enforce_ip_rate_limit
from routers.controls.origins import check_allowed_origin
from routers.controls.rate_limit import apply_app_rate_limit
from routers.public.v1.auth import api_key_header
from services.a2a_server.card_service import build_public_card, card_to_json, catalog_entry
from services.a2a_server.identity import A2ACallScope, A2ARequestLog, context_for_owner, owner_for
from services.a2a_server.response_sanitizer import derive_outcome, sanitize_json_response
from services.a2a_server.runtime import get_runtime
from services.a2a_server.stream_controls import (
    TERMINAL_TASK_STATES,
    bounded_sse_iterator,
    try_acquire_stream_bulkhead,
)
from services.a2a_server.visibility_service import Outcome, Resolution, list_visible, resolve, resolve_root
from utils.a2a_config import get_a2a_config
from utils.a2a_config import public_base_url as resolve_public_base_url
from utils.logger import get_logger

logger = get_logger(__name__)

a2a_router = APIRouter(tags=["A2A"])

_DISCOVERY_NAMESPACE = "a2a-discovery"
_RPC_PREAUTH_NAMESPACE = "a2a-rpc-preauth"

# AD-7/RB-12: client-supplied taskId/contextId must fit the SDK's String(36)
# columns and this charset. Duplicated from `services/a2a_server/
# context_builders.py` by design (see this module's docstring and that
# module's own docstring): this check must run *before* dispatch, ahead of
# the SDK's own store lookup for an existing taskId, which runs before our
# request-context builder ever gets a look at the value.
_ID_MAX_LENGTH = 36
_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")

# MEDIUM-6 (fix round 1): only a slug matching this shape is ever placed into
# a log line verbatim; anything else (including a URL-decoded control
# character) is replaced with a fixed placeholder so a crafted `app_slug`
# path segment can never forge or split a log line.
_SLUG_LOG_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,100}$")

# Methods (v1.0 + v0.3 compat) that consume the app's execution budget (DEV-2).
_SEND_METHODS = frozenset({"SendMessage", "SendStreamingMessage", "message/send", "message/stream"})

# Methods that open an SSE response (RB-2/RB-3).
_STREAM_METHODS = frozenset({"SendStreamingMessage", "SubscribeToTask", "message/stream", "tasks/resubscribe"})

# Methods whose JSON-RPC `params` carry a bare `{"id": "..."}` task id.
_TASK_ID_PARAM_METHODS = frozenset(
    {"GetTask", "CancelTask", "SubscribeToTask", "tasks/get", "tasks/cancel", "tasks/resubscribe"}
)

# MEDIUM-6: every method name this router (or the SDK, including its v0.3
# compat adapter) actually recognizes. A `method` outside this set is never
# logged verbatim (see `_safe_method_for_log`) -- it still reaches the
# dispatcher unchanged (which rejects it with `MethodNotFoundError` on its
# own), this allow-list only gates *logging*.
_KNOWN_METHODS = frozenset(
    {
        "SendMessage", "SendStreamingMessage", "GetTask", "ListTasks", "CancelTask", "SubscribeToTask",
        "GetExtendedAgentCard", "CreateTaskPushNotificationConfig", "GetTaskPushNotificationConfig",
        "ListTaskPushNotificationConfigs", "DeleteTaskPushNotificationConfig",
        "message/send", "message/stream", "tasks/get", "tasks/cancel", "tasks/resubscribe",
        "tasks/pushNotificationConfig/set", "tasks/pushNotificationConfig/get",
        "tasks/pushNotificationConfig/list", "tasks/pushNotificationConfig/delete",
    }
)

_INTERNAL_ERROR_CODE = -32603
_RETRYABLE_ERROR_MESSAGE = "A temporary server error occurred; please retry."

# MEDIUM-8 (fix round 1): a body larger than this for anything other than
# SendMessage/SendStreamingMessage is rejected with 413, even though it was
# already read within the (much larger) `A2A_MAX_REQUEST_MB` cap.
_NON_SEND_BODY_CAP_FALLBACK = 65536
# Bodies above this size are JSON-decoded in the threadpool, not on the loop.
_INLINE_JSON_PARSE_MAX_BYTES = 256 * 1024
# Bounds the RB-5 terminal-task pre-check's store read.
_TERMINAL_PRECHECK_TIMEOUT_SECONDS = 2.0
# Max time one SSE `send()` may block on a client that stopped reading.
_SSE_SEND_TIMEOUT_SECONDS = 30


def not_found() -> JSONResponse:
    """Uniform 404, byte-identical to Starlette's unmatched-route default (AD-13)."""
    return JSONResponse({"detail": "Not Found"}, status_code=status.HTTP_404_NOT_FOUND)


def _resolve_base_url(request: Request) -> str:
    return resolve_public_base_url(str(request.base_url)) or str(request.base_url).rstrip("/")


def _safe_slug_for_log(slug: str) -> str:
    """MEDIUM-6: gates `app_slug` before it is ever interpolated into a log line."""
    return slug if isinstance(slug, str) and _SLUG_LOG_PATTERN.match(slug) else "(invalid)"


def _safe_method_for_log(method: Optional[str]) -> str:
    """MEDIUM-6: only a recognized method name is ever logged verbatim."""
    return method if method in _KNOWN_METHODS else "(unknown)"


def _safe_id_for_log(value: Optional[str]) -> Optional[str]:
    """MEDIUM-6: logs a `taskId`/`contextId` only once it has passed shape
    validation; otherwise logs its length, never its (possibly
    log-injecting) raw content."""
    if value is None:
        return None
    if _valid_id_shape(value):
        return value
    return f"(invalid,len={len(value)})"


def _run_resolve(app_slug: str, agent_id: int, raw_api_key: Optional[str]) -> Resolution:
    """Sync DB work for `resolve()`, run via `run_in_threadpool` (MEDIUM-13)."""
    db = SessionLocal()
    try:
        return resolve(db, app_slug, agent_id, raw_api_key=raw_api_key)
    finally:
        db.close()


def _run_list_visible(app_slug: str, raw_api_key: Optional[str]):
    db = SessionLocal()
    try:
        return list_visible(db, app_slug, raw_api_key=raw_api_key)
    finally:
        db.close()


def _run_resolve_root() -> Resolution:
    db = SessionLocal()
    try:
        return resolve_root(db)
    finally:
        db.close()


def _run_load_app(app_id: int) -> Optional[App]:
    db = SessionLocal()
    try:
        return db.query(App).filter(App.app_id == app_id).first()
    finally:
        db.close()


def _parse_canonical_agent_id(raw: str) -> Optional[int]:
    """LOW (fix round 1): only a canonical, non-padded ASCII-digit string is
    a valid `agent_id` path segment. `" 9"`, `"09"`, full-width digits and
    anything `int()` would otherwise coerce all fall into the uniform 404."""
    if not raw or not raw.isascii() or not raw.isdigit():
        return None
    if raw != "0" and raw.startswith("0"):
        return None
    return int(raw)


# ---------------------------------------------------------------------------
# Discovery (AD-4 step 3, FR-2/FR-9/FR-10, AC-1/AC-3..AC-7/AC-10/AC-12)
# ---------------------------------------------------------------------------


def _log_discovery(kind: str, *, outcome: str, reason: Optional[str], client_ip: str, **fields: Any) -> None:
    if "app_slug" in fields:
        fields["app_slug"] = _safe_slug_for_log(fields["app_slug"])
    extra = " ".join(f"{k}={v}" for k, v in fields.items())
    logger.info(
        "a2a.discovery.%s outcome=%s reason=%s client_ip=%s %s",
        kind, outcome, reason, client_ip, extra,
    )


@a2a_router.get(
    "/a2a/v1/apps/{app_slug}/agents/{agent_id}/.well-known/agent-card.json",
    include_in_schema=False,
)
async def get_agent_card(
    app_slug: str,
    agent_id: str,
    request: Request,
    api_key: Optional[str] = Depends(api_key_header),
) -> Response:
    """Per-agent A2A v1.0 card (FR-5). `agent_id` is typed `str` so a
    non-numeric value falls into the uniform 404, never FastAPI's 422."""
    cfg = get_a2a_config()
    client_ip = client_ip_from_request(request)
    enforce_ip_rate_limit(_DISCOVERY_NAMESPACE, client_ip, cfg.discovery_rate_limit_per_minute)

    if not cfg.enabled:
        _log_discovery("card", outcome="not_found", reason="disabled_global", client_ip=client_ip)
        return not_found()

    agent_id_int = _parse_canonical_agent_id(agent_id)
    if agent_id_int is None:
        _log_discovery("card", outcome="not_found", reason="bad_agent_id", client_ip=client_ip, app_slug=app_slug)
        return not_found()

    resolution = await run_in_threadpool(_run_resolve, app_slug, agent_id_int, api_key)

    if resolution.outcome is not Outcome.VISIBLE or resolution.snapshot is None:
        _log_discovery(
            "card", outcome="not_found", reason=resolution.reason.value, client_ip=client_ip,
            app_slug=app_slug, agent_id=agent_id_int,
        )
        return not_found()

    base_url = _resolve_base_url(request)
    card = card_to_json(build_public_card(resolution.snapshot, base_url))
    cache_control = "no-store" if resolution.key is not None else "no-cache"
    _log_discovery(
        "card", outcome="visible", reason="visible", client_ip=client_ip,
        app_slug=app_slug, agent_id=agent_id_int,
    )
    return JSONResponse(card, headers={"Cache-Control": cache_control, "Content-Type": "application/json"})


@a2a_router.get("/a2a/v1/apps/{app_slug}/agents", include_in_schema=False)
async def list_agents(
    app_slug: str,
    request: Request,
    api_key: Optional[str] = Depends(api_key_header),
) -> Response:
    """The Mattin-specific app catalog (FR-9): visible agents, `agent_id` ascending."""
    cfg = get_a2a_config()
    client_ip = client_ip_from_request(request)
    enforce_ip_rate_limit(_DISCOVERY_NAMESPACE, client_ip, cfg.discovery_rate_limit_per_minute)

    if not cfg.enabled:
        _log_discovery("catalog", outcome="not_found", reason="disabled_global", client_ip=client_ip)
        return not_found()

    snapshots = await run_in_threadpool(_run_list_visible, app_slug, api_key)

    if not snapshots:
        _log_discovery("catalog", outcome="not_found", reason="empty_or_missing", client_ip=client_ip, app_slug=app_slug)
        return not_found()

    base_url = _resolve_base_url(request)
    entries = [catalog_entry(snap, base_url) for snap in snapshots]
    cache_control = "no-store" if api_key else "no-cache"
    _log_discovery(
        "catalog", outcome="visible", reason="visible", client_ip=client_ip,
        app_slug=app_slug, count=len(entries),
    )
    return JSONResponse(entries, headers={"Cache-Control": cache_control, "Content-Type": "application/json"})


@a2a_router.get("/.well-known/agent-card.json", include_in_schema=False)
async def get_root_agent_card(request: Request) -> Response:
    """The root card for `A2A_ROOT_AGENT` (FR-2); public-visibility only (AC-7)."""
    cfg = get_a2a_config()
    client_ip = client_ip_from_request(request)
    enforce_ip_rate_limit(_DISCOVERY_NAMESPACE, client_ip, cfg.discovery_rate_limit_per_minute)

    if not cfg.enabled:
        _log_discovery("root_card", outcome="not_found", reason="disabled_global", client_ip=client_ip)
        return not_found()

    resolution = await run_in_threadpool(_run_resolve_root)

    if resolution.outcome is not Outcome.VISIBLE or resolution.snapshot is None:
        _log_discovery("root_card", outcome="not_found", reason=resolution.reason.value, client_ip=client_ip)
        return not_found()

    base_url = _resolve_base_url(request)
    card = card_to_json(build_public_card(resolution.snapshot, base_url))
    _log_discovery("root_card", outcome="visible", reason="visible", client_ip=client_ip)
    return JSONResponse(card, headers={"Cache-Control": "no-cache", "Content-Type": "application/json"})


# ---------------------------------------------------------------------------
# JSON-RPC (AD-4 step 4)
# ---------------------------------------------------------------------------


def _valid_id_shape(value: Optional[str]) -> bool:
    if value is None:
        return True
    return bool(value) and len(value) <= _ID_MAX_LENGTH and bool(_ID_PATTERN.match(value))


def _rpc_request_id(body: Any) -> Any:
    if isinstance(body, dict):
        rid = body.get("id")
        if rid is None or isinstance(rid, (str, int)):
            return rid
    return None


def _error_json_response(request_id: Any, error: Exception) -> JSONResponse:
    return JSONResponse(build_error_response(request_id, error), status_code=200)


def _last_matching_value(d: Dict[str, Any], names: Tuple[str, ...]) -> Optional[str]:
    """MEDIUM-5 (fix round 1): mirrors protobuf JSON parsing's own
    last-key-wins behaviour for a field with two accepted spellings
    (`taskId`/`task_id`, `contextId`/`context_id`) -- `ParseDict` resolves
    both names to the *same* proto field and the value from whichever key
    appears **last** in the JSON document wins (verified empirically against
    `a2a.types.a2a_pb2.Message`). Checking only one spelling -- or rejecting
    on "both present" rather than computing the actual winner -- would let a
    caller smuggle a decoy value past this router's own RB-5/RB-12 checks
    while the SDK itself honors the other one.
    """
    result: Optional[str] = None
    for key, value in d.items():
        if key in names and isinstance(value, str):
            result = value
    return result


def _peek_ids(method: Optional[str], params: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Best-effort extraction of the *authoritative* `taskId`/`contextId`
    from the peeked JSON body -- see `_last_matching_value`.

    Never raises: a malformed shape is simply treated as absent here and
    left for the real shape check (`_valid_id_shape`) or the dispatcher's own
    parsing to reject properly.
    """
    if method in _TASK_ID_PARAM_METHODS:
        raw_id = params.get("id")
        return (raw_id if isinstance(raw_id, str) else None), None
    message = params.get("message")
    if not isinstance(message, dict):
        return None, None
    task_id = _last_matching_value(message, ("taskId", "task_id"))
    context_id = _last_matching_value(message, ("contextId", "context_id"))
    return task_id, context_id


def _derive_outcome(resp: Response) -> str:
    return derive_outcome(resp)


def _chain_background(resp: Response, task: BackgroundTask) -> None:
    """Sets `resp.background`, running any task the dispatcher already set first."""
    existing = resp.background
    if existing is None:
        resp.background = task
        return

    async def _run_both() -> None:
        await existing()
        await task()

    resp.background = BackgroundTask(_run_both)


def _attach_rate_limit_headers(resp: Response, response_headers: Dict[str, str]) -> Response:
    """MEDIUM-12 (fix round 1): the single funnel every return path -- the
    three early-reject ones (RB-12 shape, RB-5 terminal, RB-3 bulkhead) and
    the final dispatch one -- uses to copy the `X-RateLimit-*` headers
    `apply_app_rate_limit` already set, so a caller whose send consumed
    budget always sees its remaining-budget headers, including on a
    response this router built itself rather than the dispatcher."""
    for header_name, header_value in response_headers.items():
        resp.headers[header_name] = header_value
    return resp


@a2a_router.post("/a2a/v1/apps/{app_slug}/agents/{agent_id}", include_in_schema=False)
async def rpc_endpoint(app_slug: str, agent_id: str, request: Request) -> Response:
    """The per-agent JSON-RPC endpoint (AD-4). No FastAPI body param (RB-8):
    the body is read once, through `read_body_capped`, and replayed to the
    dispatcher via `make_replay_request`."""
    cfg = get_a2a_config()

    # MEDIUM-7 (fix round 1): a target-independent, pre-auth limiter -- the
    # very first thing this route does, before the kill switch, visibility
    # resolution or any DB work.
    client_ip = client_ip_from_request(request)
    enforce_ip_rate_limit(_RPC_PREAUTH_NAMESPACE, client_ip, cfg.rpc_preauth_rate_limit_per_minute)

    rt = get_runtime()
    if rt is None or not cfg.enabled:
        return not_found()

    agent_id_int = _parse_canonical_agent_id(agent_id)
    if agent_id_int is None:
        return not_found()

    raw_key = request.headers.get("x-api-key")

    resolution: Resolution = await run_in_threadpool(_run_resolve, app_slug, agent_id_int, raw_key)

    if resolution.outcome is not Outcome.VISIBLE or resolution.snapshot is None:
        # NFR-2: no key validation work beyond what `resolve()` already does
        # uniformly; nothing extra runs on this path.
        logger.info(
            "a2a.rpc_denied app_slug=%s agent_id=%s outcome=not_found reason=%s client_ip=%s",
            _safe_slug_for_log(app_slug), agent_id_int, resolution.reason.value, client_ip,
        )
        return not_found()

    snapshot = resolution.snapshot

    if resolution.key is None:
        logger.info(
            "a2a.rpc_denied app_id=%s agent_id=%s outcome=unauthorized reason=key_required client_ip=%s",
            snapshot.app_id, agent_id_int, client_ip,
        )
        return JSONResponse(
            {"detail": "Valid X-API-KEY required"},
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": 'ApiKey header="X-API-KEY"'},
        )

    # RB-8/MEDIUM-11: origin check only after the API key is validated (so a
    # 403 can never reveal app existence independently of the uniform
    # 404/401), and read straight off the snapshot -- no second `App` query.
    origin_app = _OriginCheckApp(app_id=snapshot.app_id, agent_cors_origins=snapshot.app_agent_cors_origins)
    check_allowed_origin(origin_app, request.headers.get("origin"), app_ref=app_slug)

    base_url = _resolve_base_url(request)

    try:
        body = await read_body_capped(request, cfg.max_request_mb * 1024 * 1024)
    except BodyReadAborted:
        # The client is already gone by the time this fires, so the 499
        # below is purely informational (for access logs/proxies) -- no
        # A2ARequestLog exists yet at this point in AD-4's own step
        # ordering (it is created only after the body is read), so this is
        # a single, synchronous INFO line rather than a BackgroundTask.
        logger.info(
            "a2a.rpc app_id=%s agent_id=%s api_key_id=%s outcome=client_disconnect",
            snapshot.app_id, agent_id_int, resolution.key.key_id,
        )
        return Response(status_code=499)

    try:
        # A large body is parsed in the threadpool: decoding tens of MB of
        # JSON on the event loop would stall every other tenant on the worker.
        if len(body) > _INLINE_JSON_PARSE_MAX_BYTES:
            parsed = await run_in_threadpool(json.loads, body)
        else:
            parsed = json.loads(body)
    except (TypeError, ValueError):
        parsed = None  # left to the dispatcher's own JSON-parse-error handling

    raw_method = parsed.get("method") if isinstance(parsed, dict) else None
    # MEDIUM-6 (fix round 1): a non-string `method` (e.g. a JSON number or
    # list) must never reach a `dict`/`set` membership test or an f-string
    # unguarded -- normalize to `None` up front.
    method: Optional[str] = raw_method if isinstance(raw_method, str) else None
    request_id = _rpc_request_id(parsed)
    params: Dict[str, Any] = {}
    if isinstance(parsed, dict) and isinstance(parsed.get("params"), dict):
        params = parsed["params"]

    # MEDIUM-8 (fix round 1): everything but a send gets a much smaller body cap.
    if method not in _SEND_METHODS and len(body) > (cfg.non_send_max_body_bytes or _NON_SEND_BODY_CAP_FALLBACK):
        return Response(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

    response_headers: Dict[str, str] = {}
    app_row: Optional[App] = None
    if method in _SEND_METHODS:
        # DEV-2/MEDIUM-11: only a send needs the app's row at all (for its
        # `agent_rate_limit`); every other method skips this query entirely.
        app_row = await run_in_threadpool(_run_load_app, snapshot.app_id)
        if app_row is not None:
            apply_app_rate_limit(app_row, response_headers)

    request_log = A2ARequestLog(method=_safe_method_for_log(method) if method else "(unparsed)")
    task_id_param, context_id_param = _peek_ids(method, params)
    request_log.task_id = _safe_id_for_log(task_id_param)
    request_log.context_id = _safe_id_for_log(context_id_param)

    owner = owner_for(snapshot.app_id, snapshot.agent_id, resolution.key.key_hash)

    def _emit_now(outcome: str) -> None:
        request_log.outcome = outcome
        request_log.emit(logger, app_id=snapshot.app_id, agent_id=snapshot.agent_id, api_key_id=resolution.key.key_id)

    # RB-12: shape-validate taskId/contextId before dispatch and before the
    # RB-5 pre-check -- the SDK looks up an existing taskId in the store
    # before our own request-context builder ever runs.
    if not _valid_id_shape(task_id_param) or not _valid_id_shape(context_id_param):
        resp = _error_json_response(
            request_id,
            InvalidParamsError(message="taskId/contextId must be at most 36 characters of [A-Za-z0-9._:-]"),
        )
        _emit_now("invalid_id_shape")
        return _attach_rate_limit_headers(resp, response_headers)

    # RB-5: a send naming an existing, already-terminal task is rejected
    # before dispatch (the SDK's own path would still invoke the executor).
    if method in _SEND_METHODS and task_id_param:
        try:
            stored = await asyncio.wait_for(
                rt.store.get(task_id_param, context_for_owner(owner)),
                timeout=_TERMINAL_PRECHECK_TIMEOUT_SECONDS,
            )
        except Exception:
            logger.warning(
                "a2a.rpc.terminal_precheck_error task_id=%s", _safe_id_for_log(task_id_param), exc_info=True
            )
            stored = None
        if stored is not None and stored.task.status.state in TERMINAL_TASK_STATES:
            resp = _error_json_response(
                request_id,
                UnsupportedOperationError(
                    message=f"Task {task_id_param} is already in a terminal state and cannot "
                    "accept further messages."
                ),
            )
            _emit_now("task_already_terminal")
            return _attach_rate_limit_headers(resp, response_headers)

    bulkhead = None
    if method in _STREAM_METHODS:
        bulkhead = await try_acquire_stream_bulkhead(cfg, app_id=snapshot.app_id, key_id=resolution.key.key_id)
        if bulkhead is None:
            resp = _error_json_response(
                request_id,
                InternalError(
                    message="Too many concurrent streams; please retry shortly.",
                    data={"retryable": True, "retryAfterSeconds": 2},
                ),
            )
            _emit_now("stream_bulkhead_rejected")
            return _attach_rate_limit_headers(resp, response_headers)

    scope = A2ACallScope(
        app_id=snapshot.app_id,
        app_slug=snapshot.app_slug,
        agent_id=snapshot.agent_id,
        api_key_id=resolution.key.key_id,
        api_key_hash=resolution.key.key_hash,
        api_key=resolution.key.raw,
        snapshot=snapshot,
        request_log=request_log,
        base_url=base_url,
    )
    request.state.a2a_scope = scope

    replay_request = make_replay_request(request, body)
    if parsed is not None:
        # MEDIUM-8 (fix round 1): hands the dispatcher the already-parsed
        # body directly -- `starlette.requests.Request.json()` serves
        # `self._json` verbatim if present (see `make_replay_request`'s own
        # docstring for the identical `_body` fast path this mirrors),
        # so this avoids a second `json.loads` over the same bytes.
        replay_request._json = parsed

    try:
        resp = await rt.dispatcher.handle_requests(replay_request)
    except Exception:
        # Defense in depth only: `handle_requests` is written to always
        # return a Response (its own top-level `except Exception` already
        # converts an unhandled error into a JSON-RPC InternalError), but a
        # bulkhead slot must never leak if that contract is ever broken.
        logger.exception("a2a.rpc.dispatch_error task_id=%s", _safe_id_for_log(task_id_param))
        if bulkhead is not None:
            bulkhead.release()
        resp = _error_json_response(request_id, InternalError(message=_RETRYABLE_ERROR_MESSAGE, data={"retryable": True}))

    if isinstance(resp, EventSourceResponse):
        # A client that keeps the socket open but stops reading would block
        # `send()` forever, so the wall-clock cap would never fire and the
        # bulkhead slot would never be released.
        resp.send_timeout = _SSE_SEND_TIMEOUT_SECONDS
        if hasattr(resp, "body_iterator"):
            resp.body_iterator = bounded_sse_iterator(
                resp.body_iterator,
                rt=rt,
                owner=owner,
                task_id=task_id_param,
                stream_max_seconds=cfg.stream_max_seconds,
                liveness_interval_seconds=cfg.stream_liveness_seconds,
                event_poll_seconds=cfg.event_poll_seconds,
                bulkhead=bulkhead,
                request_log=request_log,
            )
        else:
            # MEDIUM-14 (fix round 1): the SDK's `EventSourceResponse` has
            # always exposed `body_iterator` (it is how `sse_starlette`
            # itself drives the response) -- if that contract ever breaks,
            # RB-2's wall-clock/liveness guard and RB-3's bulkhead release
            # would both silently stop applying to every stream. Fail loud,
            # not silent: log at ERROR and still release the bulkhead so a
            # permit is never leaked.
            logger.error(
                "a2a.rpc.sse_contract_broken: EventSourceResponse has no body_iterator; "
                "RB-2/RB-3 guards are not applied to this stream"
            )
            if bulkhead is not None:
                bulkhead.release()
            if request_log.outcome is None:
                request_log.outcome = "sse_contract_broken"
    else:
        resp = sanitize_json_response(resp)
        if bulkhead is not None:
            bulkhead.release()
        if request_log.outcome is None:
            request_log.outcome = _derive_outcome(resp)

    resp = _attach_rate_limit_headers(resp, response_headers)

    emit_task = BackgroundTask(
        request_log.emit, logger, app_id=snapshot.app_id, agent_id=snapshot.agent_id,
        api_key_id=resolution.key.key_id,
    )
    if bulkhead is not None:
        # MEDIUM-9 (fix round 1): idempotent defense-in-depth. The stream
        # wrapper's own `finally` already releases `bulkhead` as the first
        # thing it does on every exit path; this second call is a no-op
        # unless that invariant is ever broken, in which case it is the
        # difference between a transient leak and a stuck bulkhead slot.
        background_bulkhead = bulkhead

        async def _release_bulkhead_too() -> None:
            background_bulkhead.release()

        _chain_background(resp, BackgroundTask(_release_bulkhead_too))
    _chain_background(resp, emit_task)
    return resp


class _OriginCheckApp:
    """A minimal duck-typed stand-in for `models.app.App` (MEDIUM-11).

    `check_allowed_origin` (`routers/controls/origins.py`) only ever reads
    `app.agent_cors_origins` and `app.app_id` off its `app` argument -- never
    checks `isinstance`, so this avoids a second `App` row fetch for the
    overwhelming majority of RPC calls (every one that is not a send).
    """

    __slots__ = ("app_id", "agent_cors_origins")

    def __init__(self, *, app_id: int, agent_cors_origins: Optional[str]) -> None:
        self.app_id = app_id
        self.agent_cors_origins = agent_cors_origins


__all__ = ["a2a_router", "not_found"]
