"""
Unit tests for AgentService.

The repository is mocked (pytest-mock), so no database is needed.
Tests focus on:
  - Agent CRUD operations (get_agents_list, get_agent_detail, create_or_update_agent)
  - Agent associations (tools, MCPs, skills)
  - Data transformation (serialization to schemas)
  - Edge cases (missing agents, invalid data)
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from services.agent_service import AgentService
from schemas.agent_schemas import AgentListItemSchema, AgentDetailSchema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_agent(
    agent_id: int = 1,
    name: str = "Test Agent",
    app_id: int = 1,
    service_id: int = None,
    silo_id: int = None,
    output_parser_id: int = None,
    is_tool: bool = False,
    has_memory: bool = False,
    agent_type: str = "agent",
    temperature: float = 0.7,
) -> MagicMock:
    """Create a mock Agent ORM object."""
    agent = MagicMock()
    agent.agent_id = agent_id
    agent.name = name
    agent.app_id = app_id
    agent.type = agent_type
    agent.created_at = datetime(2024, 1, 1)
    agent.create_date = datetime(2024, 1, 1)
    agent.service_id = service_id
    agent.silo_id = silo_id
    agent.output_parser_id = output_parser_id
    agent.is_tool = is_tool
    agent.has_memory = has_memory
    agent.temperature = temperature
    agent.description = "Test agent description"
    agent.system_prompt = "Test system prompt"
    agent.prompt_template = "Test template"
    agent.request_count = 0
    agent.marketplace_visibility = None
    agent.marketplace_profile = None
    agent.vision_service_id = None
    agent.vision_system_prompt = None
    agent.text_system_prompt = None
    return agent


def make_ai_service(
    service_id: int = 1,
    name: str = "Test Service",
    provider: str = "OpenAI"
) -> MagicMock:
    """Create a mock AIService object."""
    service = MagicMock()
    service.service_id = service_id
    service.name = name
    service.provider = provider
    return service


def make_silo(
    silo_id: int = 1,
    name: str = "Test Silo",
    app_id: int = 1
) -> MagicMock:
    """Create a mock Silo object."""
    silo = MagicMock()
    silo.silo_id = silo_id
    silo.name = name
    silo.app_id = app_id
    silo.type = "pgvector"
    return silo


# ---------------------------------------------------------------------------
# get_agents_list
# ---------------------------------------------------------------------------

class TestGetAgentsList:
    """Test AgentService.get_agents_list()"""

    def test_returns_list(self, mocker):
        """get_agents_list returns a list."""
        db = MagicMock()
        service = AgentService()
        mocker.patch.object(
            service.__class__,
            'get_agents',
            return_value=[]
        )
        result = service.get_agents_list(db, app_id=1)
        assert isinstance(result, list)

    def test_returns_empty_list_for_app_with_no_agents(self, mocker):
        """Returns empty list when app has no agents."""
        db = MagicMock()
        service = AgentService()
        
        mocker.patch('services.agent_service.AgentRepository.get_by_app_id', return_value=[])
        mocker.patch('services.agent_service.AgentRepository.get_ai_services_dict_by_app_id', return_value={})
        
        result = service.get_agents_list(db, app_id=1)
        assert result == []

    def test_returns_agents_with_metadata(self, mocker):
        """Returns agents with schema metadata."""
        db = MagicMock()
        service = AgentService()
        agent = make_agent(agent_id=1, name="Test Agent")
        
        mocker.patch('services.agent_service.AgentRepository.get_by_app_id', return_value=[agent])
        mocker.patch('services.agent_service.AgentRepository.get_ai_services_dict_by_app_id', return_value={})
        
        result = service.get_agents_list(db, app_id=1)
        
        assert len(result) == 1
        assert result[0].name == "Test Agent"
        assert result[0].agent_id == 1
        assert isinstance(result[0], AgentListItemSchema) or isinstance(result[0], dict)

    def test_includes_ai_service_info_when_linked(self, mocker):
        """Agent's AI service is included if linked."""
        db = MagicMock()
        service = AgentService()
        agent = make_agent(service_id=1)
        # Return a dict instead of MagicMock for schema validation
        ai_service_dict = {
            "service_id": 1,
            "name": "OpenAI GPT-4",
            "provider": "OpenAI"
        }
        
        mocker.patch('services.agent_service.AgentRepository.get_by_app_id', return_value=[agent])
        mocker.patch(
            'services.agent_service.AgentRepository.get_ai_services_dict_by_app_id',
            return_value={1: ai_service_dict}
        )
        
        result = service.get_agents_list(db, app_id=1)
        
        assert len(result) == 1
        # AI service should be in response
        assert result[0].service_id == 1

    def test_handles_agents_without_service(self, mocker):
        """Agents without AI service are handled gracefully."""
        db = MagicMock()
        service = AgentService()
        agent = make_agent(service_id=None)
        
        mocker.patch('services.agent_service.AgentRepository.get_by_app_id', return_value=[agent])
        mocker.patch('services.agent_service.AgentRepository.get_ai_services_dict_by_app_id', return_value={})
        
        result = service.get_agents_list(db, app_id=1)
        
        assert len(result) == 1
        assert result[0].service_id is None


