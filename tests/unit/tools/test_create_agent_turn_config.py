"""create_agent(turn_config=...) — per-turn override of the hidden internal-chat agent."""
import asyncio
import copy
from types import MappingProxyType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.tools import StructuredTool

import tools.agentTools as agentTools
from services.internal_chat.resolved_config import (
    InternalChatSessionError,
    McpConnectionSpec,
    ResolvedChatConfig,
)
from tools.agentTools import MCPClientManager, compute_thread_id, create_agent


class WatchedAgent(SimpleNamespace):
    """Agent stand-in that fails on any attribute assignment after construction."""

    def __init__(self, **kw):
        super().__init__(**kw)
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, name, value):
        if getattr(self, "_frozen", False):
            raise AssertionError(f"agent mutated: {name}")
        super().__setattr__(name, value)


def _agent(**over):
    attrs = dict(
        agent_id=7, app_id=1, kind="internal_chat", is_internal_chat=True,
        has_memory=True, enable_code_interpreter=False,
        system_prompt="AGENT PROMPT", output_parser_id=None,
        exposed_chat_filters=[], middleware_associations=[], tool_associations=[],
        server_tools=["web_search"], ai_service=None, vision_service_rel=None,
        silo_id=None, silo=None, skill_associations=[], mcp_associations=[],
        skill_router_enabled=False, temperature=0.5, rag_k=5,
        rag_search_type="similarity", rag_score_threshold=None,
        rag_fixed_filters=None, rag_max_retrieval_calls=None,
    )
    attrs.update(over)
    return WatchedAgent(**attrs)


def _skill(skill_id, name):
    return SimpleNamespace(
        skill_id=skill_id, name=name, content=f"content {name}", description=f"d {name}",
        is_enabled=True, app_id=1,
    )


def _spec(config_id, server, headers=None):
    conn = {server: {"url": f"https://{server}.example/mcp", "transport": "streamable_http",
                     "headers": dict(headers or {})}}
    return McpConnectionSpec(config_id, server, MappingProxyType(conn), True)


def _config(tag, *, silo=True):
    return ResolvedChatConfig(
        app_id=1,
        ai_service=SimpleNamespace(name=f"svc-{tag}", provider="OpenAI"),
        ai_service_id=1, ai_service_name=f"svc-{tag}",
        ai_service_is_system=False, ai_service_provider="OpenAI", ai_service_model=f"model-{tag}",
        silo=SimpleNamespace(silo_id=ord(tag), name=f"silo-{tag}", metadata_definition=None,
                             vector_db_type="PGVECTOR") if silo else None,
        silo_id=ord(tag) if silo else None, silo_name=f"silo-{tag}" if silo else None,
        skills=(_skill(ord(tag), f"skill-{tag}"),), skill_ids=(ord(tag),),
        skill_names=(f"skill-{tag}",),
        mcp_connections=(_spec(ord(tag), f"mcp{tag}"),),
        mcp_config_ids=(ord(tag),), mcp_config_names=(f"mcp{tag}",),
        system_prompt=f"PROMPT-{tag}",
    )


def _tool(name):
    return StructuredTool.from_function(func=lambda q="": name, name=name, description=name)


