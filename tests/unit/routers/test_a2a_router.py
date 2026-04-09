from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request

from routers import a2a as a2a_module


class TestA2ARouter:
    @pytest.mark.asyncio
    async def test_get_agent_card_by_id_uses_dynamic_application(self, mocker):
        app = MagicMock(app_id=7, slug="workspace")
        agent = MagicMock(agent_id=11)
        request = MagicMock(spec=Request)

        mocker.patch.object(
            a2a_module,
            "_resolve_enabled_agent_by_app_id",
            return_value=(app, agent),
        )

        fake_application = MagicMock()
        fake_application._handle_get_agent_card = AsyncMock(return_value={"card": "ok"})
        mocker.patch.object(
            a2a_module,
            "_build_application",
            return_value=fake_application,
        )

        result = await a2a_module.get_agent_card_by_id(
            app_id=7,
            agent_id=11,
            request=request,
            db=MagicMock(),
        )

        assert result == {"card": "ok"}
        fake_application._handle_get_agent_card.assert_awaited_once_with(request)

    @pytest.mark.asyncio
    async def test_rpc_by_id_validates_target_and_delegates(self, mocker):
        app = MagicMock(app_id=7, slug="workspace")
        agent = MagicMock(agent_id=11)
        request = MagicMock(spec=Request)
        response = MagicMock()

        mocker.patch.object(
            a2a_module,
            "_resolve_enabled_agent_by_app_id",
            return_value=(app, agent),
        )
        mock_handle = mocker.patch.object(
            a2a_module,
            "_handle_rpc_request",
            new=AsyncMock(return_value={"jsonrpc": "2.0"}),
        )

        result = await a2a_module.rpc_by_id(
            app_id=7,
            agent_id=11,
            request=request,
            response=response,
            api_key="test-key",
            db=MagicMock(),
        )

        assert result == {"jsonrpc": "2.0"}
        mock_handle.assert_awaited_once()
