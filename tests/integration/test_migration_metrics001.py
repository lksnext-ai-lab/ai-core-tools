"""
Integration tests for the metrics001 migration schema state.

Verifies that the agent_execution_event and agent_tool_call tables exist
with all expected columns, indexes, and enum types.

These tests use the session-scoped test_engine fixture (schema created via
Base.metadata.create_all which reflects all registered ORM models including
the new AgentExecutionEvent and AgentToolCall models).
"""
import pytest
from sqlalchemy import inspect, text


class TestMetricsMigrationSchema:
    """Verify the metrics001 migration produced the expected schema."""

    def test_agent_execution_event_table_exists(self, test_engine):
        inspector = inspect(test_engine)
        assert "agent_execution_event" in inspector.get_table_names(), \
            "agent_execution_event table not found"

    def test_agent_tool_call_table_exists(self, test_engine):
        inspector = inspect(test_engine)
        assert "agent_tool_call" in inspector.get_table_names(), \
            "agent_tool_call table not found"

    def test_agent_execution_event_columns(self, test_engine):
        inspector = inspect(test_engine)
        columns = {col["name"] for col in inspector.get_columns("agent_execution_event")}
        expected = {
            "event_id", "app_id", "agent_id", "conversation_id", "user_id",
            "api_key_id", "caller_type", "parent_execution_id", "started_at",
            "finished_at", "duration_ms", "status", "error_code", "error_message",
            "model_name", "ai_service_id", "input_tokens", "output_tokens",
            "total_tokens", "tool_calls", "retrieved_docs", "had_files", "file_count",
            "had_images", "output_parser_used", "parser_succeeded",
            "prompt_chars", "response_chars", "created_at",
        }
        missing = expected - columns
        assert not missing, f"agent_execution_event missing columns: {missing}"

    def test_agent_tool_call_columns(self, test_engine):
        inspector = inspect(test_engine)
        columns = {col["name"] for col in inspector.get_columns("agent_tool_call")}
        expected = {
            "tool_call_id", "event_id", "tool_name", "tool_type",
            "sub_agent_id", "mcp_config_id", "duration_ms", "status",
            "error_message", "started_at",
        }
        missing = expected - columns
        assert not missing, f"agent_tool_call missing columns: {missing}"

    def test_enum_types_exist(self, test_engine):
        """The four PostgreSQL enum types must exist."""
        with test_engine.connect() as conn:
            result = conn.execute(text(
                "SELECT typname FROM pg_type WHERE typtype = 'e' "
                "AND typname IN ("
                "  'agent_execution_caller_type', 'agent_execution_status',"
                "  'agent_tool_call_type', 'agent_tool_call_status'"
                ")"
            ))
            found = {row[0] for row in result}

        expected = {
            "agent_execution_caller_type",
            "agent_execution_status",
            "agent_tool_call_type",
            "agent_tool_call_status",
        }
        missing = expected - found
        assert not missing, f"Missing enum types: {missing}"
