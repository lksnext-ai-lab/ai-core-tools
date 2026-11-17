"""``_prepare_turn`` sandbox branch for App Chat turns (code interpreter from the App default sandbox service)."""
import asyncio
import dataclasses
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from services.agent_execution_service import AgentExecutionService, _LazySandboxHandle, _LazySandboxProvider
from services.internal_chat.resolved_config import ResolvedChatConfig
from tools.sandbox.factory import SandboxProviderUnavailableError, SandboxServiceRetiredError


def _config(sandbox=True):
    svc = MagicMock(service_id=77, provider="Anthropic", description="m", app_id=None)
    cfg = ResolvedChatConfig(
        app_id=1, ai_service=svc, ai_service_id=77, ai_service_name="S", ai_service_is_system=True,
        ai_service_provider="Anthropic", ai_service_model="m", silo=None, silo_id=None, silo_name=None,
        skills=(), skill_ids=(), skill_names=(), mcp_connections=(), mcp_config_ids=(), mcp_config_names=(),
        system_prompt="p",
    )
    if sandbox:
        cfg = dataclasses.replace(
            cfg, sandbox_service=SimpleNamespace(service_id=5, provider="e2b", name="sbx"),
            sandbox_enabled=True, sandbox_service_id=5, sandbox_service_name="sbx", sandbox_provider="e2b",
        )
    return cfg


def _agent():
    a = MagicMock()
    a.is_internal_chat = True
    a.is_frozen = False
    a.name, a.type, a.has_memory, a.app_id, a.agent_id = "A", "agent", True, 1, 11
    a.enable_code_interpreter = False
    return a


def _svc():
    svc = AgentExecutionService.__new__(AgentExecutionService)
    agent = _agent()
    svc.agent_service = MagicMock(get_agent=MagicMock(return_value=agent))
    svc.session_service = MagicMock(get_user_session=AsyncMock(return_value=None))
    svc.agent_execution_repo = MagicMock()
    svc.agent_execution_repo.get_agent_with_relationships.return_value = _agent()
    svc._index_turn_uploads = AsyncMock()
    svc._select_message_files = MagicMock(return_value=[])
    return svc


def _prepare(svc, tmp_path, cfg, *, conversation_id=5, factory_side_effect=None, provider=None, by_id="cfg",
             legacy_return=None):
    conv = MagicMock(conversation_id=conversation_id, session_id="conv_11_abc")
    provider = provider or MagicMock(PROVIDER_NAME="fake")
    with patch("services.conversation_service.ConversationService.get_conversation", return_value=conv), \
         patch("services.agent_execution_service.get_app_config", return_value={"TMP_BASE_FOLDER": str(tmp_path)}), \
         patch("tools.sandbox.factory.provider_for_service", return_value=(provider, 5),
               side_effect=factory_side_effect) as for_service, \
         patch("repositories.internal_chat_repository.ChatOptionsRepository.sandbox_service_by_id",
               return_value=cfg.sandbox_service if by_id == "cfg" else by_id), \
         patch("tools.sandbox.factory.resolve_provider_and_service_id", return_value=legacy_return) as legacy:
        ctx = asyncio.run(svc._prepare_turn(
            agent_id=11, message="hi", conversation_id=conversation_id, db=MagicMock(),
            user_context={"user_id": 3, "app_id": 1}, turn_config=cfg,
        ))
    return ctx, for_service, legacy, provider


def test_chat_turn_with_sandbox_binds_a_lazy_handle_keyed_by_conversation(tmp_path):
    cfg = _config()
    ctx, for_service, legacy, provider = _prepare(_svc(), tmp_path, cfg)
    assert ctx.sandbox_session_key == "conv_11_5"
    assert isinstance(ctx.sandbox_handle, _LazySandboxHandle)
    assert isinstance(ctx.sandbox_provider, _LazySandboxProvider)
    assert ctx.sandbox_handle.sandbox_service_id == 5
    assert ctx.sandbox_handle._owner == (1, 3) and ctx.sandbox_handle._chat is True  # per-user/App limits: Chat only
    assert not ctx.sandbox_handle.is_materialized()  # nothing created yet
    assert for_service.call_args.args[0] is cfg.sandbox_service
    legacy.assert_not_called()  # never resolved from the hidden agent / env default
    provider.create_sandbox.assert_not_called()


def test_each_conversation_gets_its_own_key_and_working_dir(tmp_path):
    first, *_ = _prepare(_svc(), tmp_path, _config(), conversation_id=5)
    second, *_ = _prepare(_svc(), tmp_path, _config(), conversation_id=6)
    assert (first.sandbox_session_key, second.sandbox_session_key) == ("conv_11_5", "conv_11_6")
    assert first.working_dir != second.working_dir
    assert first.working_dir.endswith("5") and second.working_dir.endswith("6")