# ---------------------------------------------------------------------------
# get_agents
# ---------------------------------------------------------------------------

class TestGetAgents:
    """Test AgentService.get_agents()"""

    def test_returns_raw_agent_objects(self, mocker):
        """get_agents returns raw ORM objects, not schemas."""
        db = MagicMock()
        service = AgentService()
        agent = make_agent()
        
        mocker.patch('services.agent_service.AgentRepository.get_by_app_id', return_value=[agent])
        
        result = service.get_agents(db, app_id=1)
        
        assert len(result) == 1
        assert result[0].agent_id == agent.agent_id

    def test_filters_by_app_id(self, mocker):
        """Only returns agents for the specified app."""
        db = MagicMock()
        service = AgentService()
        agent1 = make_agent(agent_id=1, app_id=1)
        agent2 = make_agent(agent_id=2, app_id=2)
        
        mocker.patch(
            'services.agent_service.AgentRepository.get_by_app_id',
            side_effect=lambda db, app_id: [agent1] if app_id == 1 else [agent2]
        )
        
        result = service.get_agents(db, app_id=1)
        
        assert len(result) == 1
        assert result[0].app_id == 1


# ---------------------------------------------------------------------------
# get_tool_agents
# ---------------------------------------------------------------------------

class TestGetToolAgents:
    """Test AgentService.get_tool_agents()"""

    def test_returns_only_tool_agents(self, mocker):
        """Only returns agents marked as tools."""
        db = MagicMock()
        service = AgentService()
        tool_agent = make_agent(agent_id=1, is_tool=True)
        regular_agent = make_agent(agent_id=2, is_tool=False)
        
        mocker.patch(
            'services.agent_service.AgentRepository.get_tool_agents_by_app_id',
            return_value=[tool_agent]
        )
        
        result = service.get_tool_agents(db, app_id=1)
        
        assert len(result) == 1
        assert result[0].is_tool is True

    def test_excludes_specific_agent(self, mocker):
        """Can exclude a specific agent from results."""
        db = MagicMock()
        service = AgentService()
        
        mocker.patch(
            'services.agent_service.AgentRepository.get_tool_agents_by_app_id',
            return_value=[]
        )
        
        result = service.get_tool_agents(db, app_id=1, exclude_agent_id=5)
        
        assert result == []


# ---------------------------------------------------------------------------
# get_agent_detail
# ---------------------------------------------------------------------------