class _Harness:
    def __init__(self):
        self.graph_calls = []
        self.llm_services = []
        self.mcp_connections = []
        self.retriever_silos = []
        self.skill_loader_names = []
        self.middleware_llms = []
        self.mcp_entered = None  # asyncio.Barrier proving turns overlap (set by tests)

    def patches(self):
        h = self

        def fake_llm_from_service(service, temperature=None, is_vision=False):
            h.llm_services.append(service)
            return SimpleNamespace(tag=service.name)

        def fake_graph(**kw):
            h.graph_calls.append(kw)
            return MagicMock()

        class FakeMCP:
            def __init__(self, connections=None, **_):
                h.mcp_connections.append(connections)
                self._c = connections

            async def get_tools(self):
                if h.mcp_entered is not None:
                    await asyncio.wait_for(h.mcp_entered.wait(), timeout=5)
                await asyncio.sleep(0)
                return [_tool("mcp_" + "_".join(self._c))]

        def fake_retriever(silo, *a, **k):
            h.retriever_silos.append(silo)
            return _tool(f"retriever_{silo.name}")

        def fake_loader(snapshots, **kw):
            h.skill_loader_names.append([s.name for s in snapshots])
            return _tool("load_skill")

        def fake_middlewares(agent, llm, *a, **k):
            h.middleware_llms.append(llm)
            return []

        return [
            patch("tools.aiServiceTools.create_llm_from_service", side_effect=fake_llm_from_service),
            patch("tools.agentTools.create_langchain_agent", side_effect=fake_graph),
            patch("tools.agentTools.get_retriever_tool", side_effect=fake_retriever),
            patch("tools.agentTools.MultiServerMCPClient", FakeMCP),
            patch("tools.agentTools.create_skill_loader_tool", side_effect=fake_loader),
            patch("tools.agentTools.create_skill_file_reader_tool", return_value=None),
            patch("services.skill_package_service.build_skill_tool_providers",
                  return_value=(None, None, None)),
            patch("tools.middleware.factory.build_agent_middlewares", side_effect=fake_middlewares),
            patch.object(agentTools.CheckpointerCacheService, "get_async_checkpointer",
                         new=AsyncMock(return_value=MagicMock())),
        ]

    def __enter__(self):
        for p in self.patches():
            p.start()
        return self

    def __exit__(self, *exc):
        patch.stopall()


def _tool_names(call):
    return sorted(t.name for t in call["tools"] if hasattr(t, "name"))


@pytest.mark.asyncio
async def test_concurrent_turns_are_isolated_and_agent_is_untouched():
    mcp_cfg = SimpleNamespace(name="own", ssl_verify=True, config_id=1,
                              to_connection_dict=lambda: {"own": {"url": "https://o", "headers": {"k": "v"}}})
    agent = _agent(mcp_associations=[SimpleNamespace(mcp=mcp_cfg)])
    before = copy.copy(vars(agent))
    nested_before = copy.deepcopy(mcp_cfg.to_connection_dict())
    with _Harness() as h:
        h.mcp_entered = asyncio.Barrier(2)  # both turns must be inside get_tools together
        await asyncio.gather(
            create_agent(agent, session_id="conv_7_a", turn_config=_config("A")),
            create_agent(agent, session_id="conv_7_b", turn_config=_config("B")),
        )

    assert vars(agent) == before
    assert mcp_cfg.to_connection_dict() == nested_before
    assert len(h.graph_calls) == 2
    by_tag = {c["model"].tag: c for c in h.graph_calls}
    assert set(by_tag) == {"svc-A", "svc-B"}
    for tag in "AB":
        call = by_tag[f"svc-{tag}"]
        assert call["system_prompt"].startswith(f"PROMPT-{tag}")
        assert "AGENT PROMPT" not in call["system_prompt"]
        assert f"skill-{tag}" in call["system_prompt"]
        other = "B" if tag == "A" else "A"
        assert f"skill-{other}" not in call["system_prompt"]
        names = _tool_names(call)
        assert f"retriever_silo-{tag}" in names
        assert f"mcp_mcp{tag}" in names
        assert f"retriever_silo-{other}" not in names
        assert f"mcp_mcp{other}" not in names
        assert "response_format" not in call
    assert sorted(h.skill_loader_names) == [["skill-A"], ["skill-B"]]
    # Summarization middleware is built with each turn's own LLM.
    assert sorted(m.tag for m in h.middleware_llms) == ["svc-A", "svc-B"]


@pytest.mark.asyncio
async def test_turn_config_requires_session_id():
    agent = _agent()
    with _Harness() as h:
        with pytest.raises(InternalChatSessionError):
            await create_agent(agent, turn_config=_config("A"))
        with pytest.raises(InternalChatSessionError):
            await create_agent(agent, session_id="", turn_config=_config("A"))
    assert h.graph_calls == []