def test_system_default_source_uses_the_factory_env_resolution_without_an_agent(tmp_path):
    cfg = dataclasses.replace(_config(sandbox=False), sandbox_enabled=True)  # switch on, no App default
    provider = MagicMock(PROVIDER_NAME="fake")
    ctx, for_service, legacy, _ = _prepare(_svc(), tmp_path, cfg, legacy_return=(provider, None))
    legacy.assert_called_once_with(None)
    for_service.assert_not_called()
    assert ctx.sandbox_session_key == "conv_11_5" and ctx.sandbox_handle.sandbox_service_id is None
    assert cfg.diagnostics.sandbox_degraded is False


def test_a_vanished_app_default_degrades_and_never_falls_back_to_the_system_default(tmp_path):
    cfg = _config()
    ctx, for_service, legacy, _ = _prepare(_svc(), tmp_path, cfg, by_id=None)
    assert ctx.sandbox_handle is None
    for_service.assert_not_called()
    legacy.assert_not_called()
    assert cfg.diagnostics.sandbox_degraded is True and cfg.to_client_summary()["code_interpreter"] is False


def test_chat_turn_without_sandbox_service_builds_nothing(tmp_path):
    ctx, for_service, legacy, _ = _prepare(_svc(), tmp_path, _config(sandbox=False))
    assert ctx.sandbox_handle is None and ctx.sandbox_provider is None and ctx.sandbox_session_key is None
    for_service.assert_not_called()
    legacy.assert_not_called()


def test_hidden_agent_flag_alone_never_enables_the_sandbox(tmp_path):
    svc = _svc()
    svc.agent_execution_repo.get_agent_with_relationships.return_value.enable_code_interpreter = True
    ctx, for_service, legacy, _ = _prepare(svc, tmp_path, _config(sandbox=False))
    assert ctx.sandbox_handle is None
    for_service.assert_not_called()
    legacy.assert_not_called()


def test_chat_turn_without_conversation_id_fails_before_any_sandbox(tmp_path):
    svc = _svc()
    with patch("services.agent_execution_service.get_app_config", return_value={"TMP_BASE_FOLDER": str(tmp_path)}), \
         patch("tools.sandbox.factory.provider_for_service") as for_service:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(svc._prepare_turn(
                agent_id=11, message="hi", conversation_id=None, db=MagicMock(),
                user_context={"user_id": 3, "app_id": 1}, turn_config=_config(),
            ))
    assert exc.value.status_code == 400
    for_service.assert_not_called()


@pytest.mark.parametrize("error", [SandboxProviderUnavailableError("nope"), SandboxServiceRetiredError("gone")])
def test_provider_unavailable_or_retired_degrades_to_no_code_interpreter(tmp_path, error):
    cfg = _config()
    ctx, _, legacy, _ = _prepare(_svc(), tmp_path, cfg, factory_side_effect=error)
    assert ctx.sandbox_handle is None and ctx.sandbox_provider is None and ctx.sandbox_session_key is None
    legacy.assert_not_called()  # no fallback to the env default
    assert cfg.diagnostics.sandbox_degraded is True and cfg.to_client_summary()["code_interpreter"] is False


def test_standard_agent_still_uses_resolve_provider(tmp_path):
    svc = _svc()
    agent = _agent()
    agent.is_internal_chat = False
    agent.enable_code_interpreter = True
    svc.agent_service.get_agent.return_value = agent
    fresh = _agent()
    fresh.is_internal_chat = False
    fresh.enable_code_interpreter = True
    svc.agent_execution_repo.get_agent_with_relationships.return_value = fresh
    conv = MagicMock(conversation_id=5, session_id="s")
    with patch("services.conversation_service.ConversationService.get_conversation", return_value=conv), \
         patch("services.agent_execution_service.get_app_config", return_value={"TMP_BASE_FOLDER": str(tmp_path)}), \
         patch("tools.sandbox.factory.provider_for_service") as for_service, \
         patch("tools.sandbox.factory.resolve_provider_and_service_id",
               return_value=(MagicMock(PROVIDER_NAME="fake"), 2)) as legacy:
        ctx = asyncio.run(svc._prepare_turn(
            agent_id=11, message="hi", conversation_id=5, db=MagicMock(), user_context={"user_id": 3, "app_id": 1},
        ))
    legacy.assert_called_once()
    for_service.assert_not_called()
    # agents (playground / API key / MCP / A2A / scheduled): no owner => only the global cap, as before this branch
    assert ctx.sandbox_handle._owner is None and ctx.sandbox_handle._chat is False
    assert ctx.sandbox_session_key == "conv_11_5"
