from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from models.agent import MarketplaceVisibility
from services.rate_limit_service import RateLimitService


def test_marketplace_agent_limit_uses_per_minute_counter_not_lifetime_count(
    monkeypatch,
):
    import routers.controls.rate_limit as rate_limit_module
    from routers.internal.marketplace import _apply_marketplace_agent_rate_limit

    monkeypatch.setattr(rate_limit_module, "rate_limit_service", RateLimitService())

    agent = SimpleNamespace(
        agent_id=11,
        app=SimpleNamespace(app_id=1, agent_rate_limit=1),
        marketplace_visibility=MarketplaceVisibility.PUBLIC,
        request_count=10000,
    )

    _apply_marketplace_agent_rate_limit(agent, {})

    with pytest.raises(HTTPException) as exc_info:
        _apply_marketplace_agent_rate_limit(agent, {})

    assert exc_info.value.status_code == 429


# ---------------------------------------------------------------------------
# _prepare_marketplace_chat — quota vs. agent rate-limit bucket interaction
#
# `_prepare_marketplace_chat` currently calls `_validate_marketplace_agent`
# (which consumes one slot from the agent's per-minute rate-limit bucket)
# BEFORE `_enforce_marketplace_quota`. This means a request that is ultimately
# rejected for an exhausted *monthly quota* still burns a slot from the
# *per-minute agent* budget, starving legitimate requests. These tests pin
# down the desired behavior: a quota rejection must not consume the agent
# bucket, and quota-available calls must consume exactly one request.
# ---------------------------------------------------------------------------


def _patch_marketplace_chat_dependencies(
    monkeypatch,
    agent,
    conversation,
    quota_exceeded: bool,
    quota: int = 5,
    current_usage: int = 5,
):
    import routers.internal.marketplace as marketplace_module

    monkeypatch.setattr(
        marketplace_module.ConversationService,
        "get_marketplace_conversation",
        staticmethod(lambda **kwargs: conversation),
    )
    monkeypatch.setattr(
        marketplace_module, "_get_agent_or_404", lambda db, agent_id: agent
    )
    monkeypatch.setattr(
        marketplace_module.UserService,
        "get_user_by_id",
        staticmethod(lambda db, user_id: SimpleNamespace(user_id=user_id)),
    )
    monkeypatch.setattr(
        marketplace_module.MarketplaceQuotaService,
        "is_user_exempt",
        staticmethod(lambda user: False),
    )
    monkeypatch.setattr(
        marketplace_module.SystemSettingsService,
        "get_setting",
        lambda self, name: str(quota),
    )
    monkeypatch.setattr(
        marketplace_module.MarketplaceQuotaService,
        "check_quota_exceeded",
        staticmethod(lambda user_id, db, quota_arg: quota_exceeded),
    )
    monkeypatch.setattr(
        marketplace_module.MarketplaceQuotaService,
        "get_current_month_usage",
        staticmethod(lambda user_id, db: current_usage),
    )
    return marketplace_module