@pytest.mark.asyncio
async def test_turn_config_without_silo_or_mcp_builds_neither_retriever_nor_mcp(tmp_path):
    cfg = _config("A", silo=False)
    cfg = ResolvedChatConfig(**{**{f: getattr(cfg, f) for f in cfg.__slots__},
                                "mcp_connections": (), "mcp_config_ids": (), "mcp_config_names": ()})
    # An agent that DOES have a silo / MCP / output parser / tools: all ignored.
    agent = _agent(
        ai_service=SimpleNamespace(name="agent-svc", provider="OpenAI"),
        silo_id=3, silo=SimpleNamespace(silo_id=3, name="agent-silo"),
        mcp_associations=[SimpleNamespace(mcp=SimpleNamespace(
            name="x", ssl_verify=True, config_id=9,
            to_connection_dict=lambda: {"agent-mcp": {"url": "https://a", "transport": "sse"}}))],
        output_parser_id=5, enable_code_interpreter=True,
        tool_associations=[SimpleNamespace(tool=object())],
    )
    with _Harness() as h:
        provider = MagicMock()
        with patch("tools.agentTools.resolve_provider") as resolve, \
             patch("tools.agentTools.create_sandbox_repl_tools") as repl, \
             patch("tools.agentTools.create_sandbox_builtin_tools") as builtin, \
             patch("tools.agentTools.discover_tool", new=AsyncMock()) as discover:
            await create_agent(agent, session_id="conv_7_a", working_dir=str(tmp_path),
                               sandbox_provider=provider, turn_config=cfg)
    assert h.retriever_silos == []
    assert h.mcp_connections == []
    resolve.assert_not_called()
    repl.assert_not_called()
    builtin.assert_not_called()
    provider.create_sandbox.assert_not_called()
    discover.assert_not_awaited()
    call = h.graph_calls[0]
    assert "response_format" not in call
    assert "<code_interpreter>" not in call["system_prompt"]
    assert not any(isinstance(t, dict) for t in call["tools"])  # no provider-side web_search
    assert not any(n.startswith("python_repl") for n in _tool_names(call))


@pytest.mark.asyncio
async def test_without_turn_config_agent_values_are_used():
    silo = SimpleNamespace(silo_id=3, name="agent-silo", metadata_definition=None, vector_db_type="PGVECTOR")
    agent = _agent(
        ai_service=SimpleNamespace(name="agent-svc", provider="OpenAI"), silo_id=3, silo=silo,
        skill_associations=[SimpleNamespace(skill=_skill(1, "agent-skill"))],
        mcp_associations=[SimpleNamespace(mcp=SimpleNamespace(
            name="m", ssl_verify=True, config_id=2,
            to_connection_dict=lambda: {"agent-mcp": {"url": "https://a", "transport": "sse"}}))],
    )
    with _Harness() as h:
        await create_agent(agent)
    call = h.graph_calls[0]
    assert call["model"].tag == "agent-svc"
    assert call["system_prompt"].startswith("AGENT PROMPT")
    assert "agent-skill" in call["system_prompt"]
    assert h.retriever_silos == [silo]
    assert list(h.mcp_connections[0]) == ["agent-mcp"]
    assert h.skill_loader_names == [["agent-skill"]]


@pytest.mark.asyncio
async def test_silo_override_does_not_assign_on_agent_and_reaches_resolve_search_params():
    cfg = _config("A")
    agent = _agent()
    seen = {}
    real = __import__("services.silo_service", fromlist=["x"]).resolve_search_params

    def spy(a, caller, *, silo=None):
        seen["silo"] = silo
        return real(a, caller, silo=silo)

    with _Harness(), patch("services.silo_service.resolve_search_params", side_effect=spy):
        await create_agent(agent, session_id="conv_7_a", turn_config=cfg)
    assert seen["silo"] is cfg.silo
    assert agent.silo is None


