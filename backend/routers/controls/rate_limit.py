"""
Rate limiting helpers for external agent execution endpoints.
Enforces per-agent execution limits using in-memory counters.
"""
import time

from fastapi import HTTPException, status
from typing import MutableMapping

from models.app import App
from services.rate_limit_service import rate_limit_service
from utils.logger import get_logger

logger = get_logger(__name__)


def apply_agent_rate_limit(
    app: App,
    agent_id: int,
    response_headers: MutableMapping[str, str],
) -> None:
    """Apply the app's per-agent execution limit and set standard rate-limit headers."""
    rate_limit = app.agent_rate_limit or 0

    if rate_limit <= 0:
        response_headers["X-RateLimit-Limit"] = "0"
        response_headers["X-RateLimit-Remaining"] = "-1"
        response_headers["X-RateLimit-Reset"] = str(int(time.time()) + 60)
        return

    state = rate_limit_service.check_and_consume_for_agent(
        app.app_id, agent_id, rate_limit
    )
    response_headers["X-RateLimit-Limit"] = str(state.limit)
    response_headers["X-RateLimit-Remaining"] = str(max(0, state.remaining))
    response_headers["X-RateLimit-Reset"] = str(state.reset_epoch)

    if state.exceeded:
        retry_after = max(1, state.reset_epoch - int(time.time()))
        logger.info(
            "Rate limit exceeded for app %s agent %s: %s requests per minute",
            app.app_id,
            agent_id,
            rate_limit,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum {rate_limit} requests per minute allowed.",
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(state.limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(state.reset_epoch),
            },
        )

    logger.debug(
        "Rate limit check passed for app %s agent %s: %s remaining",
        app.app_id,
        agent_id,
        state.remaining,
    )