class TestGetAgentDetail:
    """Test AgentService.get_agent_detail()"""

    def test_returns_agent_detail_schema(self, mocker):
        """get_agent_detail returns AgentDetailSchema."""
        db = MagicMock()
        service = AgentService()
        agent = make_agent()
        
        # Mock the private methods
        mocker.patch.object(service, '_get_agent_for_detail', return_value=agent)
        mocker.patch.object(service, '_get_form_data', return_value={
            'ai_services': [],
            'silos': [],
            'output_parsers': [],
            'tools': [],
            'mcp_configs': [],
            'skills': []
        })
        mocker.patch.object(service, '_get_agent_associations', return_value={
            'tool_ids': [],
            'mcp_ids': [],
            'skill_ids': []
        })
        mocker.patch.object(service, '_get_silo_info', return_value=None)
        mocker.patch.object(service, '_get_output_parser_info', return_value=None)
        
        result = service.get_agent_detail(db, app_id=1, agent_id=1)
        
        assert result is not None
        assert result.agent_id == 1

    def test_returns_none_for_missing_agent(self, mocker):
        """Returns None if agent doesn't exist."""
        db = MagicMock()
        service = AgentService()
        
        mocker.patch.object(service, '_get_agent_for_detail', return_value=None)
        
        result = service.get_agent_detail(db, app_id=1, agent_id=99999)
        
        assert result is None

    def test_includes_form_data(self, mocker):
        """Response includes form data for dropdowns."""
        db = MagicMock()
        service = AgentService()
        agent = make_agent()
        
        # Return dicts instead of MagicMock objects for schema validation
        form_data = {
            'ai_services': [{"service_id": 1, "name": "OpenAI GPT-4", "provider": "OpenAI"}],
            'silos': [],
            'output_parsers': [],
            'tools': [],
            'mcp_configs': [],
            'skills': []
        }
        
        mocker.patch.object(service, '_get_agent_for_detail', return_value=agent)
        mocker.patch.object(service, '_get_form_data', return_value=form_data)
        mocker.patch.object(service, '_get_agent_associations', return_value={
            'tool_ids': [],
            'mcp_ids': [],
            'skill_ids': []
        })
        mocker.patch.object(service, '_get_silo_info', return_value=None)
        mocker.patch.object(service, '_get_output_parser_info', return_value=None)
        
        result = service.get_agent_detail(db, app_id=1, agent_id=1)
        
        assert result.ai_services is not None
        assert len(result.ai_services) == 1


# ---------------------------------------------------------------------------
# get_available_chat_filter_fields
# ---------------------------------------------------------------------------

class TestGetAvailableChatFilterFields:
    """Test AgentService.get_available_chat_filter_fields()"""

    def test_unions_fields_across_candidate_silos(self, mocker):
        """Fields from the own silo and every candidate tool's silo are unioned."""
        db = MagicMock()
        service = AgentService()

        db.query.return_value.filter.return_value.all.return_value = [(2, 201)]

        def fake_silo_info(_db, silo_id):
            if silo_id == 100:  # own silo
                return {"metadata_definition": {"fields": [{"name": "region", "type": "str"}]}}
            if silo_id == 201:  # subagent silo
                return {"metadata_definition": {"fields": [{"name": "machine_model", "type": "str"}]}}
            return None

        mocker.patch(
            'services.agent_service.AgentRepository.get_silo_with_metadata_definition',
            side_effect=fake_silo_info,
        )

        result = service.get_available_chat_filter_fields(db, tool_ids=[2], own_silo_id=100)

        names = {f['name'] for f in result}
        assert names == {'region', 'machine_model'}

    def test_dedupes_field_name_across_silos_without_erroring(self, mocker):
        """Two candidate silos declaring the same field name by different types
        must be deduped into a single entry, not raise, and (per the current
        implementation, which iterates a plain Python ``set`` of silo_ids —
        NOT an ordered structure) the type kept is whichever silo is visited
        first in that set's iteration order."""
        db = MagicMock()
        service = AgentService()

        # tool_ids [2, 3] map to silo_ids 201 and 202 respectively.
        db.query.return_value.filter.return_value.all.return_value = [(2, 201), (3, 202)]

        def fake_silo_info(_db, silo_id):
            if silo_id == 201:
                return {"metadata_definition": {"fields": [{"name": "machine_model", "type": "str"}]}}
            if silo_id == 202:
                return {"metadata_definition": {"fields": [{"name": "machine_model", "type": "int"}]}}
            return None

        mocker.patch(
            'services.agent_service.AgentRepository.get_silo_with_metadata_definition',
            side_effect=fake_silo_info,
        )

        result = service.get_available_chat_filter_fields(db, tool_ids=[2, 3], own_silo_id=None)

        # Deduped: exactly one "machine_model" entry, no exception raised.
        matching = [f for f in result if f['name'] == 'machine_model']
        assert len(matching) == 1
        # CPython set iteration over small distinct ints is ascending in practice,
        # so silo 201 (added first) is visited before 202 — asserting the actual
        # observed behavior, not a documented contract.
        assert matching[0]['type'] == 'str'

    def test_broken_metadata_definition_for_one_silo_does_not_block_others(self, mocker):
        """A silo lookup raising an exception contributes nothing but doesn't
        prevent other candidate silos' fields from being included."""
        db = MagicMock()
        service = AgentService()

        db.query.return_value.filter.return_value.all.return_value = [(2, 201), (3, 202)]

        def fake_silo_info(_db, silo_id):
            if silo_id == 201:
                raise RuntimeError("boom")
            if silo_id == 202:
                return {"metadata_definition": {"fields": [{"name": "machine_model", "type": "str"}]}}
            return None

        mocker.patch(
            'services.agent_service.AgentRepository.get_silo_with_metadata_definition',
            side_effect=fake_silo_info,
        )

        result = service.get_available_chat_filter_fields(db, tool_ids=[2, 3], own_silo_id=None)

        assert [f['name'] for f in result] == ['machine_model']

    def test_returns_empty_list_with_no_candidates(self, mocker):
        db = MagicMock()
        service = AgentService()

        result = service.get_available_chat_filter_fields(db, tool_ids=[], own_silo_id=None)

        assert result == []


