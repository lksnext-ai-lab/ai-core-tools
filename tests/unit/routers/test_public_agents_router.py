"""
Tests for public API agents router.
Covers: list, get, create, update, delete agent endpoints.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, status

from routers.public.v1 import agents as agents_module
from routers.public.v1 import auth as auth_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_agent(agent_id=1, app_id=1, name="Test Agent", agent_type="agent"):
    agent = MagicMock()
    agent.agent_id = agent_id
    agent.app_id = app_id
    agent.name = name
    agent.type = agent_type
    agent.description = "desc"
    agent.status = "active"
    agent.is_tool = False
    agent.has_memory = False
    agent.create_date = None
    agent.request_count = 0
    agent.service_id = None
    agent.silo_id = None
    agent.output_parser_id = None
    agent.memory_max_messages = 20
    agent.memory_max_tokens = 4000
    agent.memory_summarize_threshold = 4000
    agent.system_prompt = ""
    agent.prompt_template = ""
    agent.temperature = 0.7
    return agent


def _patch_auth(mocker):
    """Patch validate_api_key_for_app to be a no-op."""
    return mocker.patch.object(
        agents_module, "validate_api_key_for_app", return_value=None
    )


def _patch_agent_service(mocker):
    """Patch AgentService and return the mock instance."""
    mock_cls = mocker.patch.object(agents_module, "AgentService")
    return mock_cls.return_value


# ---------------------------------------------------------------------------
# TestListAgents
# ---------------------------------------------------------------------------

def _patch_schemas(mocker):
    """Patch Pydantic schema validation to avoid MagicMock validation errors."""
    mocker.patch(
        "routers.public.v1.agents.PublicAgentSchema.model_validate",
        side_effect=lambda a: MagicMock(agent_id=a.agent_id),
    )
    mocker.patch(
        "routers.public.v1.agents.PublicAgentDetailSchema.model_validate",
        side_effect=lambda a: MagicMock(agent_id=a.agent_id),
    )
    mock_response = mocker.patch("routers.public.v1.agents.PublicAgentResponseSchema")
    mock_response.side_effect = lambda **kwargs: MagicMock(**kwargs)
    mock_list = mocker.patch("routers.public.v1.agents.PublicAgentsResponseSchema")
    mock_list.side_effect = lambda **kwargs: MagicMock(**kwargs)


class TestListAgents:
    @pytest.mark.asyncio
    async def test_list_agents_happy_path(self, mocker):
        _patch_auth(mocker)
        _patch_schemas(mocker)
        svc = _patch_agent_service(mocker)
        agents = [_mock_agent(agent_id=1), _mock_agent(agent_id=2)]
        svc.get_agents.return_value = agents

        result = await agents_module.list_agents(app_id=1, api_key="key", db=MagicMock())
        assert len(result.agents) == 2

    @pytest.mark.asyncio
    async def test_list_agents_empty(self, mocker):
        _patch_auth(mocker)
        svc = _patch_agent_service(mocker)
        svc.get_agents.return_value = []

        result = await agents_module.list_agents(app_id=1, api_key="key", db=MagicMock())
        assert result.agents == []

    @pytest.mark.asyncio
    async def test_list_agents_invalid_api_key(self, mocker):
        mocker.patch.object(
            agents_module,
            "validate_api_key_for_app",
            side_effect=HTTPException(status_code=401, detail="Invalid"),
        )

        with pytest.raises(HTTPException) as exc_info:
            await agents_module.list_agents(app_id=1, api_key="bad", db=MagicMock())
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# TestGetAgent
# ---------------------------------------------------------------------------

class TestGetAgent:
    @pytest.mark.asyncio
    async def test_get_agent_happy_path(self, mocker):
        _patch_auth(mocker)
        _patch_schemas(mocker)
        agent = _mock_agent()
        mocker.patch.object(
            agents_module, "validate_agent_ownership", return_value=agent
        )

        result = await agents_module.get_agent(app_id=1, agent_id=1, api_key="key", db=MagicMock())
        assert result.agent.agent_id == 1

    @pytest.mark.asyncio
    async def test_get_agent_not_found(self, mocker):
        _patch_auth(mocker)
        mocker.patch.object(
            agents_module,
            "validate_agent_ownership",
            side_effect=HTTPException(status_code=404, detail="Agent not found"),
        )

        with pytest.raises(HTTPException) as exc_info:
            await agents_module.get_agent(app_id=1, agent_id=999, api_key="key", db=MagicMock())
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_agent_wrong_app(self, mocker):
        _patch_auth(mocker)
        mocker.patch.object(
            agents_module,
            "validate_agent_ownership",
            side_effect=HTTPException(status_code=404, detail="Agent not found"),
        )

        with pytest.raises(HTTPException) as exc_info:
            await agents_module.get_agent(app_id=2, agent_id=1, api_key="key", db=MagicMock())
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# TestCreateAgent
# ---------------------------------------------------------------------------

class TestCreateAgent:
    @pytest.mark.asyncio
    async def test_create_agent_happy_path(self, mocker):
        _patch_auth(mocker)
        _patch_schemas(mocker)
        mocker.patch.object(agents_module, "_validate_referenced_resources")
        svc = _patch_agent_service(mocker)
        svc.create_or_update_agent.return_value = 10
        svc.get_agent.return_value = _mock_agent(agent_id=10)

        agent_data = MagicMock()
        agent_data.model_dump.return_value = {"name": "New Agent", "type": "agent"}

        result = await agents_module.create_agent(
            app_id=1, agent_data=agent_data, api_key="key", db=MagicMock()
        )
        assert result.agent.agent_id == 10

    @pytest.mark.asyncio
    async def test_create_agent_error_does_not_leak(self, mocker):
        _patch_auth(mocker)
        mocker.patch.object(agents_module, "_validate_referenced_resources")
        svc = _patch_agent_service(mocker)
        svc.create_or_update_agent.side_effect = RuntimeError("SQL syntax error near...")

        agent_data = MagicMock()
        agent_data.model_dump.return_value = {"name": "Bad", "type": "agent"}

        with pytest.raises(HTTPException) as exc_info:
            await agents_module.create_agent(
                app_id=1, agent_data=agent_data, api_key="key", db=MagicMock()
            )
        assert exc_info.value.status_code == 400
        assert "SQL" not in exc_info.value.detail
        assert exc_info.value.detail == "Failed to create agent"

    @pytest.mark.asyncio
    async def test_create_agent_idor_service_id_blocked(self, mocker):
        _patch_auth(mocker)
        mocker.patch.object(
            agents_module,
            "_validate_referenced_resources",
            side_effect=HTTPException(
                status_code=400, detail="Invalid service_id: not found in this app"
            ),
        )
        svc = _patch_agent_service(mocker)

        agent_data = MagicMock()
        agent_data.model_dump.return_value = {
            "name": "Agent",
            "type": "agent",
            "service_id": 999,
        }

        with pytest.raises(HTTPException) as exc_info:
            await agents_module.create_agent(
                app_id=1, agent_data=agent_data, api_key="key", db=MagicMock()
            )
        assert exc_info.value.status_code == 400
        assert "service_id" in exc_info.value.detail


# ---------------------------------------------------------------------------
# TestUpdateAgent
# ---------------------------------------------------------------------------

class TestUpdateAgent:
    @pytest.mark.asyncio
    async def test_update_agent_happy_path(self, mocker):
        _patch_auth(mocker)
        _patch_schemas(mocker)
        existing = _mock_agent()
        mocker.patch.object(
            agents_module, "validate_agent_ownership", return_value=existing
        )
        mocker.patch.object(agents_module, "_validate_referenced_resources")
        svc = _patch_agent_service(mocker)
        svc.create_or_update_agent.return_value = 1
        svc.get_agent.return_value = existing

        agent_data = MagicMock()
        agent_data.model_dump.return_value = {"name": "Updated"}

        result = await agents_module.update_agent(
            app_id=1, agent_id=1, agent_data=agent_data, api_key="key", db=MagicMock()
        )
        assert result.agent.agent_id == 1

    @pytest.mark.asyncio
    async def test_update_agent_not_found(self, mocker):
        _patch_auth(mocker)
        mocker.patch.object(
            agents_module,
            "validate_agent_ownership",
            side_effect=HTTPException(status_code=404, detail="Agent not found"),
        )

        agent_data = MagicMock()
        agent_data.model_dump.return_value = {"name": "Updated"}

        with pytest.raises(HTTPException) as exc_info:
            await agents_module.update_agent(
                app_id=1, agent_id=999, agent_data=agent_data, api_key="key", db=MagicMock()
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_agent_error_does_not_leak(self, mocker):
        _patch_auth(mocker)
        mocker.patch.object(
            agents_module, "validate_agent_ownership", return_value=_mock_agent()
        )
        mocker.patch.object(agents_module, "_validate_referenced_resources")
        svc = _patch_agent_service(mocker)
        svc.create_or_update_agent.side_effect = RuntimeError("Internal DB error")

        agent_data = MagicMock()
        agent_data.model_dump.return_value = {"name": "Fail"}

        with pytest.raises(HTTPException) as exc_info:
            await agents_module.update_agent(
                app_id=1, agent_id=1, agent_data=agent_data, api_key="key", db=MagicMock()
            )
        assert exc_info.value.status_code == 400
        assert "Internal DB" not in exc_info.value.detail


# ---------------------------------------------------------------------------
# TestDeleteAgent
# ---------------------------------------------------------------------------

class TestDeleteAgent:
    @pytest.mark.asyncio
    async def test_delete_agent_happy_path(self, mocker):
        _patch_auth(mocker)
        mocker.patch.object(
            agents_module, "validate_agent_ownership", return_value=_mock_agent()
        )
        svc = _patch_agent_service(mocker)
        svc.delete_agent.return_value = True

        result = await agents_module.delete_agent(
            app_id=1, agent_id=1, api_key="key", db=MagicMock()
        )
        assert result is None  # 204 No Content

    @pytest.mark.asyncio
    async def test_delete_agent_not_found(self, mocker):
        _patch_auth(mocker)
        mocker.patch.object(
            agents_module,
            "validate_agent_ownership",
            side_effect=HTTPException(status_code=404, detail="Agent not found"),
        )

        with pytest.raises(HTTPException) as exc_info:
            await agents_module.delete_agent(
                app_id=1, agent_id=999, api_key="key", db=MagicMock()
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_agent_failure(self, mocker):
        _patch_auth(mocker)
        mocker.patch.object(
            agents_module, "validate_agent_ownership", return_value=_mock_agent()
        )
        svc = _patch_agent_service(mocker)
        svc.delete_agent.return_value = False

        with pytest.raises(HTTPException) as exc_info:
            await agents_module.delete_agent(
                app_id=1, agent_id=1, api_key="key", db=MagicMock()
            )
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# TestValidateReferencedResources
# ---------------------------------------------------------------------------

class TestValidateReferencedResources:
    def test_valid_service_id(self, mocker):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = MagicMock()

        # Should not raise
        agents_module._validate_referenced_resources(
            db, {"service_id": 1}, app_id=1
        )

    def test_invalid_service_id(self, mocker):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            agents_module._validate_referenced_resources(
                db, {"service_id": 999}, app_id=1
            )
        assert exc_info.value.status_code == 400
        assert "service_id" in exc_info.value.detail

    def test_no_references_is_fine(self, mocker):
        db = MagicMock()
        # Should not raise or call db
        agents_module._validate_referenced_resources(db, {"name": "test"}, app_id=1)
