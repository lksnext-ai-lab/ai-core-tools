from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from routers.internal.agents import (
    _get_agent_or_404,
    _get_user_from_auth_context,
    refresh_a2a_card,
)


def test_get_agent_or_404_returns_agent_when_found():
    db = MagicMock()
    agent = MagicMock()

    with patch("routers.internal.agents.AgentService.get_agent", return_value=agent) as mock_get_agent:
        result = _get_agent_or_404(db, 12)

    assert result is agent
    mock_get_agent.assert_called_once_with(db, 12)


def test_get_agent_or_404_raises_when_missing():
    db = MagicMock()

    with patch("routers.internal.agents.AgentService.get_agent", return_value=None) as mock_get_agent:
        with pytest.raises(HTTPException) as exc:
            _get_agent_or_404(db, 99)

    assert exc.value.status_code == 404
    assert exc.value.detail == "Agent not found"
    mock_get_agent.assert_called_once_with(db, 99)


def test_get_agent_or_404_returns_agent_when_app_id_matches():
    db = MagicMock()
    agent = MagicMock()
    agent.app_id = 5

    with patch("routers.internal.agents.AgentService.get_agent", return_value=agent):
        result = _get_agent_or_404(db, 12, app_id=5)

    assert result is agent


def test_get_agent_or_404_raises_when_app_id_mismatch():
    db = MagicMock()
    agent = MagicMock()
    agent.app_id = 5

    with patch("routers.internal.agents.AgentService.get_agent", return_value=agent):
        with pytest.raises(HTTPException) as exc:
            _get_agent_or_404(db, 12, app_id=999)

    assert exc.value.status_code == 404
    assert exc.value.detail == "Agent not found"


def test_get_agent_or_404_skips_app_check_when_app_id_none():
    """When app_id is None (default), no ownership check is performed."""
    db = MagicMock()
    agent = MagicMock()
    agent.app_id = 5

    with patch("routers.internal.agents.AgentService.get_agent", return_value=agent):
        result = _get_agent_or_404(db, 12)

    assert result is agent


def test_get_user_from_auth_context_delegates_to_user_service():
    db = MagicMock()
    user = MagicMock()
    auth_context = SimpleNamespace(identity=SimpleNamespace(id="7"))

    with patch("routers.internal.agents.UserService.get_user_by_id", return_value=user) as mock_get_user:
        result = _get_user_from_auth_context(db, auth_context)

    assert result is user
    mock_get_user.assert_called_once_with(db, 7)


@pytest.mark.asyncio
async def test_refresh_a2a_card_delegates_to_service_and_returns_agent_detail():
    db = MagicMock()
    auth_context = SimpleNamespace(identity=SimpleNamespace(id="7"))
    agent = MagicMock()
    agent.a2a_config = MagicMock()
    refreshed_detail = {"agent_id": 12, "source_type": "a2a"}
    agent_service = MagicMock()
    agent_service.get_agent_detail.return_value = refreshed_detail

    with patch("routers.internal.agents._get_agent_or_404", return_value=agent) as mock_get_agent:
        with patch("routers.internal.agents.A2AService.refresh_card", new=AsyncMock(return_value=agent.a2a_config)) as mock_refresh:
            result = await refresh_a2a_card(
                app_id=5,
                agent_id=12,
                auth_context=auth_context,
                role=MagicMock(),
                db=db,
                agent_service=agent_service,
            )

    assert result == refreshed_detail
    mock_get_agent.assert_called_once_with(db, 12, 5)
    mock_refresh.assert_awaited_once_with(agent.a2a_config, db)
    agent_service.get_agent_detail.assert_called_once_with(db, 5, 12)


@pytest.mark.asyncio
async def test_refresh_a2a_card_rejects_non_a2a_agents():
    db = MagicMock()
    auth_context = SimpleNamespace(identity=SimpleNamespace(id="7"))
    agent = MagicMock()
    agent.a2a_config = None

    with patch("routers.internal.agents._get_agent_or_404", return_value=agent):
        with pytest.raises(HTTPException) as exc:
            await refresh_a2a_card(
                app_id=5,
                agent_id=12,
                auth_context=auth_context,
                role=MagicMock(),
                db=db,
                agent_service=MagicMock(),
            )

    assert exc.value.status_code == 400
    assert "Only imported A2A agents" in exc.value.detail
