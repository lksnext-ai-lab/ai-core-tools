"""
Byte-capped request body reading and replay.

`read_body_capped` enforces a maximum body size on bytes **actually read** from the
ASGI stream, not only on the `Content-Length` header, so a chunked request with no
Content-Length cannot bypass the cap. `make_replay_request` lets a caller consume the
body once (to inspect it, e.g. to peek a JSON-RPC method) and then hand a fresh
`Request` wrapping the same buffered bytes to downstream code that needs to read the
body again, while still sharing `request.state`.

Both functions in this module are **fail-closed**: any error (an over-cap body, a
mid-read client disconnect, a stalled read) raises, and the caller must reject the
request rather than fall back to serving it unread. This is a deliberate contrast
with the existing `enforce_*` dependencies in `rate_limit.py`/`origins.py`, which are
**fail-open** by established public-API convention (they log unexpected errors and
let the request through, because the DB lookup they depend on is a secondary
concern next to serving the request). A body-size guard has no such fallback: if it
cannot verify size, it must not claim the body is safe to read downstream.
"""
import asyncio

from fastapi import HTTPException, Request, status
from starlette.requests import ClientDisconnect

from utils.logger import get_logger

logger = get_logger(__name__)

#: Default wall-clock budget for reading a request body end to end.
DEFAULT_READ_TIMEOUT_SECONDS = 30.0


class BodyReadAborted(Exception):
    """Raised when the client disconnects before the body is fully read."""


async def read_body_capped(
    request: Request,
    max_bytes: int,
    *,
    read_timeout_s: float = DEFAULT_READ_TIMEOUT_SECONDS,
) -> bytes:
    """
    Read a request body while enforcing a byte cap on bytes actually read.

    Pre-rejects using `Content-Length` when present and already over the cap, then
    streams the body via `request.stream()`, counting bytes as they arrive so a
    chunked body with no `Content-Length` cannot exceed the cap either. The whole
    read is bounded by `read_timeout_s`, so a slow or stalled client cannot hold the
    connection (and a worker) open indefinitely.

    Args:
        request: The incoming request.
        max_bytes: Maximum allowed body size in bytes.
        read_timeout_s: Maximum wall-clock time allowed for the full read.

    Returns:
        The full body as bytes, if within the cap.

    Raises:
        HTTPException: 413 with `{"detail": "Request body too large"}` if the cap is
            exceeded, by `Content-Length` or by bytes actually read; 408 with
            `{"detail": "Request body read timeout"}` if `read_timeout_s` elapses
            before the body finishes.
        BodyReadAborted: if the client disconnects before the body is fully read.
    """
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > max_bytes:
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                     detail="Request body too large")
        except ValueError:
            # Malformed Content-Length: fall through to the streaming check below,
            # which is authoritative regardless.
            pass

    try:
        async with asyncio.timeout(read_timeout_s):
            buffer = bytearray()
            async for chunk in request.stream():
                buffer += chunk
                if len(buffer) > max_bytes:
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                         detail="Request body too large")
    except ClientDisconnect as exc:
        raise BodyReadAborted("Client disconnected before the request body was fully read") from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_408_REQUEST_TIMEOUT,
                             detail="Request body read timeout") from exc

    return bytes(buffer)


def make_replay_request(request: Request, body: bytes) -> Request:
    """
    Build a new `Request` over the same ASGI scope/receive that replays an
    already-read body, without wrapping `receive()`.

    This lets a buffered body be read once by `read_body_capped` (e.g. to peek the
    JSON-RPC method) and then handed, unread, to downstream dispatch code via a fresh
    `Request` object. The returned request shares `scope`, so `request.state` set by
    earlier dependencies/middleware remains visible, and it shares the *real*
    `receive` callable, so `is_disconnected()` and any later ASGI messages reflect
    the actual underlying connection.

    Implementation note (Starlette 1.7.0): do **not** intercept `receive()` to hand
    back a synthetic `{"type": "http.request", "body": body, ...}` message on the
    first call. `HTTPConnection.is_disconnected()` calls `self._receive()` inside an
    immediately-cancelled `anyio.CancelScope`; if that call is the interceptor, it
    still consumes (and discards) the one-shot replay message, so a later
    `.body()`/`.stream()`/`.json()` call finds nothing buffered and blocks on the
    real channel instead. Starlette's `Request.stream()` (and therefore `.body()`
    and `.json()`) already special-cases this: `if hasattr(self, "_body"): yield
    self._body; yield b""; return` — so setting `_body` directly makes those reads
    serve the buffered bytes without ever touching `receive()`, while `receive()`
    itself (used by `is_disconnected()` and anything else that reads the raw ASGI
    channel) stays wired straight to the original, real receive callable. If a
    future Starlette version changes this `_body` fast path, this function (and its
    tests) need to change too — pin and review on upgrade.

    Args:
        request: The original request, whose `scope` and `receive` callable are reused.
        body: The full, already-read body bytes to replay.

    Returns:
        A new `starlette.requests.Request` whose `.body()`/`.stream()`/`.json()`
        serve `body` directly, and whose `receive()` is the original, real channel.
    """
    replay_request = Request(request.scope, receive=request.receive)
    replay_request._body = body
    return replay_request
