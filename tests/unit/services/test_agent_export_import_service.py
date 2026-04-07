from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from schemas.export_schemas import (
    AgentExportFileSchema,
    ExportA2AAuthConfigSchema,
    ExportA2AConfigSchema,
    ExportAgentSchema,
    ExportMetadataSchema,
)
from schemas.import_schemas import ConflictMode
from services.agent_export_service import AgentExportService
from services.agent_import_service import AgentImportService
from services.full_app_export_service import FullAppExportService


def test_export_agent_includes_sanitized_a2a_config():
    session = MagicMock()
    service = AgentExportService(session)
    agent = MagicMock()
    agent.agent_id = 7
    agent.app_id = 3
    agent.type = "agent"
    agent.name = "Remote Search"
    agent.description = "Searches remotely"
    agent.system_prompt = ""
    agent.prompt_template = ""
    agent.ai_service = None
    agent.silo = None
    agent.output_parser = None
    agent.service_id = None
    agent.silo_id = None
    agent.output_parser_id = None
    agent.has_memory = False
    agent.memory_max_messages = 20
    agent.memory_max_tokens = None
    agent.memory_summarize_threshold = 10
    agent.temperature = 0.7
    agent.a2a_config = SimpleNamespace(
        card_url="https://remote.example.com/.well-known/agent-card.json",
        remote_agent_id="https://remote.example.com",
        remote_skill_id="skill-1",
        remote_skill_name="Search",
        auth_config={
            "scheme_name": "remoteApiKey",
            "scheme_type": "apiKey",
            "api_key": "super-secret",
        },
        remote_agent_metadata={"name": "Remote Agent"},
        remote_skill_metadata={"id": "skill-1", "name": "Search"},
        sync_status="synced",
        health_status="healthy",
        last_successful_refresh_at=None,
        last_refresh_attempt_at=None,
        last_refresh_error=None,
        documentation_url=None,
        icon_url=None,
    )

    with patch(
        "services.agent_export_service.AgentRepository.get_by_id",
        return_value=agent,
    ), patch(
        "services.agent_export_service.AgentRepository.get_agent_tool_associations",
        return_value=[],
    ), patch(
        "services.agent_export_service.AgentRepository.get_agent_mcp_associations",
        return_value=[],
    ):
        export_data = service.export_agent(agent.agent_id, agent.app_id)

    assert export_data.agent.source_type == "a2a"
    assert export_data.agent.a2a_config is not None
    assert export_data.agent.a2a_config.remote_skill_id == "skill-1"
    assert export_data.agent.a2a_config.auth_config is not None
    assert export_data.agent.a2a_config.auth_config.api_key is None


def test_import_agent_restores_a2a_config_with_pending_health():
    session = MagicMock()
    added_objects = []

    def add_side_effect(obj):
        added_objects.append(obj)

    def flush_side_effect():
        for obj in added_objects:
            if getattr(obj, "__tablename__", None) == "Agent" and getattr(obj, "agent_id", None) is None:
                obj.agent_id = 101

    session.add.side_effect = add_side_effect
    session.flush.side_effect = flush_side_effect
    session.query.return_value.filter.return_value.first.return_value = None

    service = AgentImportService(session)
    export_data = AgentExportFileSchema(
        metadata=ExportMetadataSchema(),
        agent=ExportAgentSchema(
            name="Imported Remote Search",
            description="Searches through a remote A2A agent",
            system_prompt="",
            prompt_template="",
            has_memory=False,
            memory_max_messages=20,
            memory_max_tokens=None,
            memory_summarize_threshold=10,
            temperature=0.7,
            source_type="a2a",
            a2a_config=ExportA2AConfigSchema(
                card_url="https://remote.example.com/.well-known/agent-card.json",
                remote_agent_id="https://remote.example.com",
                remote_skill_id="skill-1",
                remote_skill_name="Search",
                auth_config=ExportA2AAuthConfigSchema(
                    scheme_name="remoteApiKey",
                    scheme_type="apiKey",
                ),
                remote_agent_metadata={"name": "Remote Agent"},
                remote_skill_metadata={"id": "skill-1", "name": "Search"},
                sync_status="synced",
                health_status="healthy",
            ),
        ),
    )

    with patch.object(service, "get_by_name_and_app", return_value=None), patch.object(
        service, "_update_agent_tools"
    ) as mock_tools, patch.object(service, "_update_agent_mcps") as mock_mcps:
        summary = service.import_agent(export_data, app_id=9)

    mock_tools.assert_called_once()
    mock_mcps.assert_called_once()
    session.commit.assert_called_once()
    assert summary.created is True
    assert "Refresh the imported A2A agent metadata" in summary.next_steps[0]

    created_agent = next(obj for obj in added_objects if getattr(obj, "__tablename__", None) == "Agent")
    created_a2a = next(obj for obj in added_objects if getattr(obj, "__tablename__", None) == "A2AAgent")

    assert created_agent.service_id is None
    assert created_a2a.agent_id == 101
    assert created_a2a.remote_skill_id == "skill-1"
    assert created_a2a.health_status == "pending"
    assert created_a2a.last_successful_refresh_at is None
    assert created_a2a.last_refresh_attempt_at is None
    assert "Refresh the remote A2A agent card" in created_a2a.last_refresh_error