@pytest.mark.asyncio
async def test_mcp_override_does_not_mutate_spec_connections():
    spec = _spec(1, "srv", headers={"X-Existing": "1"})
    original = copy.deepcopy(dict(spec.connections))
    captured = {}

    class FakeClient:
        def __init__(self, connections=None, **_):
            captured["c"] = connections

    with patch("tools.agentTools.MultiServerMCPClient", FakeClient), \
         patch("tools.agentTools.get_user_token_from_context", return_value="tok"):
        await MCPClientManager().get_client(
            None, {"oauth": True, "token": "t"}, connections_override=[spec]
        )
        # A second turn with the same spec must see pristine data too.
        await MCPClientManager().get_client(None, None, connections_override=[spec])

    assert dict(spec.connections) == original
    assert "Authorization" not in spec.connections["srv"]["headers"]
    assert captured["c"]["srv"]["headers"] == {"X-Existing": "1"}


@pytest.mark.asyncio
async def test_mcp_override_ssl_and_empty_override():
    spec = McpConnectionSpec(
        1, "n", {"s": {"url": "https://s", "transport": "sse"}}, ssl_verify=False)
    captured = {}

    class FakeClient:
        def __init__(self, connections=None, **_):
            captured["c"] = connections

    with patch("tools.agentTools.MultiServerMCPClient", FakeClient):
        await MCPClientManager().get_client(None, None, connections_override=[spec])
        assert "httpx_client_factory" in captured["c"]["s"]
        assert "httpx_client_factory" not in spec.connections["s"]
        # Empty override means "no MCP", never the agent's own associations.
        agent = _agent(mcp_associations=[SimpleNamespace(mcp=SimpleNamespace(
            name="m", ssl_verify=True, to_connection_dict=lambda: {"a": {"url": "u"}}))])
        assert await MCPClientManager().get_client(agent, None, connections_override=()) is None


def test_compute_thread_id_require_session():
    agent = _agent()
    assert compute_thread_id(agent, "conv_7_a", require_session=True) == "thread_7_conv_7_a"
    with pytest.raises(InternalChatSessionError):
        compute_thread_id(agent, None, require_session=True)
    with pytest.raises(InternalChatSessionError):
        compute_thread_id(agent, "", require_session=True)
    # Legacy behaviour unchanged.
    assert compute_thread_id(agent, None) == "thread_7"
    assert compute_thread_id(agent, "s") == "thread_7_s"


def test_resolved_config_is_frozen_and_serialisable():
    cfg = _config("A")
    with pytest.raises(Exception):
        cfg.system_prompt = "x"
    assert cfg.to_selection_dict() == {
        "ai_service_id": 1, "silo_id": ord("A"), "skill_ids": [ord("A")], "mcp_config_ids": [ord("A")],
    }
    assert "mcpA" in str(cfg.to_trace_metadata())
    assert "https://" not in str(cfg.to_trace_metadata())


def test_get_llm_override_uses_override_without_touching_agent():
    from tools.aiServiceTools import get_llm
    agent = _agent(ai_service=SimpleNamespace(name="own"))
    override = SimpleNamespace(name="override")
    with patch("tools.aiServiceTools.create_llm_from_service") as m:
        get_llm(agent, ai_service_override=override)
        assert m.call_args.args[0] is override
        get_llm(agent)
        assert m.call_args.args[0] is agent.ai_service


def test_resolve_skills_matches_resolve_agent_skills():
    from tools.skill_tools import resolve_agent_skills, resolve_skills
    sys_skill = SimpleNamespace(skill_id=1, name="Dup", is_enabled=True, app_id=None)
    app_skill = SimpleNamespace(skill_id=2, name="dup", is_enabled=True, app_id=5)
    off = SimpleNamespace(skill_id=3, name="off", is_enabled=False, app_id=5)
    assocs = [SimpleNamespace(skill=s) for s in (sys_skill, app_skill, off)] + [SimpleNamespace(skill=None)]
    assert resolve_agent_skills(assocs) == resolve_skills([sys_skill, app_skill, off]) == [app_skill]


