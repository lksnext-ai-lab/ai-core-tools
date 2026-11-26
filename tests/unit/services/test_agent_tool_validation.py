"""
Unit tests for AgentService.validate_tool_selection and tool_ids on the agent list.

The repository is mocked (pytest-mock), so no database is needed.
Tests focus on:
  - Self-reference rejection (an agent cannot use itself as a tool)
  - Non-tool / cross-app tool rejection
  - Direct and indirect tool cycle rejection
  - De-duplication of the selection
  - Only NEWLY added ids are validated: already-attached ids that went stale (no
    longer tool agents) are dropped silently, and pre-existing cycles don't block a
    save that adds nothing new
  - tool_ids exposure on AgentListItemSchema
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from services.agent_service import AgentService


# ---------------------------------------------------------------------------
# validate_tool_selection
# ---------------------------------------------------------------------------

class TestValidateToolSelection:
    """Test AgentService.validate_tool_selection()"""

    def test_self_reference_rejected(self, mocker):
        """An agent cannot list itself as a tool."""
        db = MagicMock()
        mocker.patch('services.agent_service.AgentRepository.get_valid_tool_ids', return_value=[])
        mocker.patch('services.agent_service.AgentRepository.get_tool_edges_by_app_id', return_value={})

        with pytest.raises(ValueError, match="An agent cannot use itself as a tool"):
            AgentService.validate_tool_selection(db, app_id=1, agent_id=1, tool_ids=[1])

    def test_non_tool_dropped(self, mocker):
        """A selection id that is not a tool agent of this app is dropped, not attached."""
        db = MagicMock()
        mocker.patch('services.agent_service.AgentRepository.get_valid_tool_ids', return_value=[2])
        mocker.patch('services.agent_service.AgentRepository.get_tool_edges_by_app_id', return_value={})

        assert AgentService.validate_tool_selection(db, app_id=1, agent_id=1, tool_ids=[2, 3]) == [2]

    def test_direct_cycle_rejected(self, mocker):
        """Selecting a tool that already uses this agent would create a direct cycle."""
        db = MagicMock()
        mocker.patch('services.agent_service.AgentRepository.get_valid_tool_ids', return_value=[2])
        mocker.patch('services.agent_service.AgentRepository.get_tool_edges_by_app_id', return_value={2: [1]})

        with pytest.raises(ValueError, match="Adding agent 2 as a tool would create a cycle"):
            AgentService.validate_tool_selection(db, app_id=1, agent_id=1, tool_ids=[2])

    def test_indirect_cycle_rejected(self, mocker):
        """A cycle through an intermediate tool agent is rejected."""
        db = MagicMock()
        mocker.patch('services.agent_service.AgentRepository.get_valid_tool_ids', return_value=[2])
        mocker.patch('services.agent_service.AgentRepository.get_tool_edges_by_app_id', return_value={2: [3], 3: [1]})

        with pytest.raises(ValueError, match="Adding agent 2 as a tool would create a cycle"):
            AgentService.validate_tool_selection(db, app_id=1, agent_id=1, tool_ids=[2])

    def test_new_agent_skips_cycle_check(self, mocker):
        """A new agent (id 0) has no outgoing edges yet, so no cycle is possible."""
        db = MagicMock()
        mocker.patch('services.agent_service.AgentRepository.get_valid_tool_ids', return_value=[2])
        mocker.patch('services.agent_service.AgentRepository.get_tool_edges_by_app_id', return_value={2: [5]})

        result = AgentService.validate_tool_selection(db, app_id=1, agent_id=0, tool_ids=[2])

        assert result == [2]

    def test_valid_selection_returns_deduplicated(self, mocker):
        """Duplicates are dropped; a valid acyclic selection passes through."""
        db = MagicMock()
        mocker.patch('services.agent_service.AgentRepository.get_valid_tool_ids', return_value=[2, 4])
        mocker.patch('services.agent_service.AgentRepository.get_tool_edges_by_app_id', return_value={})

        result = AgentService.validate_tool_selection(db, app_id=1, agent_id=1, tool_ids=[2, 2, 4])

        assert result == [2, 4]

    def test_empty_selection_ok(self, mocker):
        """An empty selection returns early without touching the repository."""
        db = MagicMock()
        get_valid = mocker.patch('services.agent_service.AgentRepository.get_valid_tool_ids', return_value=[])
        get_edges = mocker.patch('services.agent_service.AgentRepository.get_tool_edges_by_app_id', return_value={})

        result = AgentService.validate_tool_selection(db, app_id=1, agent_id=1, tool_ids=[])

        assert result == []
        get_valid.assert_not_called()
        get_edges.assert_not_called()


class TestValidateToolSelectionExistingTools:
    """Only ids that are NEW for the agent are validated; existing ids are tolerated."""

    def test_self_reference_rejected_even_if_already_attached(self, mocker):
        """Self-reference is always rejected, regardless of the current associations."""
        db = MagicMock()
        mocker.patch('services.agent_service.AgentRepository.get_agent_tool_associations',
                     return_value=[MagicMock(tool_id=1)])
        mocker.patch('services.agent_service.AgentRepository.get_valid_tool_ids', return_value=[1])
        mocker.patch('services.agent_service.AgentRepository.get_tool_edges_by_app_id', return_value={})

        with pytest.raises(ValueError, match="An agent cannot use itself as a tool"):
            AgentService.validate_tool_selection(db, app_id=1, agent_id=1, tool_ids=[1])

    def test_existing_stale_non_tool_dropped_new_valid_kept(self, mocker):
        """An already-attached id that is no longer a tool agent is dropped without error."""
        db = MagicMock()
        mocker.patch('services.agent_service.AgentRepository.get_agent_tool_associations',
                     return_value=[MagicMock(tool_id=2)])
        mocker.patch('services.agent_service.AgentRepository.get_valid_tool_ids', return_value=[3])
        mocker.patch('services.agent_service.AgentRepository.get_tool_edges_by_app_id', return_value={})

        result = AgentService.validate_tool_selection(db, app_id=1, agent_id=1, tool_ids=[2, 3])

        assert result == [3]

    def test_existing_cycle_does_not_block_save_adding_nothing_new(self, mocker):
        """A pre-existing cycle is not re-checked when the selection adds no new id."""
        db = MagicMock()
        mocker.patch('services.agent_service.AgentRepository.get_agent_tool_associations',
                     return_value=[MagicMock(tool_id=2)])
        mocker.patch('services.agent_service.AgentRepository.get_valid_tool_ids', return_value=[2])
        # 1 -> 2 -> 1 is already a cycle in the stored graph.
        mocker.patch('services.agent_service.AgentRepository.get_tool_edges_by_app_id', return_value={2: [1]})

        result = AgentService.validate_tool_selection(db, app_id=1, agent_id=1, tool_ids=[2])

        assert result == [2]

    def test_new_invalid_id_is_dropped(self, mocker):
        """A NEW id that is not a tool agent of the app is dropped, even next to existing ids."""
        db = MagicMock()
        mocker.patch('services.agent_service.AgentRepository.get_agent_tool_associations',
                     return_value=[MagicMock(tool_id=2)])
        mocker.patch('services.agent_service.AgentRepository.get_valid_tool_ids', return_value=[2])
        mocker.patch('services.agent_service.AgentRepository.get_tool_edges_by_app_id', return_value={})

        assert AgentService.validate_tool_selection(db, app_id=1, agent_id=1, tool_ids=[2, 3]) == [2]

    def test_new_id_creating_cycle_still_rejected(self, mocker):
        """A NEW id whose tool graph leads back to this agent raises, even with existing ids kept."""
        db = MagicMock()
        mocker.patch('services.agent_service.AgentRepository.get_agent_tool_associations',
                     return_value=[MagicMock(tool_id=4)])
        mocker.patch('services.agent_service.AgentRepository.get_valid_tool_ids', return_value=[2, 4])
        mocker.patch('services.agent_service.AgentRepository.get_tool_edges_by_app_id',
                     return_value={2: [3], 3: [1], 4: []})

        with pytest.raises(ValueError, match="Adding agent 2 as a tool would create a cycle"):
            AgentService.validate_tool_selection(db, app_id=1, agent_id=1, tool_ids=[4, 2])

    def test_existing_and_new_kept_in_submitted_order(self, mocker):
        """Existing valid ids and new valid ids are returned de-duplicated, in submitted order."""
        db = MagicMock()
        mocker.patch('services.agent_service.AgentRepository.get_agent_tool_associations',
                     return_value=[MagicMock(tool_id=4), MagicMock(tool_id=2)])
        mocker.patch('services.agent_service.AgentRepository.get_valid_tool_ids', return_value=[2, 3, 4])
        mocker.patch('services.agent_service.AgentRepository.get_tool_edges_by_app_id', return_value={})

        result = AgentService.validate_tool_selection(db, app_id=1, agent_id=1, tool_ids=[4, 3, 2, 4])

        assert result == [4, 3, 2]


# ---------------------------------------------------------------------------
# AgentListItemSchema.tool_ids
# ---------------------------------------------------------------------------

class TestListItemIncludesToolIds:
    """Test that get_agents_list fills tool_ids from the app's tool edges (one query)"""

    def test_list_item_includes_tool_ids(self, mocker):
        """The agent list item carries the ids of the tool agents it uses."""
        db = MagicMock()
        service = AgentService()
        agent = MagicMock()
        agent.agent_id = 5
        agent.name = "Test Agent"
        agent.description = "Test agent description"
        agent.type = "agent"
        agent.is_tool = False
        agent.create_date = datetime(2024, 1, 1)
        agent.service_id = None
        agent.request_count = 0
        agent.marketplace_visibility = None
        mocker.patch('services.agent_service.AgentRepository.get_by_app_id', return_value=[agent])
        mocker.patch('services.agent_service.AgentRepository.get_ai_services_dict_by_app_id', return_value={})
        mocker.patch('services.agent_service.AgentRepository.get_tool_edges_by_app_id', return_value={5: [7]})

        result = service.get_agents_list(db, app_id=1)

        assert len(result) == 1
        assert result[0].tool_ids == [7]
