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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
