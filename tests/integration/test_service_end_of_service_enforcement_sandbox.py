"""Integration tests: retired sandbox services degrade the code interpreter (step_012, [SANDBOX]).

AC-23 (chat succeeds without code-interpreter tools; no sandbox, no fallback provider, WARNING logged;
moving the date restores the tools), AC-24 (reaper / destroy path still rebuilds the provider from the
stored service).
Real test DB; sandbox providers in ``tools.sandbox.factory._PROVIDER_REGISTRY`` are recording fakes.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from tests.integration._eos_enforcement_helpers import (  # noqa: F401  (fixtures)
    LLM_ANSWER,
    SessionProxy,
    ai_service,
    fake_sandbox_registry,
    future,
    guard_warnings,
    lifecycle_caplog,
    llm_builders,
    make_agent,
    past,
    sandbox_service,
)
from tests.integration.routers.internal._eos_helpers import iso, sandbox_payload

pytestmark = pytest.mark.integration

# AD-14: the guard is not de-duplicated across the layers that resolve the provider within one turn, so a
# retired sandbox service logs one WARNING at each of: (1) AgentExecutionService turn preparation
# (resolve_provider_and_service_id), (2) create_agent's prompt-languages probe, (3) create_agent's tool
# assembly. Pinned to the exact count so an accidental extra (or missing) resolution is noticed.
GUARD_WARNINGS_PER_TURN = 3


@pytest.fixture
def built_tools(monkeypatch):
    """Spy on the tool list handed to LangChain's ``create_agent`` (a list of tool-name lists, one per turn)."""
    import tools.agentTools as module

    real = module.create_langchain_agent
    captured = []

    def spy(*args, **kwargs):
        captured.append(sorted(getattr(t, "name", str(t)) for t in (kwargs.get("tools") or [])))
        return real(*args, **kwargs)

    monkeypatch.setattr(module, "create_langchain_agent", spy)
    return captured


def _chat(client, app, agent, headers):
    return client.post(f"/internal/apps/{app.app_id}/agents/{agent.agent_id}/chat",
                       data={"message": "run some code"}, headers=headers)


def _code_agent(db, app, llm, sandbox=None):
    return make_agent(db, app, llm, enable_code_interpreter=True,
                      sandbox_service_id=sandbox.service_id if sandbox is not None else None)


def _baseline_tools(client, db, app, llm, headers, built_tools):
    """Tool names of an agent without a code interpreter (what a degraded turn must look like)."""
    plain = make_agent(db, app, llm)
    assert _chat(client, app, plain, headers).status_code == 200
    return built_tools[-1]


class TestChatDegradesWithoutCodeInterpreter:
    """AC-23."""

    def test_agent_level_retired_sandbox_chat_succeeds_without_tools(
        self, client, db, fake_app, fake_ai_service, owner_headers, llm_builders, fake_sandbox_registry,
        built_tools, lifecycle_caplog,
    ):
        baseline = _baseline_tools(client, db, fake_app, fake_ai_service, owner_headers, built_tools)
        retired = sandbox_service(db, fake_app, name="sb-agent-retired", eos=past(1))
        agent = _code_agent(db, fake_app, fake_ai_service, retired)
        lifecycle_caplog.clear()

        resp = _chat(client, fake_app, agent, owner_headers)

        assert resp.status_code == 200, resp.text
        assert resp.json()["response"] == LLM_ANSWER
        assert built_tools[-1] == baseline  # no code-interpreter tools
        assert fake_sandbox_registry.instances == []  # no sandbox, no fallback provider
        warnings = guard_warnings(lifecycle_caplog)
        assert len(warnings) == GUARD_WARNINGS_PER_TURN
        for record in warnings:
            text = record.getMessage()
            assert f"service_id={retired.service_id}" in text
            assert "kind=sandbox" in text
            assert f"app_id={fake_app.app_id}" in text
            assert f"resource_id={agent.agent_id}" in text

    def test_app_default_retired_sandbox_chat_succeeds_without_tools(
        self, client, db, fake_app, fake_ai_service, owner_headers, llm_builders, fake_sandbox_registry,
        built_tools, lifecycle_caplog,
    ):
        baseline = _baseline_tools(client, db, fake_app, fake_ai_service, owner_headers, built_tools)
        retired = sandbox_service(db, fake_app, name="sb-default-retired", eos=past(1))
        fake_app.default_sandbox_service_id = retired.service_id
        db.flush()
        agent = _code_agent(db, fake_app, fake_ai_service, None)  # inherits the app default
        lifecycle_caplog.clear()

        resp = _chat(client, fake_app, agent, owner_headers)

        assert resp.status_code == 200, resp.text
        assert built_tools[-1] == baseline
        assert fake_sandbox_registry.instances == []
        warnings = guard_warnings(lifecycle_caplog)
        assert len(warnings) == GUARD_WARNINGS_PER_TURN
        for record in warnings:
            text = record.getMessage()
            assert f"service_id={retired.service_id}" in text and "kind=sandbox" in text
            assert f"app_id={fake_app.app_id}" in text and f"resource_id={agent.agent_id}" in text

    def test_retired_agent_level_service_does_not_fall_back_to_active_app_default(
        self, client, db, fake_app, fake_ai_service, owner_headers, llm_builders, fake_sandbox_registry,
        built_tools, lifecycle_caplog,
    ):
        baseline = _baseline_tools(client, db, fake_app, fake_ai_service, owner_headers, built_tools)
        active_default = sandbox_service(db, fake_app, name="sb-default-active")
        fake_app.default_sandbox_service_id = active_default.service_id
        retired = sandbox_service(db, fake_app, name="sb-agent-retired-2", eos=past(1))
        agent = _code_agent(db, fake_app, fake_ai_service, retired)
        lifecycle_caplog.clear()

        resp = _chat(client, fake_app, agent, owner_headers)

        assert resp.status_code == 200, resp.text
        assert built_tools[-1] == baseline  # D-10: no fallback to the active app default
        assert fake_sandbox_registry.instances == []
        assert len(guard_warnings(lifecycle_caplog)) == GUARD_WARNINGS_PER_TURN

    def test_active_sandbox_gets_the_code_interpreter_tools(
        self, client, db, fake_app, fake_ai_service, owner_headers, llm_builders, fake_sandbox_registry,
        built_tools, lifecycle_caplog,
    ):
        baseline = _baseline_tools(client, db, fake_app, fake_ai_service, owner_headers, built_tools)
        active = sandbox_service(db, fake_app, name="sb-active", eos=future(90))
        agent = _code_agent(db, fake_app, fake_ai_service, active)
        lifecycle_caplog.clear()

        resp = _chat(client, fake_app, agent, owner_headers)

        assert resp.status_code == 200, resp.text
        assert set(baseline) < set(built_tools[-1])  # the code-interpreter tools are present
        assert len(fake_sandbox_registry.instances) >= 1
        assert guard_warnings(lifecycle_caplog) == []

    def test_moving_the_date_to_the_future_restores_the_tools(
        self, client, db, fake_app, fake_ai_service, owner_headers, llm_builders, fake_sandbox_registry,
        built_tools, lifecycle_caplog,
    ):
        baseline = _baseline_tools(client, db, fake_app, fake_ai_service, owner_headers, built_tools)
        svc = sandbox_service(db, fake_app, name="sb-comes-back", eos=past(1))
        agent = _code_agent(db, fake_app, fake_ai_service, svc)

        assert _chat(client, fake_app, agent, owner_headers).status_code == 200
        assert built_tools[-1] == baseline
        assert fake_sandbox_registry.instances == []

        update = client.post(f"/internal/apps/{fake_app.app_id}/sandbox-services/{svc.service_id}",
                             json=sandbox_payload(name="sb-comes-back", end_of_service_at=iso(future(60))),
                             headers=owner_headers)
        assert update.status_code == 200, update.text
        lifecycle_caplog.clear()

        resp = _chat(client, fake_app, agent, owner_headers)

        assert resp.status_code == 200, resp.text
        assert set(baseline) < set(built_tools[-1])
        assert len(fake_sandbox_registry.instances) >= 1
        assert guard_warnings(lifecycle_caplog) == []