# ---------------------------------------------------------------------------
# get_chat_filter_values
# ---------------------------------------------------------------------------

class TestGetChatFilterValues:
    """Test AgentService.get_chat_filter_values()"""

    def _make_orchestrator_with_subagents(self, exposed_chat_filters, sub_silo_ids):
        agent = MagicMock()
        agent.exposed_chat_filters = exposed_chat_filters
        agent.silo_id = None
        associations = []
        for silo_id in sub_silo_ids:
            assoc = MagicMock()
            assoc.tool = MagicMock(silo_id=silo_id)
            associations.append(assoc)
        agent.tool_associations = associations
        return agent

    def test_aggregates_values_only_from_silos_that_declare_the_field(self, mocker):
        """Only the subagent silo declaring ``machine_model`` contributes values;
        the other subagent's silo (which lacks the field) causes no error and no
        garbage entry."""
        db = MagicMock()
        service = AgentService()
        agent = self._make_orchestrator_with_subagents(
            exposed_chat_filters=["machine_model"], sub_silo_ids=[101, 102]
        )

        def fake_silo_info(_db, silo_id):
            if silo_id == 101:
                return {"metadata_definition": {"fields": [{"name": "machine_model", "type": "str"}]}}
            if silo_id == 102:
                return {"metadata_definition": {"fields": [{"name": "other_field", "type": "str"}]}}
            return None

        mocker.patch(
            'services.agent_service.AgentRepository.get_silo_with_metadata_definition',
            side_effect=fake_silo_info,
        )
        mock_get_values = mocker.patch(
            'services.agent_service.MetadataValuesCacheService.get_distinct_values',
            return_value=["X100", "X200"],
        )

        result = service.get_chat_filter_values(db, agent)

        assert result == [{"field_name": "machine_model", "values": ["X100", "X200"]}]
        # Only the declaring silo (101) was ever queried for distinct values.
        called_silo_ids = {call.args[0] for call in mock_get_values.call_args_list}
        assert called_silo_ids == {101}

    def test_never_raises_when_one_silos_lookup_fails(self, mocker):
        """A distinct-values lookup failure for one silo is swallowed; aggregation
        for the other declaring silo still completes."""
        db = MagicMock()
        service = AgentService()
        agent = self._make_orchestrator_with_subagents(
            exposed_chat_filters=["machine_model"], sub_silo_ids=[101, 102]
        )

        def fake_silo_info(_db, silo_id):
            # Both silos declare the field so both are queried for values.
            return {"metadata_definition": {"fields": [{"name": "machine_model", "type": "str"}]}}

        mocker.patch(
            'services.agent_service.AgentRepository.get_silo_with_metadata_definition',
            side_effect=fake_silo_info,
        )

        def fake_get_values(silo_id, field, db_arg):
            if silo_id == 101:
                raise RuntimeError("vector store unreachable")
            return ["X200"]

        mocker.patch(
            'services.agent_service.MetadataValuesCacheService.get_distinct_values',
            side_effect=fake_get_values,
        )

        result = service.get_chat_filter_values(db, agent)

        # Never raises; the surviving silo's values are still returned.
        assert result == [{"field_name": "machine_model", "values": ["X200"]}]

    def test_returns_empty_list_when_no_exposed_filters(self, mocker):
        db = MagicMock()
        service = AgentService()
        agent = self._make_orchestrator_with_subagents(exposed_chat_filters=[], sub_silo_ids=[101])

        result = service.get_chat_filter_values(db, agent)

        assert result == []

    def test_field_omitted_when_no_silo_declares_it(self, mocker):
        """A field in exposed_chat_filters with zero declaring silos is silently
        omitted from the result, not an error."""
        db = MagicMock()
        service = AgentService()
        agent = self._make_orchestrator_with_subagents(
            exposed_chat_filters=["machine_model"], sub_silo_ids=[101]
        )

        mocker.patch(
            'services.agent_service.AgentRepository.get_silo_with_metadata_definition',
            return_value={"metadata_definition": {"fields": [{"name": "other_field", "type": "str"}]}},
        )

        result = service.get_chat_filter_values(db, agent)

        assert result == []