class TestPrepareMarketplaceChatQuotaVsRateLimit:
    def test_exhausted_quota_does_not_consume_agent_rate_limit_bucket(
        self, monkeypatch
    ):
        import routers.controls.rate_limit as rate_limit_module

        fresh_service = RateLimitService()
        monkeypatch.setattr(rate_limit_module, "rate_limit_service", fresh_service)

        agent = SimpleNamespace(
            agent_id=11,
            app=SimpleNamespace(app_id=1, agent_rate_limit=1),
            marketplace_visibility=MarketplaceVisibility.PUBLIC,
        )
        conversation = SimpleNamespace(agent_id=11)

        marketplace_module = _patch_marketplace_chat_dependencies(
            monkeypatch, agent, conversation, quota_exceeded=True
        )

        with pytest.raises(HTTPException) as exc_info:
            marketplace_module._prepare_marketplace_chat(
                conversation_id=1,
                user_id=42,
                db=MagicMock(),
                response_headers={},
            )
        assert exc_info.value.status_code == 429

        # The agent only allows 1 request/minute. If the quota-rejected call
        # above had NOT consumed that single slot, this direct check should
        # still succeed (remaining == 0 after consuming it now, exceeded is
        # False). If the bug is present, the slot was already burned by the
        # rejected call and this check comes back exceeded.
        state = fresh_service.check_and_consume_for_agent(
            app_id=1, agent_id=11, max_per_minute=1
        )
        assert state.exceeded is False
        assert state.remaining == 0

    def test_available_quota_consumes_exactly_one_agent_request(self, monkeypatch):
        import routers.controls.rate_limit as rate_limit_module

        fresh_service = RateLimitService()
        monkeypatch.setattr(rate_limit_module, "rate_limit_service", fresh_service)

        agent = SimpleNamespace(
            agent_id=12,
            app=SimpleNamespace(app_id=1, agent_rate_limit=5),
            marketplace_visibility=MarketplaceVisibility.PUBLIC,
        )
        conversation = SimpleNamespace(agent_id=12)

        marketplace_module = _patch_marketplace_chat_dependencies(
            monkeypatch, agent, conversation, quota_exceeded=False
        )

        result_conversation, result_agent = marketplace_module._prepare_marketplace_chat(
            conversation_id=1,
            user_id=42,
            db=MagicMock(),
            response_headers={},
        )
        assert result_conversation is conversation
        assert result_agent is agent

        # Exactly one request should have been consumed from the 5/minute
        # budget by the call above.
        state = fresh_service.check_and_consume_for_agent(
            app_id=1, agent_id=12, max_per_minute=5
        )
        assert state.remaining == 3  # 5 - 1 (prepare call) - 1 (this check)

    def test_missing_agent_still_raises_404_before_quota_check(self, monkeypatch):
        import routers.internal.marketplace as marketplace_module

        conversation = SimpleNamespace(agent_id=999)
        monkeypatch.setattr(
            marketplace_module.ConversationService,
            "get_marketplace_conversation",
            staticmethod(lambda **kwargs: conversation),
        )
        mock_agent_service_cls = MagicMock()
        mock_agent_service_cls.return_value.get_agent.return_value = None
        monkeypatch.setattr(marketplace_module, "AgentService", mock_agent_service_cls)

        quota_calls = []
        monkeypatch.setattr(
            marketplace_module.MarketplaceQuotaService,
            "check_quota_exceeded",
            staticmethod(
                lambda user_id, db, quota: quota_calls.append(1) or False
            ),
        )

        with pytest.raises(HTTPException) as exc_info:
            marketplace_module._prepare_marketplace_chat(
                conversation_id=1,
                user_id=42,
                db=MagicMock(),
                response_headers={},
            )

        assert exc_info.value.status_code == 404
        assert quota_calls == []

    def test_unpublished_agent_still_raises_403_before_quota_check(
        self, monkeypatch
    ):
        import routers.internal.marketplace as marketplace_module

        agent = SimpleNamespace(
            agent_id=13,
            app=SimpleNamespace(app_id=1, agent_rate_limit=5),
            marketplace_visibility=MarketplaceVisibility.UNPUBLISHED,
        )
        conversation = SimpleNamespace(agent_id=13)

        monkeypatch.setattr(
            marketplace_module.ConversationService,
            "get_marketplace_conversation",
            staticmethod(lambda **kwargs: conversation),
        )
        monkeypatch.setattr(
            marketplace_module, "_get_agent_or_404", lambda db, agent_id: agent
        )

        quota_calls = []
        monkeypatch.setattr(
            marketplace_module.MarketplaceQuotaService,
            "check_quota_exceeded",
            staticmethod(
                lambda user_id, db, quota: quota_calls.append(1) or False
            ),
        )

        with pytest.raises(HTTPException) as exc_info:
            marketplace_module._prepare_marketplace_chat(
                conversation_id=1,
                user_id=42,
                db=MagicMock(),
                response_headers={},
            )

        assert exc_info.value.status_code == 403
        assert quota_calls == []
