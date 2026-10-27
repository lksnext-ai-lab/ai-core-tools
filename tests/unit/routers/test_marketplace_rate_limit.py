from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from models.agent import MarketplaceVisibility
from services.rate_limit_service import RateLimitService


def test_marketplace_agent_limit_uses_per_minute_counter_not_lifetime_count(
    monkeypatch,
):
    import routers.controls.rate_limit as rate_limit_module
    from routers.internal.marketplace import _validate_marketplace_agent

    monkeypatch.setattr(rate_limit_module, "rate_limit_service", RateLimitService())

    agent = SimpleNamespace(
        agent_id=11,
        app=SimpleNamespace(app_id=1, agent_rate_limit=1),
        marketplace_visibility=MarketplaceVisibility.PUBLIC,
        request_count=10000,
    )

    _validate_marketplace_agent(agent, {})

    with pytest.raises(HTTPException) as exc_info:
        _validate_marketplace_agent(agent, {})

    assert exc_info.value.status_code == 429
