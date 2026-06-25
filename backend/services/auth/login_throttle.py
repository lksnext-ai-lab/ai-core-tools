"""Per-IP and per-account fixed-window login throttle for LOCAL auth mode.

``login_throttle`` (IP-keyed) is a FastAPI dependency; ``_account_throttle``
is called inline in the handler (body not yet parsed when the dependency runs).

Env vars: ``LOCAL_LOGIN_THROTTLE_PER_IP_PER_MIN`` (default 20),
``LOCAL_LOGIN_THROTTLE_PER_ACCOUNT_PER_MIN`` (default 10),
``TRUST_PROXY_HEADERS`` (default true — uses X-Forwarded-For first hop).
"""

import threading
import time
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from fastapi import Depends, HTTPException, Request, status

from utils.config import Config
from utils.logger import get_logger

logger = get_logger(__name__)

_PER_IP_PER_MIN: int = Config.get_int_env_var(
    "LOCAL_LOGIN_THROTTLE_PER_IP_PER_MIN", default=20
)
_PER_ACCOUNT_PER_MIN: int = Config.get_int_env_var(
    "LOCAL_LOGIN_THROTTLE_PER_ACCOUNT_PER_MIN", default=10
)
_TRUST_PROXY: bool = Config.get_bool_env_var("TRUST_PROXY_HEADERS", default=True)

# Intentionally vague — does not reveal whether throttle is IP- or account-keyed.
ERR_TOO_MANY_REQUESTS = "Too many requests. Please try again later."

@dataclass
class ThrottleState:
    """Result of ``LoginThrottle.hit``.  ``remaining=-1`` means throttle is disabled."""

    allowed: bool
    remaining: int
    retry_after_seconds: int


@runtime_checkable
class LoginThrottle(Protocol):
    """Protocol for swappable throttle implementations (in-process or Redis-backed)."""

    def hit(self, key: str) -> ThrottleState:
        """Consume one slot for *key*.  Returns ``allowed=False`` when exhausted."""
        ...

    def reset(self, key: str) -> None:
        """Clear the counter for *key* (call after successful login)."""
        ...


class InProcessLoginThrottle:
    """Thread-safe in-memory fixed-window throttle (per-minute buckets).

    Stale entries are pruned lazily when tracked-key count exceeds
    ``cleanup_threshold``.  ``per_minute=0`` disables the throttle.
    """

    def __init__(self, per_minute: int = 20, cleanup_threshold: int = 500) -> None:
        self._per_minute = per_minute
        self._cleanup_threshold = cleanup_threshold
        self._counters: dict[str, dict[str, int]] = {}  # key -> {window_start, count}
        self._lock = threading.RLock()

    def hit(self, key: str) -> ThrottleState:
        if self._per_minute <= 0:
            return ThrottleState(allowed=True, remaining=-1, retry_after_seconds=0)

        current_time = time.time()
        current_minute = int(current_time // 60)
        window_reset_epoch = (current_minute + 1) * 60
        retry_after = max(0, int(window_reset_epoch - current_time))

        with self._lock:
            counter = self._counters.get(key)
            if counter is None:
                self._counters[key] = {"window_start": current_minute, "count": 0}
                counter = self._counters[key]
            elif counter["window_start"] < current_minute:
                counter["window_start"] = current_minute
                counter["count"] = 0

            self._cleanup_if_needed()

            if counter["count"] >= self._per_minute:
                return ThrottleState(
                    allowed=False,
                    remaining=0,
                    retry_after_seconds=retry_after,
                )

            counter["count"] += 1
            remaining = self._per_minute - counter["count"]
            return ThrottleState(
                allowed=True,
                remaining=remaining,
                retry_after_seconds=retry_after,
            )

    def reset(self, key: str) -> None:
        with self._lock:
            self._counters.pop(key, None)

    def _cleanup_if_needed(self) -> None:
        """Prune keys whose window is stale (called inside the lock)."""
        if len(self._counters) <= self._cleanup_threshold:
            return

        current_minute = int(time.time() // 60)
        stale = [
            k for k, c in self._counters.items()
            if c["window_start"] < current_minute - 1
        ]
        for k in stale:
            del self._counters[k]


login_throttle: LoginThrottle = InProcessLoginThrottle(per_minute=_PER_IP_PER_MIN, cleanup_threshold=500)
_account_throttle: LoginThrottle = InProcessLoginThrottle(per_minute=_PER_ACCOUNT_PER_MIN, cleanup_threshold=500)


def extract_client_ip(request: Request) -> Optional[str]:
    """Return the real client IP, preferring X-Forwarded-For when TRUST_PROXY_HEADERS is set."""
    if _TRUST_PROXY:
        forwarded_for: Optional[str] = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None



def hit_account_throttle(email: str) -> ThrottleState:
    """Consume one per-account throttle slot.  Call inline in the handler (body not yet
    parsed when the FastAPI dependency runs).
    """
    return _account_throttle.hit(f"account:{email}")


def reset_account_throttle(email: str) -> None:
    """Clear the per-account counter after a successful login."""
    _account_throttle.reset(f"account:{email}")


async def enforce_login_throttle(request: Request) -> None:
    """FastAPI dependency: enforce per-IP login throttle; raise HTTP 429 on exhaustion.

    ``Retry-After`` is set on ``HTTPException`` directly — setting it on an
    injected ``Response`` object does not work for exception responses.
    """
    ip = extract_client_ip(request)
    if ip is None:
        # Prefer availability over blocking when IP is indeterminate.
        logger.warning("auth:throttle_no_ip path=%s", request.url.path)
        return

    state = login_throttle.hit(f"ip:{ip}")
    if not state.allowed:
        logger.warning(
            "auth:throttle_ip_exceeded ip=%s path=%s retry_after=%s",
            ip,
            request.url.path,
            state.retry_after_seconds,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=ERR_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(state.retry_after_seconds)},
        )
