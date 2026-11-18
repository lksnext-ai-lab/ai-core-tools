"""Unit tests for the sandbox service end-of-service lifecycle (FR-15..FR-18, AD-14)."""

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from repositories.service_usage_repository import AgentRefs, ServiceSnapshot, UsageAppRow
from schemas.sandbox_service_schemas import CreateUpdateSandboxServiceSchema
from services.app_service import AppService
from services.agent_service import AgentService
from services.sandbox_service_service import SandboxServiceService
from services.service_lifecycle_service import LifecycleContext, ServiceLifecycleService
from tools.sandbox import factory
from tools.sandbox.factory import (
    SandboxProviderUnavailableError,
    SandboxServiceRetiredError,
    resolve_provider,
    resolve_provider_and_service_id,
)
from utils.service_lifecycle import RetiredServiceAssignmentError

NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)
PAST = datetime.now(timezone.utc) - timedelta(days=2)
FUTURE = datetime.now(timezone.utc) + timedelta(days=200)
MODULE = "services.service_lifecycle_service"


def _svc(service_id=1, app_id=10, eos=None, notice=None, provider="opensandbox"):
    return SimpleNamespace(
        service_id=service_id, app_id=app_id, name=f"sb{service_id}", provider=provider, endpoint=None,
        api_key=None, extra_config=None, end_of_service_at=eos, deprecation_notice=notice,
    )


def _agent(own=None, app_default=None):
    app = SimpleNamespace(default_sandbox_service=app_default)
    return SimpleNamespace(agent_id=5, app_id=10, app=app, sandbox_service=own)


@pytest.fixture
def lifecycle_caplog(caplog):
    """The project logger does not propagate to root, so attach caplog's handler directly."""
    from utils import service_lifecycle

    service_lifecycle.logger.addHandler(caplog.handler)
    caplog.set_level(logging.DEBUG)
    yield caplog
    service_lifecycle.logger.removeHandler(caplog.handler)


@pytest.fixture
def fake_registry(monkeypatch):
    instances = []

    class FakeProvider:
        PROVIDER_NAME = "opensandbox"

        def __init__(self, credentials=None):
            instances.append(self)

    monkeypatch.setattr(factory, "_PROVIDER_REGISTRY", {"opensandbox": FakeProvider})
    monkeypatch.delenv("SANDBOX_DEFAULT_PROVIDER", raising=False)
    return instances


# ==================== degrade enforcement ====================


class TestResolveRetired:
    def test_error_is_provider_unavailable_subclass(self):
        assert issubclass(SandboxServiceRetiredError, SandboxProviderUnavailableError)

    def test_retired_agent_service_raises_without_instantiating(self, fake_registry, lifecycle_caplog):
        caplog = lifecycle_caplog
        agent = _agent(own=_svc(eos=PAST, notice="use E2B"))
        with pytest.raises(SandboxServiceRetiredError) as exc:
            resolve_provider_and_service_id(agent)
        assert fake_registry == []
        assert "code interpreter is disabled" in str(exc.value) and "use E2B" in str(exc.value)
        blocked = [r for r in caplog.records if "service_lifecycle.blocked" in r.getMessage()]
        assert len(blocked) == 1 and "kind=sandbox" in blocked[0].getMessage()

    def test_retired_app_default_raises(self, fake_registry):
        agent = _agent(app_default=_svc(service_id=2, eos=PAST))
        with pytest.raises(SandboxServiceRetiredError):
            resolve_provider(agent)
        assert fake_registry == []

    def test_no_fallback_to_active_app_default(self, fake_registry):
        agent = _agent(own=_svc(eos=PAST), app_default=_svc(service_id=2))
        with pytest.raises(SandboxServiceRetiredError):
            resolve_provider_and_service_id(agent)
        assert fake_registry == []

    def test_future_date_and_active_service_resolve(self, fake_registry):
        provider, sid = resolve_provider_and_service_id(_agent(own=_svc(eos=FUTURE)))
        assert sid == 1 and len(fake_registry) == 1

    def test_env_default_path_unaffected(self, fake_registry):
        provider, sid = resolve_provider_and_service_id(_agent())
        assert sid is None and len(fake_registry) == 1

    def test_provider_rebuild_for_cleanup_works_for_retired_service(self, fake_registry):
        from services.sandbox_session_service import _provider_from_saved_state

        retired = _svc(eos=PAST)
        state = SimpleNamespace(sandbox_service_id=1, provider="opensandbox", sandbox_id="x")
        with patch("db.database.SessionLocal", return_value=MagicMock()), patch(
            "repositories.sandbox_service_repository.SandboxServiceRepository.get_by_id", return_value=retired
        ):
            provider = _provider_from_saved_state(state)
        assert provider is not None and len(fake_registry) == 1


# ==================== warnings ====================


def _snap(service_id, days):
    return ServiceSnapshot(service_id, f"sb{service_id}", 10, NOW + timedelta(days=days), None)


def _ctx(snaps, default=None):
    return LifecycleContext(
        warning_days=30, now=NOW, services={"sandbox": {s.service_id: s for s in snaps}},
        app_default_sandbox_service_id=default,
    )


