"""
Per-client-IP rate limiting for anonymous/discovery endpoints.

Unlike `rate_limit.py` (which enforces a per-app execution budget keyed by
`app.agent_rate_limit`), this module enforces a budget keyed by an arbitrary
string namespace plus the caller's IP address, backed by
`rate_limit_service.check_and_consume_key`. The counters live in a separate
dict in `RateLimitService`, so this traffic can never touch, and can never be
drained by, an app's execution budget.
"""
import ipaddress
import time

from fastapi import HTTPException, Request, status

from services.rate_limit_service import RateLimitState, rate_limit_service
from utils.logger import get_logger

logger = get_logger(__name__)


def enforce_ip_rate_limit(namespace: str, client_ip: str, limit_per_minute: int) -> RateLimitState:
    """
    Enforce a per-client-IP rate limit within a given namespace.

    This is a **fail-closed** check: unlike the `enforce_*` dependencies in
    `rate_limit.py`/`origins.py` (which, by existing public-API convention, log and
    continue on unexpected errors), any exception here propagates and must result in
    the request being rejected rather than silently allowed, since this is the only
    guard standing between an anonymous caller and an unbounded discovery budget.

    The budget is per **worker process** (in-memory counters, no shared backing
    store), so the effective rate limit across a multi-worker deployment is
    approximately `limit_per_minute * worker_count`, not a single global cap. This
    mirrors `apply_app_rate_limit`'s existing behavior for the per-app budget.

    A correct client IP behind a reverse proxy (e.g. Caddy) requires uvicorn to be
    configured with proxy headers (`--proxy-headers` / `forwarded_allow_ips`), so that
    `request.client.host` reflects the real client rather than the proxy. Without that
    configuration every request appears to share the proxy's IP and this limiter
    effectively becomes a single shared budget across all clients.

    Args:
        namespace: A short string identifying the budget (e.g. "a2a_discovery"). Kept
            distinct from any app id so this budget can never collide with, or drain,
            an app's `agent_rate_limit` counter.
        client_ip: The caller's IP address, typically `request.client.host`.
        limit_per_minute: Maximum requests per minute for this namespace+IP. A value
            `<= 0` means unlimited.

    Returns:
        RateLimitState describing the caller's current budget, when not exceeded.

    Raises:
        HTTPException: 429 if the limit is exceeded, with `Retry-After` and
            `X-RateLimit-*` headers, mirroring the shape used by `apply_app_rate_limit`.
    """
    key = f"{namespace}:{client_ip}"
    state = rate_limit_service.check_and_consume_key(key, limit_per_minute)

    if state.exceeded:
        retry_after = max(1, state.reset_epoch - int(time.time()))

        logger.info(f"IP rate limit exceeded for namespace '{namespace}': {limit_per_minute} requests per minute")

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum {limit_per_minute} requests per minute allowed.",
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(state.limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(state.reset_epoch)
            }
        )

    return state


def client_ip_from_request(request: Request) -> str:
    """
    Resolve the caller's rate-limit bucket key from a request's client IP.

    IPv6 addresses are bucketed by their /64 network: a residential or cloud IPv6
    allocation typically gives a client a full /64 (or larger) to rotate through
    freely, so limiting by the single address would be trivially bypassable. IPv4
    addresses are returned unchanged (no bucketing), and a client value that is not a
    valid IP (e.g. a unix socket path in some test clients) is passed through as-is.

    Args:
        request: The incoming FastAPI/Starlette request.

    Returns:
        The client IP (or IPv6 /64 network) as a string, or "unknown" if the
        connection info is unavailable (e.g. in some test clients).
    """
    if not request.client:
        return "unknown"

    host = request.client.host
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # Not a parseable IP (e.g. a unix socket path from some test clients).
        return host

    if ip.version == 6:
        network = ipaddress.ip_network(f"{host}/64", strict=False)
        return str(network.network_address) + "/64"

    return host
