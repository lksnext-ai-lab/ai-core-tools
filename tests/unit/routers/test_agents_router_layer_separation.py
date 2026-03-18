from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from routers.internal.agents import _get_agent_or_404, _get_user_from_auth_context


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