def _refs(**kw):
    base = dict(agent_id=1, service_id=None, vision_service_id=None, transcription_service_id=None,
                video_ai_service_id=None, media_embedding_service_id=None, silo_id=None)
    base.update(kw)
    return AgentRefs(**base)


class TestSandboxWarnings:
    def test_own_service(self):
        ctx = _ctx([_snap(3, -1)])
        w = ServiceLifecycleService.warnings_for_agent(_refs(sandbox_service_id=3, enable_code_interpreter=True), ctx)
        assert [(x.kind, x.role, x.via, x.lifecycle_status) for x in w] == [("sandbox", "sandbox", None, "retired")]

    def test_inherited_from_app_default(self):
        ctx = _ctx([_snap(4, 10)], default=4)
        w = ServiceLifecycleService.warnings_for_agent(_refs(enable_code_interpreter=True), ctx)
        assert [(x.role, x.via, x.lifecycle_status) for x in w] == [("sandbox", "app default", "deprecated")]

    def test_own_service_wins_over_retired_default(self):
        ctx = _ctx([_snap(3, 365), _snap(4, -1)], default=4)
        w = ServiceLifecycleService.warnings_for_agent(_refs(sandbox_service_id=3, enable_code_interpreter=True), ctx)
        assert w == []

    def test_code_interpreter_off_gives_nothing(self):
        ctx = _ctx([_snap(3, -1), _snap(4, -1)], default=4)
        assert ServiceLifecycleService.warnings_for_agent(_refs(sandbox_service_id=3), ctx) == []
        assert ServiceLifecycleService.warnings_for_agent(_refs(), ctx) == []


# ==================== used-by ====================


def _usage_row(**kw):
    base = dict(agent_id=1, name="a", app_id=10, app_name="App", service_id=None, vision_service_id=None,
                transcription_service_id=None, video_ai_service_id=None, media_embedding_service_id=None,
                silo_id=None, sandbox_service_id=None, enable_code_interpreter=False)
    return SimpleNamespace(**{**base, **kw})


class TestSandboxUsage:
    def test_agent_roles(self):
        roles = ServiceLifecycleService.agent_roles
        assert roles(_usage_row(sandbox_service_id=7), "sandbox", 7) == ["sandbox"]
        assert roles(_usage_row(enable_code_interpreter=True), "sandbox", 7) == ["sandbox_app_default"]

    def test_get_usage_aggregates(self, monkeypatch):
        q = MagicMock()
        q.service_snapshot.return_value = ServiceSnapshot(7, "sb", None, PAST, None)
        q.sandbox_agents.return_value = [
            _usage_row(sandbox_service_id=7), _usage_row(agent_id=2, enable_code_interpreter=True)]
        q.sandbox_tasks.return_value = [SimpleNamespace(task_id=1, name="t", agent_id=2, app_id=10, app_name="App")]
        q.sandbox_apps.return_value = [UsageAppRow(10, "App")]
        monkeypatch.setattr(f"{MODULE}.ServiceUsageQueries", q)
        monkeypatch.setattr(ServiceLifecycleService, "warning_days", staticmethod(lambda db: 30))

        result = ServiceLifecycleService.get_usage(MagicMock(), "sandbox", 7, 10)

        assert result.kind == "sandbox" and result.lifecycle_status == "retired" and result.is_system
        assert [a.roles for a in result.agents] == [["sandbox"], ["sandbox_app_default"]]
        assert [(a.app_id, a.app_name) for a in result.apps_using_as_default] == [(10, "App")]
        assert [t.task_id for t in result.scheduled_tasks] == [1]
        assert result.silos == [] and result.repositories == [] and result.middlewares == []

    def test_foreign_app_service_hidden(self, monkeypatch):
        q = MagicMock()
        q.service_snapshot.return_value = ServiceSnapshot(7, "sb", 99, None, None)
        monkeypatch.setattr(f"{MODULE}.ServiceUsageQueries", q)
        assert ServiceLifecycleService.get_usage(MagicMock(), "sandbox", 7, 10) is None
        q.sandbox_agents.assert_not_called()


# ==================== API fields ====================


