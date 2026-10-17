"""Basic tests for Agent Export/Import functionality."""

import pytest
from pydantic import ValidationError
from schemas.export_schemas import (
    ExportAgentSchema,
    ExportAgentToolRefSchema,
    ExportAgentMCPRefSchema,
    AgentExportFileSchema,
    ExportMetadataSchema,
)


def test_export_agent_schema_minimal():
    """Test minimal valid agent export schema."""
    agent = ExportAgentSchema(
        name="Test Agent",
        description="A test agent",
        system_prompt="You are a helpful assistant",
        service_name="GPT-4",
    )
    assert agent.name == "Test Agent"
    assert agent.service_name == "GPT-4"
    assert agent.has_memory is False  # Default
    assert agent.temperature == 0.7  # Default


def test_export_agent_schema_full():
    """Test agent export schema with all fields."""
    agent = ExportAgentSchema(
        name="Full Agent",
        description="Complete agent",
        system_prompt="System prompt",
        service_name="GPT-4",
        silo_name="Knowledge Base",
        output_parser_name="JSON Parser",
        agent_tool_refs=[
            ExportAgentToolRefSchema(tool_agent_name="Helper Agent")
        ],
        agent_mcp_refs=[
            ExportAgentMCPRefSchema(mcp_name="File MCP")
        ],
        has_memory=True,
        memory_max_messages=50,
        memory_max_tokens=8000,
        memory_summarize_threshold=20,
        temperature=0.5,
    )
    assert agent.name == "Full Agent"
    assert agent.has_memory is True
    assert agent.memory_max_messages == 50
    assert len(agent.agent_tool_refs) == 1
    assert len(agent.agent_mcp_refs) == 1


def test_export_agent_schema_validation():
    """Test agent export schema validation."""
    # Empty name should fail
    with pytest.raises(ValidationError):
        ExportAgentSchema(name="")

    # Valid minimal agent
    agent = ExportAgentSchema(name="Valid Agent")
    assert agent.name == "Valid Agent"


def test_agent_export_file_schema():
    """Test full agent export file schema."""
    from schemas.export_schemas import ExportAIServiceSchema
    
    metadata = ExportMetadataSchema()
    agent = ExportAgentSchema(
        name="Test Agent",
        service_name="GPT-4"
    )
    ai_service = ExportAIServiceSchema(
        name="GPT-4",
        provider="openai",
        model_name="gpt-4",
    )
    
    export_file = AgentExportFileSchema(
        metadata=metadata,
        agent=agent,
        ai_service=ai_service,
    )
    
    assert export_file.agent.name == "Test Agent"
    assert export_file.ai_service is not None
    assert export_file.ai_service.name == "GPT-4"
    assert export_file.silo is None
    assert export_file.output_parser is None


def test_agent_tool_ref_schema():
    """Test agent tool reference schema."""
    tool_ref = ExportAgentToolRefSchema(tool_agent_name="Helper")
    assert tool_ref.tool_agent_name == "Helper"


def test_agent_mcp_ref_schema():
    """Test agent MCP reference schema."""
    mcp_ref = ExportAgentMCPRefSchema(mcp_name="File Manager")
    assert mcp_ref.mcp_name == "File Manager"


# ==================== A2A FIELDS (step_010, FR-24, AC-39) ====================


def test_export_agent_schema_a2a_fields_default_when_omitted():
    """An export payload that never mentions the A2A fields (e.g. a legacy
    export file predating step_009/step_010) must still import with the
    documented defaults, never raise."""
    agent = ExportAgentSchema(name="Legacy Agent")
    assert agent.a2a_enabled is False
    assert agent.a2a_card_visibility == "public"
    assert agent.a2a_name_override is None
    assert agent.a2a_description_override is None
    assert agent.a2a_skill_tags == []
    assert agent.a2a_examples == []


def test_export_agent_schema_a2a_fields_full():
    """All A2A fields round-trip through the export schema unchanged."""
    agent = ExportAgentSchema(
        name="A2A Agent",
        service_name="GPT-4",
        a2a_enabled=True,
        a2a_card_visibility="api_key",
        a2a_name_override="Public Name",
        a2a_description_override="Public description",
        a2a_skill_tags=["billing", "support"],
        a2a_examples=["How do I pay my invoice?"],
    )
    assert agent.a2a_enabled is True
    assert agent.a2a_card_visibility == "api_key"
    assert agent.a2a_name_override == "Public Name"
    assert agent.a2a_description_override == "Public description"
    assert agent.a2a_skill_tags == ["billing", "support"]
    assert agent.a2a_examples == ["How do I pay my invoice?"]


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param(
            {"a2a_skill_tags": [f"tag-{i}" for i in range(21)]},
            id="too_many_skill_tags",
        ),
        pytest.param(
            {"a2a_skill_tags": ["x" * 51]},
            id="skill_tag_too_long",
        ),
        pytest.param(
            {"a2a_examples": [f"example {i}" for i in range(21)]},
            id="too_many_examples",
        ),
        pytest.param(
            {"a2a_examples": ["x" * 501]},
            id="example_too_long",
        ),
        pytest.param(
            {"a2a_description_override": "x" * 1001},
            id="description_override_too_long",
        ),
        pytest.param(
            {"a2a_name_override": "x" * 256},
            id="name_override_too_long",
        ),
    ],
)
def test_export_agent_schema_a2a_fields_reject_over_cap_values(overrides):
    """Untrusted import payloads that exceed any step_009 cap must be
    rejected with a 422-equivalent ValidationError, not silently truncated."""
    with pytest.raises(ValidationError):
        ExportAgentSchema(name="Agent", **overrides)


def test_export_agent_schema_a2a_reuses_step_009_validators():
    """The export schema must reuse the exact caps/normalization from
    ``A2AAgentFieldsMixin`` (step_009) rather than duplicating them: a NUL
    character is rejected, and tags/examples are deduped and capped."""
    with pytest.raises(ValidationError):
        ExportAgentSchema(name="Agent", a2a_name_override="bad\x00name")

    agent = ExportAgentSchema(
        name="Agent",
        a2a_skill_tags=["Billing", "billing", "  Support  "],
    )
    assert agent.a2a_skill_tags == ["Billing", "Support"]

    with pytest.raises(ValidationError):
        ExportAgentSchema(name="Agent", a2a_card_visibility="invalid")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