@pytest.mark.asyncio
async def test_turn_config_rejects_wrong_app_and_non_internal_agent():
    with _Harness() as h:
        with pytest.raises(InternalChatSessionError):
            await create_agent(_agent(app_id=2), session_id="s", turn_config=_config("A"))
        with pytest.raises(InternalChatSessionError):
            await create_agent(_agent(is_internal_chat=False, kind="standard"),
                               session_id="s", turn_config=_config("A"))
    assert h.graph_calls == []


@pytest.mark.asyncio
async def test_turn_config_ignores_agent_middlewares_and_filters():
    agent = _agent(middleware_associations=[SimpleNamespace(middleware=None)],
                   exposed_chat_filters=["f"], skill_router_enabled=True)
    with _Harness() as h:
        with patch("tools.agentTools.build_chat_filter_prompt_block") as block:
            await create_agent(agent, session_id="s", search_params={"filter": {"f": 1}},
                               turn_config=_config("A"))
        block.assert_not_called()
    assert len(h.middleware_llms) == 1


def test_build_agent_middlewares_ignore_flag_skips_associations():
    from tools.middleware.factory import build_agent_middlewares
    bad = SimpleNamespace(middleware=SimpleNamespace(
        middleware_type="x", middleware_id=1, config={}))
    agent = _agent(middleware_associations=[bad])
    llm = SimpleNamespace(profile=None)
    with patch("tools.middleware.factory._summarization", return_value=None) as summ, \
         patch("tools.middleware.factory.parse_middleware_config") as parse:
        assert build_agent_middlewares(agent, llm, ignore_agent_middlewares=True) == []
        parse.assert_not_called()
        assert summ.call_args.args[2] is None


def test_compute_thread_id_require_session_ignores_has_memory():
    agent = _agent(has_memory=False)
    assert compute_thread_id(agent, "conv_7_a", require_session=True) == "thread_7_conv_7_a"
    assert compute_thread_id(agent, "conv_7_a") == "thread_7"


def test_repr_does_not_leak_secrets():
    secret = "SUPER-SECRET-TOKEN"
    spec = _spec(1, "srv", headers={"Authorization": secret})
    cfg = ResolvedChatConfig(**{**{f: getattr(_config("A"), f) for f in ResolvedChatConfig.__slots__},
                                "mcp_connections": (spec,)})
    assert secret not in repr(cfg)
    assert secret not in repr(spec)


def test_resolved_config_rejects_missing_service_and_non_tuples():
    base = {f: getattr(_config("A"), f) for f in ResolvedChatConfig.__slots__}
    with pytest.raises(ValueError):
        ResolvedChatConfig(**{**base, "ai_service": None})
    with pytest.raises(TypeError):
        ResolvedChatConfig(**{**base, "skills": []})
    with pytest.raises(TypeError):
        ResolvedChatConfig(**{**base, "mcp_connections": []})


def test_resolved_config_import_is_light():
    import subprocess
    import sys
    import os
    backend = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend"))
    code = (
        f"import sys; sys.path.insert(0, {backend!r}); import services.internal_chat.resolved_config; "
        "bad=[m for m in sys.modules if m=='tools' or m.startswith('tools.') or "
        "m.startswith('sqlalchemy') or (m.startswith('services.') and "
        "not m.startswith('services.internal_chat'))]; "
        "print(bad); sys.exit(1 if bad else 0)"
    )
    r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.asyncio
async def test_legacy_mcp_path_merges_headers_ssl_and_skips_bad_config():
    def good():
        return {"secure": {"url": "https://s", "transport": "sse"}}

    def insecure():
        return {"insecure": {"url": "https://i", "transport": "sse"}}

    def bad():
        raise ValueError("boom")

    def cfg(fn, ssl, cid):
        return SimpleNamespace(mcp=SimpleNamespace(
            name=f"c{cid}", ssl_verify=ssl, config_id=cid, to_connection_dict=fn))

    agent = _agent(mcp_associations=[cfg(good, True, 1), cfg(insecure, False, 2), cfg(bad, True, 3)])
    captured = {}

    class FakeClient:
        def __init__(self, connections=None, **_):
            captured["c"] = connections

    with patch("tools.agentTools.MultiServerMCPClient", FakeClient):
        await MCPClientManager().get_client(agent, {"oauth": True, "token": "t"})
    c = captured["c"]
    assert set(c) == {"secure", "insecure"}
    for name in c:
        assert "Authorization" in c[name]["headers"]
    assert "httpx_client_factory" in c["insecure"]
    assert "httpx_client_factory" not in c["secure"]