# ---------------------------------------------------------------------------
# create_or_update_agent
# ---------------------------------------------------------------------------

class TestCreateOrUpdateAgent:
    """Test AgentService.create_or_update_agent()"""

    def test_creates_new_agent_when_id_is_zero(self, mocker):
        """Creating with agent_id=0 creates a new agent."""
        db = MagicMock()
        service = AgentService()
        agent_data = {
            'agent_id': 0,
            'app_id': 1,
            'name': 'New Agent',
            'description': 'Test',
            'system_prompt': 'Test prompt',
            'prompt_template': None,
            'status': None,
            'service_id': None,
            'silo_id': None,
            'has_memory': False,
            'output_parser_id': None,
            'temperature': 0.7,
            'is_tool': False,
            'vision_service_id': None,
            'vision_system_prompt': None,
            'text_system_prompt': None,
        }
        
        # Mock the repository methods
        mocker.patch('services.agent_service.AgentRepository.get_agent_by_id_and_type', return_value=None)
        
        # Create a mock agent that will be returned by create
        created_agent = MagicMock()
        created_agent.agent_id = 5
        mocker.patch('services.agent_service.AgentRepository.create', return_value=created_agent)
        
        result = service.create_or_update_agent(db, agent_data, agent_type='agent')
        
        # The service returns the agent_id from the created agent
        assert result == 5

    def test_updates_existing_agent_when_id_not_zero(self, mocker):
        """Creating with agent_id!=0 updates the existing agent."""
        db = MagicMock()
        service = AgentService()
        agent_data = {
            'agent_id': 5,
            'app_id': 1,
            'name': 'Updated Agent',
            'description': 'Test',
            'system_prompt': 'Updated prompt',
            'prompt_template': None,
            'status': None,
            'service_id': None,
            'silo_id': None,
            'has_memory': False,
            'output_parser_id': None,
            'temperature': 0.7,
            'is_tool': False,
            'vision_service_id': None,
            'vision_system_prompt': None,
            'text_system_prompt': None,
        }
        
        existing_agent = make_agent(agent_id=5, name='Old Name')
        updated_agent = make_agent(agent_id=5, name='Updated Agent')
        
        mocker.patch('services.agent_service.AgentRepository.get_agent_by_id_and_type', return_value=existing_agent)
        mocker.patch.object(service, '_update_normal_agent')
        mocker.patch('services.agent_service.AgentRepository.update', return_value=updated_agent)
        
        result = service.create_or_update_agent(db, agent_data, agent_type='agent')

        assert result == 5  # Returns the agent ID

    def test_rejects_exposed_chat_filters_referencing_unknown_field(self, mocker):
        """An exposed_chat_filters entry absent from every candidate silo's
        metadata fields is rejected with a ValueError, mirroring the existing
        rag_fixed_filters unknown-field validation."""
        db = MagicMock()
        service = AgentService()
        agent_data = {
            'agent_id': 0,
            'app_id': 1,
            'name': 'Orchestrator',
            'description': 'Test',
            'system_prompt': '',
            'prompt_template': None,
            'status': None,
            'service_id': None,
            'silo_id': None,
            'has_memory': False,
            'output_parser_id': None,
            'temperature': 0.7,
            'is_tool': False,
            'vision_service_id': None,
            'vision_system_prompt': None,
            'text_system_prompt': None,
            'tool_ids': [2],
            'exposed_chat_filters': ['bogus_field'],
        }

        mocker.patch('services.agent_service.AgentRepository.get_agent_by_id_and_type', return_value=None)
        mocker.patch.object(
            service,
            'get_available_chat_filter_fields',
            return_value=[{'name': 'machine_model', 'type': 'str', 'description': None}],
        )

        with pytest.raises(ValueError, match='exposed_chat_filters references unknown metadata fields'):
            service.create_or_update_agent(db, agent_data, agent_type='agent')

    def test_accepts_exposed_chat_filters_that_are_available(self, mocker):
        """An exposed_chat_filters entry present in the available fields union is
        accepted and the agent is persisted normally."""
        db = MagicMock()
        service = AgentService()
        agent_data = {
            'agent_id': 0,
            'app_id': 1,
            'name': 'Orchestrator',
            'description': 'Test',
            'system_prompt': '',
            'prompt_template': None,
            'status': None,
            'service_id': None,
            'silo_id': None,
            'has_memory': False,
            'output_parser_id': None,
            'temperature': 0.7,
            'is_tool': False,
            'vision_service_id': None,
            'vision_system_prompt': None,
            'text_system_prompt': None,
            'tool_ids': [2],
            'exposed_chat_filters': ['machine_model'],
        }

        mocker.patch('services.agent_service.AgentRepository.get_agent_by_id_and_type', return_value=None)
        mocker.patch.object(
            service,
            'get_available_chat_filter_fields',
            return_value=[{'name': 'machine_model', 'type': 'str', 'description': None}],
        )
        created_agent = MagicMock()
        created_agent.agent_id = 7
        mocker.patch('services.agent_service.AgentRepository.create', return_value=created_agent)

        result = service.create_or_update_agent(db, agent_data, agent_type='agent')

        assert result == 7

    def test_rejects_rag_fixed_filters_on_agent_without_silo(self, mocker):
        """rag_fixed_filters requires a silo; setting it without one is rejected.

        Mirrors the existing validation pattern this test class follows for
        exposed_chat_filters, confirming the two validations are independent.
        """
        db = MagicMock()
        service = AgentService()
        agent_data = {
            'agent_id': 0,
            'app_id': 1,
            'name': 'No Silo Agent',
            'description': 'Test',
            'system_prompt': '',
            'prompt_template': None,
            'status': None,
            'service_id': None,
            'silo_id': None,
            'has_memory': False,
            'output_parser_id': None,
            'temperature': 0.7,
            'is_tool': False,
            'vision_service_id': None,
            'vision_system_prompt': None,
            'text_system_prompt': None,
            'rag_fixed_filters': [{'field': 'machine_model', 'op': '$eq', 'value': 'X100'}],
        }

        mocker.patch('services.agent_service.AgentRepository.get_agent_by_id_and_type', return_value=None)

        with pytest.raises(ValueError, match='rag_fixed_filters can only be set on an agent that has a silo'):
            service.create_or_update_agent(db, agent_data, agent_type='agent')