class TestDestroyPathStillBuildsTheProvider:
    """AC-24: cleanup must reach the live sandbox even though the service is retired."""

    @staticmethod
    def _state(service, sandbox_id="sbx-1", activity=None):
        # persisted format: naive UTC + "Z"
        stamp = (activity or datetime.now(timezone.utc)).replace(tzinfo=None).isoformat() + "Z"
        return json.dumps({
            "provider": "opensandbox", "session_key": "k", "sandbox_id": sandbox_id, "updated_at": stamp,
            "last_activity_at": stamp, "sandbox_service_id": service.service_id,
        })

    def test_destroy_persisted_sandbox_uses_the_stored_retired_service(
        self, db, fake_app, fake_sandbox_registry, monkeypatch, lifecycle_caplog
    ):
        import db.database as database
        from services.sandbox_session_service import _destroy_persisted_sandbox, _load_sandbox_state
        from tools.sandbox.factory import _credentials_from_service

        retired = sandbox_service(db, fake_app, name="sb-reap-retired", eos=past(3))
        monkeypatch.setattr(database, "SessionLocal", lambda: SessionProxy(db))
        state = _load_sandbox_state(type("C", (), {"sandbox_state": self._state(retired)})())

        assert _destroy_persisted_sandbox(state) is True

        assert len(fake_sandbox_registry.instances) == 1
        provider = fake_sandbox_registry.instances[0]
        assert provider.credentials == _credentials_from_service(retired)  # the tenant's credentials
        assert provider.credentials["api_key"] == retired.api_key
        assert provider.destroyed_ids == ["sbx-1"]
        assert guard_warnings(lifecycle_caplog) == []

    def test_reaper_destroys_stale_sandbox_of_a_retired_service_and_clears_state(
        self, db, fake_app, fake_ai_service, fake_sandbox_registry, monkeypatch, lifecycle_caplog
    ):
        import db.database as database
        from models.conversation import Conversation
        from services.sandbox_session_service import sandbox_session_service

        retired = sandbox_service(db, fake_app, name="sb-reap-retired-2", eos=past(3))
        agent = _code_agent(db, fake_app, fake_ai_service, retired)
        conv = Conversation(agent_id=agent.agent_id, session_id="eos-reap-session", sandbox_session_id="k",
                            sandbox_state=self._state(retired, "sbx-2", datetime.now(timezone.utc) - timedelta(days=30)))
        db.add(conv)
        db.flush()
        monkeypatch.setattr(database, "SessionLocal", lambda: SessionProxy(db))

        sandbox_session_service._reap_stale(db=db)

        provider = next(p for p in fake_sandbox_registry.instances if "sbx-2" in p.destroyed_ids)
        assert provider.credentials["api_key"] == retired.api_key
        db.refresh(conv)
        assert conv.sandbox_state is None and conv.sandbox_session_id is None  # destroy confirmed -> cleared
        assert guard_warnings(lifecycle_caplog) == []
