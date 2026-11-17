"""ResolvedChatConfig: the code-interpreter fields and where they do (not) show up."""
import dataclasses
from types import SimpleNamespace
from unittest.mock import MagicMock

from services.internal_chat.resolved_config import ResolvedChatConfig


def _config(sandbox):
    cfg = ResolvedChatConfig(
        app_id=1, ai_service=MagicMock(), ai_service_id=7, ai_service_name="S", ai_service_is_system=False,
        ai_service_provider="OpenAI", ai_service_model="m", silo=None, silo_id=None, silo_name=None,
        skills=(), skill_ids=(), skill_names=(), mcp_connections=(), mcp_config_ids=(), mcp_config_names=(),
        system_prompt="p",
    )
    if sandbox:
        cfg = dataclasses.replace(
            cfg, sandbox_service=SimpleNamespace(api_key="sb-secret"),  # pragma: allowlist secret
            sandbox_enabled=True, sandbox_service_id=5, sandbox_service_name="sbx", sandbox_provider="e2b",
        )
    return cfg


def test_client_summary_and_trace_carry_a_plain_flag():
    on, off = _config(True), _config(False)
    assert on.to_client_summary()["code_interpreter"] is True
    assert off.to_client_summary()["code_interpreter"] is False
    assert on.to_trace_metadata()["chat_code_interpreter"] is True
    assert on.to_trace_metadata()["chat_sandbox_service_id"] == 5
    assert off.to_trace_metadata()["chat_code_interpreter"] is False


def test_selection_dict_is_unchanged_and_secrets_are_not_exposed():
    on = _config(True)
    assert on.to_selection_dict() == _config(False).to_selection_dict()
    assert set(on.to_selection_dict()) == {"ai_service_id", "silo_id", "skill_ids", "mcp_config_ids"}
    assert "sb-secret" not in repr(on)  # pragma: allowlist secret
    assert "sb-secret" not in str(on.to_client_summary()) + str(on.to_trace_metadata())  # pragma: allowlist secret


def test_a_degraded_turn_reports_no_code_interpreter():
    cfg = _config(True)
    cfg.diagnostics.sandbox_degraded = True
    assert cfg.to_client_summary()["code_interpreter"] is False
    assert cfg.to_trace_metadata()["chat_code_interpreter"] is False


def test_system_default_source_is_enabled_without_a_service_id():
    cfg = dataclasses.replace(_config(False), sandbox_enabled=True)
    assert cfg.sandbox_service_id is None
    assert cfg.to_client_summary()["code_interpreter"] is True
