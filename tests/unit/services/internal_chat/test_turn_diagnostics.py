"""TurnDiagnostics: the per-turn carrier of MCP load failures (never shared, never part of config equality)."""
from unittest.mock import MagicMock

from services.internal_chat.resolved_config import ResolvedChatConfig, TurnDiagnostics
from tools.agentTools import _report_chat_mcp_unavailable


def _real_config(mcp_ids=(1, 2)) -> ResolvedChatConfig:
    return ResolvedChatConfig(
        app_id=1, ai_service=MagicMock(), ai_service_id=77, ai_service_name="S",
        ai_service_is_system=False, ai_service_provider="Anthropic", ai_service_model="claude-x",
        silo=None, silo_id=None, silo_name=None, skills=(), skill_ids=(), skill_names=(),
        mcp_connections=(), mcp_config_ids=tuple(mcp_ids), mcp_config_names=tuple("m" for _ in mcp_ids),
        system_prompt="p",
    )


def test_each_resolved_config_owns_its_carrier():
    a, b = _real_config((1, 2)), _real_config((3,))
    assert a.diagnostics is not b.diagnostics  # fails if default_factory were replaced by a shared default
    _report_chat_mcp_unavailable(a)
    _report_chat_mcp_unavailable(a)  # deduplicated
    assert a.diagnostics.mcp_unavailable_ids == [1, 2]
    assert b.diagnostics.mcp_unavailable_ids == []  # another turn / user is untouched


def test_non_chat_agents_and_turns_without_mcp_report_nothing():
    _report_chat_mcp_unavailable(None)
    empty = _real_config(())
    _report_chat_mcp_unavailable(empty)
    assert empty.diagnostics.mcp_unavailable_ids == []


def test_reset_drops_the_report_of_an_earlier_attempt():
    cfg = _real_config((1,))
    _report_chat_mcp_unavailable(cfg)
    cfg.diagnostics.reset()
    assert cfg.diagnostics.mcp_unavailable_ids == []
