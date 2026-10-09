"""RB-4: never let a JSON-RPC `-32603` (INTERNAL_ERROR_CODE) response reach
the caller with the SDK dispatcher's raw `str(e)` (step_017 fix round 1,
CRITICAL-2 + HIGH-4).

`a2a.server.routes.jsonrpc_dispatcher.JsonRpcDispatcher` catches generic
`Exception` in three places (its own top-level `handle_requests`, the eager
first-event fetch inside `_process_streaming_request`, and the per-item loop
inside `_create_response`'s `event_generator`) and, for anything that is not
already an `A2AError`/`JSONRPCError`, builds `InternalError(message=str(e))`
-- which can leak a DB pool-timeout/`DBAPIError`'s connection string or query
text. None of those three call sites are reachable from this package without
copying SDK internals, so sanitization happens here instead, at the response
boundary: every `-32603` error -- plain JSON or an in-flight SSE event -- is
rewritten to a generic, retryable message before either reaches the caller.

Extracted out of `routers/a2a_server/router.py` (fix round 1) for unit
testability without an HTTP round trip.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

from fastapi.responses import JSONResponse
from starlette.responses import Response

INTERNAL_ERROR_CODE = -32603
RETRYABLE_ERROR_MESSAGE = "A temporary server error occurred; please retry."


def sanitize_error_payload(payload: Any) -> bool:
    """Mutates a JSON-RPC response payload in place if its `error.code` is
    `-32603`, replacing `message`/`data` with a generic, retryable pair.

    Returns True iff it changed anything. Never raises: any shape other than
    `{"error": {"code": -32603, ...}}` is left untouched.
    """
    if not isinstance(payload, dict):
        return False
    error = payload.get("error")
    if not isinstance(error, dict) or error.get("code") != INTERNAL_ERROR_CODE:
        return False
    error["message"] = RETRYABLE_ERROR_MESSAGE
    error["data"] = {"retryable": True}
    return True


def sanitize_sse_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitizes one in-flight SSE item's JSON-RPC `data` payload, if needed.

    Unlike `sanitize_and_derive_outcome`, there is no HTTP framing concern here:
    SSE frames are newline-delimited, not length-prefixed, so rewriting
    `data` to a same-or-different length is always safe.
    """
    raw = item.get("data") if isinstance(item, dict) else None
    if not raw:
        return item
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return item
    if not sanitize_error_payload(payload):
        return item
    sanitized_item = dict(item)
    sanitized_item["data"] = json.dumps(payload)
    return sanitized_item


def sanitize_and_derive_outcome(resp: Response) -> Tuple[Response, str]:
    """Sanitizes a non-streaming response and derives its outcome label from one JSON parse.

    `b'"error"'` is a cheap substring probe, so the common success path (`{"result": ...}`)
    never parses at all. The rewrite itself is delegated to `sanitize_error_payload`. A
    rewritten body gets a fresh `JSONResponse` (so `Content-Length` matches the new body)
    that keeps the original `background` task.

    Returns:
        The (possibly rewritten) response and the outcome label of the *original* payload.
    """
    if not isinstance(resp, JSONResponse):
        return resp, f"http_{resp.status_code}"
    raw = bytes(resp.body)
    if b'"error"' not in raw:
        return resp, "ok"
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return resp, f"http_{resp.status_code}"
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return resp, "ok"
    outcome = f"jsonrpc_error_{error.get('code', 'unknown')}"
    if not sanitize_error_payload(payload):
        return resp, outcome
    sanitized = JSONResponse(payload, status_code=resp.status_code)
    sanitized.background = resp.background
    return sanitized, outcome


def extract_task_id_from_sse_item(item: Dict[str, Any]) -> Optional[str]:
    """Best-effort extraction of the task id from one SSE item's JSON-RPC payload."""
    raw = item.get("data") if isinstance(item, dict) else None
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None
    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        return None
    task = result.get("task")
    if isinstance(task, dict) and isinstance(task.get("id"), str):
        return task["id"]
    for key in ("statusUpdate", "artifactUpdate"):
        sub = result.get(key)
        if isinstance(sub, dict) and isinstance(sub.get("taskId"), str):
            return sub["taskId"]
    return None


__all__ = [
    "INTERNAL_ERROR_CODE",
    "RETRYABLE_ERROR_MESSAGE",
    "sanitize_error_payload",
    "sanitize_sse_item",
    "sanitize_and_derive_outcome",
    "extract_task_id_from_sse_item",
]