class TestSandboxApiFields:
    def test_list_item_and_detail_carry_status(self):
        svc = _svc(eos=PAST, notice="n")
        svc.create_date = None
        item = SandboxServiceService._to_list_item(svc, warning_days=30)
        detail = SandboxServiceService.to_detail(svc, 30)
        assert item.lifecycle_status == detail.lifecycle_status == "retired"
        assert detail.deprecation_notice == "n" and detail.end_of_service_at == PAST

    def test_apply_honours_fields_set(self):
        svc = _svc(eos=PAST, notice="keep")
        svc.service_id = 1
        data = CreateUpdateSandboxServiceSchema(name="n", provider="opensandbox", api_key="k")
        SandboxServiceService.apply_lifecycle_fields(svc, data, 1)
        assert svc.end_of_service_at == PAST and svc.deprecation_notice == "keep"
        cleared = CreateUpdateSandboxServiceSchema(
            name="n", provider="opensandbox", api_key="k", end_of_service_at=None)
        SandboxServiceService.apply_lifecycle_fields(svc, cleared, 1)
        assert svc.end_of_service_at is None and svc.deprecation_notice == "keep"

    def test_copy_leaves_fields_null(self):
        src = _svc(eos=PAST, notice="n")
        src.create_date = datetime(2024, 1, 1)
        created = {}

        def _create(db, s):
            created["svc"] = s
            s.service_id = 2
            return s

        with patch("services.sandbox_service_service.SandboxServiceRepository.get_by_id_and_app_id",
                   return_value=src), \
                patch("services.sandbox_service_service.SandboxServiceRepository.get_by_app_id", return_value=[]), \
                patch("services.sandbox_service_service.SandboxServiceRepository.get_system_services",
                      return_value=[]), \
                patch("services.sandbox_service_service.SandboxServiceRepository.create", side_effect=_create), \
                patch.object(SandboxServiceService, "get_sandbox_service_detail", return_value=MagicMock()), \
                patch.object(ServiceLifecycleService, "warning_days", return_value=30):
            SandboxServiceService.copy_sandbox_service(MagicMock(), 10, 1)
        assert created["svc"].end_of_service_at is None and created["svc"].deprecation_notice is None


# ==================== assignment ====================


class TestAssignment:
    def _data(self, sid):
        return {"app_id": 10, "sandbox_service_id": sid}

    def _validate(self, service, current=None):
        existing = SimpleNamespace(sandbox_service_id=current) if current is not None else None
        with patch("repositories.sandbox_service_repository.SandboxServiceRepository.get_by_id",
                   return_value=service):
            AgentService()._validate_referenced_resource_ids(MagicMock(), self._data(5), existing)

    def test_agent_rejects_new_retired(self):
        with pytest.raises(RetiredServiceAssignmentError):
            self._validate(_svc(service_id=5, eos=PAST))

    def test_agent_keeps_current_retired(self):
        self._validate(_svc(service_id=5, eos=PAST), current=5)

    def test_agent_ownership_before_lifecycle(self):
        with pytest.raises(ValueError) as exc:
            self._validate(_svc(service_id=5, app_id=99, eos=PAST))
        assert not isinstance(exc.value, RetiredServiceAssignmentError)

    def _app_validate(self, service, sid=5, current=None):
        with patch("repositories.sandbox_service_repository.SandboxServiceRepository.get_by_id",
                   return_value=service):
            AppService(MagicMock()).validate_default_sandbox_service(10, sid, current)

    def test_app_default_none_is_valid(self):
        self._app_validate(None, sid=None)

    def test_app_default_rejects_new_retired(self):
        with pytest.raises(RetiredServiceAssignmentError):
            self._app_validate(_svc(service_id=5, eos=PAST))

    def test_app_default_keeps_current_retired(self):
        self._app_validate(_svc(service_id=5, eos=PAST), current=5)

    def test_app_default_foreign_service_is_generic_error_even_if_retired(self):
        with pytest.raises(ValueError) as exc:
            self._app_validate(_svc(service_id=5, app_id=99, eos=PAST))
        assert not isinstance(exc.value, RetiredServiceAssignmentError)
        assert "retired" not in str(exc.value)

    def test_app_default_missing(self):
        with pytest.raises(ValueError):
            self._app_validate(None)


# ==================== logging and call context ====================


class TestLoggingAndContext:
    def test_context_reset_after_resolution_when_none_existed(self, fake_registry):
        from utils.service_lifecycle import get_service_call_context

        assert get_service_call_context() == {}
        with pytest.raises(SandboxServiceRetiredError):
            resolve_provider(_agent(own=_svc(eos=PAST)))
        assert get_service_call_context() == {}

    def test_existing_context_is_untouched_and_used(self, fake_registry, lifecycle_caplog):
        from utils.service_lifecycle import get_service_call_context, service_call_context

        with service_call_context(channel="chat", app_id=10, resource_type="agent", resource_id=99):
            with pytest.raises(SandboxServiceRetiredError):
                resolve_provider(_agent(own=_svc(eos=PAST)))
            assert get_service_call_context()["channel"] == "chat"
        blocked = [r for r in lifecycle_caplog.records if "service_lifecycle.blocked" in r.getMessage()]
        assert len(blocked) == 1 and "channel=chat" in blocked[0].getMessage()

    def test_one_warning_total_across_caller_catch(self, fake_registry, lifecycle_caplog):
        from tools import agentTools

        agent = _agent(own=_svc(eos=PAST))
        agent.enable_code_interpreter = True
        agentTools.logger.addHandler(lifecycle_caplog.handler)
        try:
            try:
                resolve_provider(agent)
            except SandboxProviderUnavailableError as exc:
                if isinstance(exc, SandboxServiceRetiredError):
                    agentTools.logger.debug("retired")
                else:
                    agentTools.logger.warning("%s", exc)
        finally:
            agentTools.logger.removeHandler(lifecycle_caplog.handler)
        warnings = [r for r in lifecycle_caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1 and "service_lifecycle.blocked" in warnings[0].getMessage()