@pytest.mark.asyncio
async def test_empty_override_returns_none_without_warning():
    with patch.object(agentTools.logger, "warning") as warn:
        assert await MCPClientManager().get_client(_agent(), None, connections_override=()) is None
    warn.assert_not_called()


def test_mcp_log_view_has_only_names_and_transports():
    view = agentTools._summarize_mcp_connections(
        {"s": {"url": "https://x/?api_key=SECRET", "transport": "sse", "headers": {"A": "SECRET"}}})
    assert view == {"s": "sse"}


@pytest.mark.asyncio
@pytest.mark.parametrize("has_memory", [False, None])
async def test_turn_config_requires_agent_memory(has_memory):
    with _Harness() as h:
        with pytest.raises(InternalChatSessionError):
            await create_agent(_agent(has_memory=has_memory), session_id="s",
                               turn_config=_config("A"))
    assert h.graph_calls == []


@pytest.mark.asyncio
async def test_mcp_spec_unchanged_with_token_and_insecure_ssl():
    spec = McpConnectionSpec(1, "n", {"s": {"url": "https://s", "transport": "sse"}}, ssl_verify=False)
    original = copy.deepcopy(dict(spec.connections))
    captured = {}

    class FakeClient:
        def __init__(self, connections=None, **_):
            captured["c"] = connections

    with patch("tools.agentTools.MultiServerMCPClient", FakeClient):
        await MCPClientManager().get_client(None, {"oauth": True, "token": "t"},
                                            connections_override=[spec])
    assert "Authorization" in captured["c"]["s"]["headers"]
    assert "httpx_client_factory" in captured["c"]["s"]
    assert dict(spec.connections) == original


@pytest.mark.asyncio
async def test_mcp_failure_is_reported_and_a_successful_retry_clears_it():
    """create_agent can run twice in one turn: only the last attempt's MCP outcome may stay in the diagnostics."""
    cfg = _config("A")
    agent = _agent()
    broken = {"on": True}

    async def get_tools(self):
        if broken["on"]:
            raise ConnectionError("mcp down")
        return [_tool("mcp_ok")]

    with _Harness():
        fake_client = agentTools.MultiServerMCPClient  # the harness' fake class
        original = fake_client.get_tools
        fake_client.get_tools = get_tools
        try:
            await create_agent(agent, session_id="conv_7_a", turn_config=cfg)
            assert cfg.diagnostics.mcp_unavailable_ids == [ord("A")]
            broken["on"] = False
            await create_agent(agent, session_id="conv_7_a", turn_config=cfg)  # the retry connects
            assert cfg.diagnostics.mcp_unavailable_ids == []
        finally:
            fake_client.get_tools = original


# --------------------------------------------------------------------------- code interpreter (App default sandbox)


def _with_sandbox(cfg, sandbox=True):
    import dataclasses

    if not sandbox:
        return cfg
    return dataclasses.replace(
        cfg,
        sandbox_service=SimpleNamespace(service_id=5, name="sbx", provider="e2b"),
        sandbox_enabled=True, sandbox_service_id=5, sandbox_service_name="sbx", sandbox_provider="e2b",
    )


def _provider():
    provider = MagicMock()
    provider.get_supported_languages.return_value = ["python", "bash"]
    return provider