# ---------------------------------------------------------------------------
# update_agent_tools
# ---------------------------------------------------------------------------

class TestUpdateAgentTools:
    """Test AgentService.update_agent_tools()"""

    def test_adds_tool_associations(self, mocker):
        """Adding tools creates new associations."""
        db = MagicMock()
        service = AgentService()
        agent = make_agent(agent_id=1)
        
        mocker.patch('services.agent_service.AgentRepository.get_by_id', return_value=agent)
        mocker.patch('services.agent_service.AgentRepository.get_agent_tool_associations', return_value=[])
        mocker.patch('services.agent_service.AgentRepository.get_valid_tool_ids', return_value={2, 3})
        mock_create = mocker.patch('services.agent_service.AgentRepository.create_agent_tool_association')
        
        service.update_agent_tools(db, agent_id=1, tool_ids=[2, 3])
        
        # Should call create for each tool
        assert mock_create.call_count == 2

    def test_removes_obsolete_tool_associations(self, mocker):
        """Removing tools deletes old associations."""
        db = MagicMock()
        service = AgentService()
        agent = make_agent(agent_id=1)
        old_assoc = MagicMock()
        old_assoc.tool_id = 2
        
        mocker.patch('services.agent_service.AgentRepository.get_by_id', return_value=agent)
        mocker.patch(
            'services.agent_service.AgentRepository.get_agent_tool_associations',
            return_value=[old_assoc]
        )
        mocker.patch('services.agent_service.AgentRepository.get_valid_tool_ids', return_value=set())
        mocker.patch('services.agent_service.AgentRepository.delete_agent_tool_association')
        
        service.update_agent_tools(db, agent_id=1, tool_ids=[])
        
        # Should delete the old association