def test_import_agent_override_rejects_local_to_a2a_conversion():
    session = MagicMock()
    service = AgentImportService(session)
    existing_agent = MagicMock()
    existing_agent.a2a_config = None

    export_data = AgentExportFileSchema(
        metadata=ExportMetadataSchema(),
        agent=ExportAgentSchema(
            name="Existing Agent",
            source_type="a2a",
            a2a_config=ExportA2AConfigSchema(
                card_url="https://remote.example.com/.well-known/agent-card.json",
                remote_agent_id="https://remote.example.com",
                remote_skill_id="skill-1",
                remote_skill_name="Search",
                remote_agent_metadata={"name": "Remote Agent"},
                remote_skill_metadata={"id": "skill-1", "name": "Search"},
                sync_status="synced",
                health_status="healthy",
            ),
        ),
    )

    with patch.object(service, "get_by_name_and_app", return_value=existing_agent):
        with pytest.raises(
            ValueError,
            match="Changing an agent between local and A2A sources is not supported yet",
        ):
            service.import_agent(
                export_data,
                app_id=9,
                conflict_mode=ConflictMode.OVERRIDE,
            )


def test_full_app_export_keeps_a2a_agents_without_local_ai_service():
    session = MagicMock()
    service = FullAppExportService(session)
    invalid_local_agent = MagicMock(agent_id=1, service_id=None, a2a_config=None)
    a2a_agent = MagicMock(agent_id=2, service_id=None, a2a_config=object())

    service.app_repo.get_agents_by_app_id = MagicMock(
        return_value=[invalid_local_agent, a2a_agent]
    )
    service.agent_export.export_agent = MagicMock(
        return_value=AgentExportFileSchema(
            metadata=ExportMetadataSchema(),
            agent=ExportAgentSchema(
                name="Remote Search",
                source_type="a2a",
                a2a_config=ExportA2AConfigSchema(
                    card_url="https://remote.example.com/.well-known/agent-card.json",
                    remote_agent_id="https://remote.example.com",
                    remote_skill_id="skill-1",
                    remote_skill_name="Search",
                    remote_agent_metadata={"name": "Remote Agent"},
                    remote_skill_metadata={"id": "skill-1", "name": "Search"},
                    sync_status="synced",
                    health_status="healthy",
                ),
            ),
        )
    )

    exported = service._export_all_agents(app_id=3)

    assert len(exported) == 1
    assert exported[0].source_type == "a2a"
    service.agent_export.export_agent.assert_called_once_with(
        a2a_agent.agent_id,
        3,
        include_ai_service=True,
        include_silo=True,
        include_output_parser=True,
        include_mcp_configs=True,
        include_agent_tools=True,
    )