def test_effective_surface_chat_code_interpreter_follows_the_turn_config():
    on = agentTools._effective_surface(_agent(), _with_sandbox(_config("A")))
    off = agentTools._effective_surface(_agent(enable_code_interpreter=True), _config("A"))
    assert on.is_chat and on.code_interpreter_enabled is True
    # The hidden agent's own flag never enables it; the turn config does.
    assert off.code_interpreter_enabled is False
    # Everything else the Chat does not expose stays off with the sandbox on.
    assert on.server_tools == () and on.tool_associations == () and on.use_output_parser is False
    assert agentTools._effective_surface(_agent(enable_code_interpreter=True), None).code_interpreter_enabled is True


@pytest.mark.asyncio
async def test_chat_turn_with_sandbox_gets_code_interpreter_block_and_tools(tmp_path):
    provider, handle = _provider(), MagicMock()
    with _Harness() as h:
        with patch("tools.agentTools.resolve_provider") as resolve, \
             patch("tools.agentTools.create_sandbox_repl_tools", return_value=[_tool("python_repl")]) as repl, \
             patch("tools.agentTools.create_sandbox_builtin_tools", return_value=[_tool("Bash")]) as builtin, \
             patch("tools.agentTools.create_skill_loader_tool") as loader:
            loader.return_value = _tool("load_skill")
            await create_agent(
                _agent(), session_id="conv_7_a", working_dir=str(tmp_path),
                sandbox_provider=provider, sandbox_handle=handle, sandbox_session_key="conv_7_55",
                turn_config=_with_sandbox(_config("A")),
            )
    resolve.assert_not_called()  # never resolved from the shared hidden agent
    repl.assert_called_once()
    builtin.assert_called_once()
    assert repl.call_args.kwargs["session_key"] == "conv_7_55"
    call = h.graph_calls[0]
    assert "<code_interpreter>" in call["system_prompt"]
    assert str(tmp_path) not in call["system_prompt"]  # never the server's absolute path in a Chat prompt
    assert {"python_repl", "Bash"} <= set(_tool_names(call))
    # load_skill receives the turn's handle/provider so it can materialise the skill in the sandbox.
    assert loader.call_args.kwargs["sandbox_handle"] is handle
    assert loader.call_args.kwargs["sandbox_provider"] is provider
    assert loader.call_args.kwargs["payload_provider"] is None  # harness stub of build_skill_tool_providers


@pytest.mark.asyncio
async def test_chat_turn_without_prepared_provider_never_resolves_from_the_agent(tmp_path):
    """Sandbox configured on the turn but prepare degraded (provider None): no tools, no env fallback."""
    with _Harness() as h:
        with patch("tools.agentTools.resolve_provider") as resolve, \
             patch("tools.agentTools.create_sandbox_repl_tools") as repl, \
             patch("tools.agentTools.create_sandbox_builtin_tools") as builtin:
            await create_agent(
                _agent(enable_code_interpreter=True), session_id="conv_7_a", working_dir=str(tmp_path),
                turn_config=_with_sandbox(_config("A")),
            )
    resolve.assert_not_called()
    repl.assert_not_called()
    builtin.assert_not_called()
    assert "<code_interpreter>" not in h.graph_calls[0]["system_prompt"]


@pytest.mark.asyncio
async def test_chat_turn_with_provider_but_no_handle_creates_no_fallback_sandbox(tmp_path):
    provider = _provider()
    with _Harness() as h:
        with patch("tools.agentTools.resolve_provider") as resolve, \
             patch("tools.agentTools.create_sandbox_repl_tools") as repl:
            await create_agent(
                _agent(), session_id="conv_7_a", working_dir=str(tmp_path),
                sandbox_provider=provider, turn_config=_with_sandbox(_config("A")),
            )
    resolve.assert_not_called()
    provider.create_sandbox.assert_not_called()
    repl.assert_not_called()
    assert h.graph_calls


@pytest.mark.asyncio
async def test_chat_turn_without_sandbox_service_never_calls_resolve_provider(tmp_path):
    with _Harness():
        with patch("tools.agentTools.resolve_provider") as resolve:
            await create_agent(_agent(enable_code_interpreter=True), session_id="conv_7_a",
                               working_dir=str(tmp_path), turn_config=_config("A"))
    resolve.assert_not_called()
