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


def test_get_user_from_auth_context_delegates_to_user_service():
    db = MagicMock()
    user = MagicMock()
    auth_context = SimpleNamespace(identity=SimpleNamespace(id="7"))

    with patch("routers.internal.agents.UserService.get_user_by_id", return_value=user) as mock_get_user:
        result = _get_user_from_auth_context(db, auth_context)

    assert result is user
    mock_get_user.assert_called_once_with(db, 7)