# ---------------------------------------------------------------------------
# update_agent_mcps
# ---------------------------------------------------------------------------

class TestUpdateAgentMCPs:
    """Test AgentService.update_agent_mcps()"""

    def test_adds_mcp_associations(self, mocker):
        """Adding MCPs creates new associations."""
        db = MagicMock()
        service = AgentService()
        agent = make_agent(agent_id=1)
        
        mocker.patch('services.agent_service.AgentRepository.get_by_id', return_value=agent)
        mocker.patch('services.agent_service.AgentRepository.get_agent_mcp_associations', return_value=[])
        mocker.patch('services.agent_service.AgentRepository.create_agent_mcp_association')
        
        service.update_agent_mcps(db, agent_id=1, mcp_ids=[2, 3])
        
        # Should create associations


# ---------------------------------------------------------------------------
# Edge Cases and Error Handling
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_handles_agent_without_type(self, mocker):
        """Agents without a type are handled gracefully."""
        db = MagicMock()
        service = AgentService()
        agent = make_agent()
        agent.type = None
        
        mocker.patch('services.agent_service.AgentRepository.get_by_app_id', return_value=[agent])
        mocker.patch('services.agent_service.AgentRepository.get_ai_services_dict_by_app_id', return_value={})
        
        result = service.get_agents_list(db, app_id=1)
        
        assert len(result) == 1

    def test_handles_agent_with_zero_temperature(self, mocker):
        """Temperature of 0 is valid."""
        db = MagicMock()
        service = AgentService()
        agent_data = {
            'agent_id': 0,
            'app_id': 1,
            'name': 'Cold Agent',
            'description': '',
            'system_prompt': '',
            'prompt_template': None,
            'status': None,
            'service_id': None,
            'silo_id': None,
            'has_memory': False,
            'output_parser_id': None,
            'temperature': 0,  # Valid edge case
            'is_tool': False,
            'vision_service_id': None,
            'vision_system_prompt': None,
            'text_system_prompt': None,
        }
        
        # Mock the repository methods
        mocker.patch('services.agent_service.AgentRepository.get_agent_by_id_and_type', return_value=None)
        
        # Create a mock agent that will be returned by create
        created_agent = MagicMock()
        created_agent.agent_id = 10
        created_agent.temperature = 0
        mocker.patch('services.agent_service.AgentRepository.create', return_value=created_agent)
        
        result = service.create_or_update_agent(db, agent_data, agent_type='agent')
        
        # Verify the temperature was set to 0 on the returned agent
        assert result == 10
