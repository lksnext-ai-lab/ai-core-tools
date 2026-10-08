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
from typing import Any, Dict, Optional

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


def sanitize_json_response(resp: Response) -> Response:
    """Applies `sanitize_error_payload` to a plain (non-streaming) response.

    CRITICAL-2 (fix round 1): the sanitized response is built **without**
    copying any of the original response's headers -- in particular
    `Content-Length`, which would otherwise describe the *original* (longer)
    body and desync from the rewritten one, producing a framing error an
    HTTP/1.1 client (h11, curl) rejects outright ("Too little data for
    declared Content-Length"). `JSONResponse.__init__` computes a fresh,
    correct `Content-Length`/`Content-Type` for the new body on its own.
    """
    if not isinstance(resp, JSONResponse):
        return resp
    try:
        payload = json.loads(bytes(resp.body))
    except (TypeError, ValueError):
        return resp
    if not sanitize_error_payload(payload):
        return resp
    sanitized = JSONResponse(payload, status_code=resp.status_code)
    sanitized.background = resp.background
    return sanitized


def sanitize_sse_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitizes one in-flight SSE item's JSON-RPC `data` payload, if needed.

    Unlike `sanitize_json_response`, there is no HTTP framing concern here:
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


def derive_outcome(resp: Response) -> str:
    """A best-effort outcome label for `A2ARequestLog`, derived from a
    non-streaming response's own status/JSON-RPC error code."""
    if not isinstance(resp, JSONResponse):
        return f"http_{resp.status_code}"
    try:
        payload = json.loads(bytes(resp.body))
    except (TypeError, ValueError):
        return f"http_{resp.status_code}"
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        return f"jsonrpc_error_{payload['error'].get('code', 'unknown')}"
    return "ok"


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
    "sanitize_json_response",
    "sanitize_sse_item",
    "derive_outcome",
    "extract_task_id_from_sse_item",
]
