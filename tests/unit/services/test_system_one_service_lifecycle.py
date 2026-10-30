"""Unit tests for the System One service end-of-service lifecycle (mirrors test_sandbox_service_lifecycle.py).

Repositories, the external server and the warning-days setting are mocked: no database, no network.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import TypeAdapter, ValidationError

from models.system_one_agent import SystemOneAgent
from models.system_one_service import SystemOneService
from schemas.export_schemas import ExportSystemOneServiceSchema
from schemas.system_one_schemas import Question
from schemas.system_one_service_schemas import CreateUpdateSystemOneServiceSchema
from services import system_one_service_service as module
from services.service_lifecycle_service import ServiceLifecycleService
from services.system_one_evaluator import SystemOneEvaluator
from services.system_one_porting import export_system_one_service, import_system_one_service
from services.system_one_service_service import SystemOneServiceService
from tools.system_one_tool import IACTSystemOneTool
from utils.error_handlers import AppError
from utils.service_lifecycle import (
    SERVICE_KIND_SYSTEM_ONE,
    ServiceRetiredError,
    compute_lifecycle_status,
    system_one_retired_message,
)

NOW = datetime.now(timezone.utc)
PAST = NOW - timedelta(days=2)
SOON = NOW + timedelta(days=10)          # inside the 30-day warning window: deprecated
FAR = NOW + timedelta(days=200)          # active
EOS_DATE = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _svc(service_id=1, eos=None, notice=None):
    return SystemOneService(
        service_id=service_id, app_id=10, name="Nimble", endpoint="http://so.test", api_key="secret-token",
        description="nimble-latest", extra_config='{"max_concurrency": 2}', create_date=datetime(2026, 10, 9),
        end_of_service_at=eos, deprecation_notice=notice,
    )


def _data(**kw):
    base = dict(name="Nimble", endpoint="http://so.test", api_key="tok", model="nimble-latest", max_concurrency=2)
    return CreateUpdateSystemOneServiceSchema(**{**base, **kw})


QUESTION = TypeAdapter(Question).validate_python(
    {"key": "is_urgent", "type": "noul", "instructions": "Is this urgent?"})


def _agent(service):
    agent = SystemOneAgent(agent_id=3, name="Triage Bot", description="Routes tickets", app_id=10,
                           max_state_chars=6000, questions=[QUESTION.model_dump(mode="json")])
    agent.system_one_service = service
    return agent


def _stamp(s):
    s.service_id = s.service_id or 99     # what the database would assign on insert
    return s


@pytest.fixture(autouse=True)
def warning_days():
    with patch.object(ServiceLifecycleService, "warning_days", return_value=30):
        yield


@pytest.fixture
def repo():
    with patch.object(module, "SystemOneServiceRepository") as r:
        r.create.side_effect = lambda db, s: _stamp(s)
        r.update.side_effect = lambda db, s: s
        r.get_agents_using.return_value = []
        yield r


@pytest.fixture
def lifecycle_caplog(caplog):
    """The project logger does not propagate to root, so attach caplog's handler directly."""
    from utils import service_lifecycle

    service_lifecycle.logger.addHandler(caplog.handler)
    caplog.set_level(logging.DEBUG)
    yield caplog
    service_lifecycle.logger.removeHandler(caplog.handler)


# ==================== kind, message, error ====================


def test_kind_and_retired_message_mention_the_agents_and_the_notice():
    assert SERVICE_KIND_SYSTEM_ONE == "system_one"
    message = system_one_retired_message("Nimble", EOS_DATE, "Use Nimble 2.")
    assert message == (
        "Service Nimble was retired on 2026-06-01. Agents using it cannot evaluate text until another "
        "System One service is selected. Use Nimble 2."
    )


def test_retired_error_for_a_system_one_service_is_a_409_with_the_kind_message():
    err = ServiceRetiredError(_svc(eos=EOS_DATE), SERVICE_KIND_SYSTEM_ONE)
    assert isinstance(err, AppError)
    assert err.status_code == 409 and err.error_code == "SERVICE_RETIRED"
    assert err.message == system_one_retired_message("Nimble", EOS_DATE, None)


# ==================== notice and date normalization (schema) ====================


class TestSchemaFields:
    def test_notice_control_characters_become_spaces_and_are_stripped(self):
        data = _data(deprecation_notice="  use\nthis\tone​now  ")
        assert data.deprecation_notice == "use this one now"

    def test_blank_notice_is_none(self):
        assert _data(deprecation_notice="   \n ").deprecation_notice is None

    def test_notice_limit_is_1000_characters(self):
        assert _data(deprecation_notice="x" * 1000).deprecation_notice == "x" * 1000
        with pytest.raises(ValidationError):
            _data(deprecation_notice="x" * 1001)

    def test_naive_end_of_service_is_taken_as_utc(self):
        data = _data(end_of_service_at=datetime(2026, 6, 1, 12, 0))
        assert data.end_of_service_at == datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)

    def test_fields_are_optional(self):
        data = _data()
        assert data.end_of_service_at is None and data.deprecation_notice is None
        assert "end_of_service_at" not in data.model_fields_set


# ==================== create / update ====================


class TestCrud:
    def test_create_stores_the_lifecycle_fields(self, repo):
        repo.get_by_id_and_app_id.return_value = None
        out = SystemOneServiceService.create_or_update_system_one_service(
            MagicMock(), 10, 0, _data(end_of_service_at=SOON, deprecation_notice="Move to v2."), actor_id=5)
        saved = repo.create.call_args[0][1]
        assert saved.end_of_service_at == SOON and saved.deprecation_notice == "Move to v2."
        assert out.end_of_service_at == SOON and out.deprecation_notice == "Move to v2."
        assert out.lifecycle_status == "deprecated"

    def test_create_without_fields_has_none_and_is_active(self, repo):
        repo.get_by_id_and_app_id.return_value = None
        out = SystemOneServiceService.create_or_update_system_one_service(MagicMock(), 10, 0, _data())
        saved = repo.create.call_args[0][1]
        assert saved.end_of_service_at is None and saved.deprecation_notice is None
        assert out.end_of_service_at is None and out.lifecycle_status == "active"

    def test_create_logs_a_dated_service_once(self, repo):
        repo.get_by_id_and_app_id.return_value = None
        with patch.object(ServiceLifecycleService, "log_change") as log:
            SystemOneServiceService.create_or_update_system_one_service(
                MagicMock(), 10, 0, _data(end_of_service_at=SOON), actor_id=5)
        log.assert_called_once()
        args = log.call_args[0]
        assert args[1] == SERVICE_KIND_SYSTEM_ONE and args[2] is None and args[4] == 5

    def test_update_without_the_fields_keeps_the_stored_ones(self, repo):
        repo.get_by_id_and_app_id.return_value = _svc(eos=SOON, notice="keep me")
        SystemOneServiceService.create_or_update_system_one_service(MagicMock(), 10, 1, _data())
        saved = repo.update.call_args[0][1]
        assert saved.end_of_service_at == SOON and saved.deprecation_notice == "keep me"

    def test_update_with_explicit_nulls_clears_them(self, repo):
        repo.get_by_id_and_app_id.return_value = _svc(eos=SOON, notice="old")
        out = SystemOneServiceService.create_or_update_system_one_service(
            MagicMock(), 10, 1, _data(end_of_service_at=None, deprecation_notice=None))
        saved = repo.update.call_args[0][1]
        assert saved.end_of_service_at is None and saved.deprecation_notice is None
        assert out.lifecycle_status == "active"

    def test_update_sets_a_new_date_and_logs_the_change(self, repo):
        repo.get_by_id_and_app_id.return_value = _svc(eos=SOON)
        with patch.object(ServiceLifecycleService, "log_change") as log:
            SystemOneServiceService.create_or_update_system_one_service(
                MagicMock(), 10, 1, _data(end_of_service_at=FAR), actor_id=7)
        assert repo.update.call_args[0][1].end_of_service_at == FAR
        assert log.call_args[0][2] == SOON and log.call_args[0][4] == 7

    def test_copy_leaves_the_lifecycle_fields_unset(self, repo):
        repo.get_by_id_and_app_id.return_value = _svc(eos=PAST, notice="retired already")
        repo.get_by_app_id.return_value = []
        created = {}

        def _create(db, s):
            created["svc"] = s
            return _stamp(s)

        repo.create.side_effect = _create
        SystemOneServiceService.copy_system_one_service(MagicMock(), 10, 1)
        assert created["svc"].end_of_service_at is None and created["svc"].deprecation_notice is None


# ==================== status and read schemas ====================


class TestStatus:
    @pytest.mark.parametrize("eos,expected", [
        (PAST, "retired"), (SOON, "deprecated"), (FAR, "active"), (None, "active"),
    ])
    def test_status_is_computed_for_the_list_and_the_detail(self, repo, eos, expected):
        repo.get_by_app_id.return_value = [_svc(eos=eos, notice="n")]
        item = SystemOneServiceService.get_system_one_services_by_app_id(MagicMock(), 10)[0]
        repo.get_by_id_and_app_id.return_value = _svc(eos=eos, notice="n")
        detail = SystemOneServiceService.get_system_one_service_detail(MagicMock(), 10, 1)
        assert item.lifecycle_status == detail.lifecycle_status == expected
        assert item.deprecation_notice == detail.deprecation_notice == "n"

    def test_read_schemas_return_the_stored_dates_as_utc(self, repo):
        repo.get_by_id_and_app_id.return_value = _svc(eos=PAST, notice="gone")
        detail = SystemOneServiceService.get_system_one_service_detail(MagicMock(), 10, 1)
        assert detail.end_of_service_at == PAST and detail.end_of_service_at.tzinfo is not None
        assert detail.lifecycle_status == "retired"

    def test_new_service_form_defaults_to_active(self):
        detail = SystemOneServiceService.get_system_one_service_detail(MagicMock(), 10, 0)
        assert detail.end_of_service_at is None and detail.lifecycle_status == "active"

    def test_status_matches_the_shared_rule(self):
        assert compute_lifecycle_status(SOON, 30).value == "deprecated"


# ==================== runtime ====================


@pytest.fixture
def blocked_logs(lifecycle_caplog):
    def _blocked():
        return [r for r in lifecycle_caplog.records if "service_lifecycle.blocked" in r.getMessage()]

    return _blocked


class TestRuntime:
    def test_the_evaluator_snapshot_blocks_a_retired_service(self, blocked_logs):
        with pytest.raises(ServiceRetiredError) as exc:
            SystemOneEvaluator.snapshot(_agent(_svc(eos=PAST, notice="Use v2.")))
        assert exc.value.status_code == 409 and exc.value.error_code == "SERVICE_RETIRED"
        assert "cannot evaluate text" in exc.value.message and "Use v2." in exc.value.message
        blocked = blocked_logs()
        assert len(blocked) == 1 and "kind=system_one" in blocked[0].getMessage()

    def test_the_evaluator_snapshot_works_for_an_active_or_deprecated_service(self):
        assert SystemOneEvaluator.snapshot(_agent(_svc(eos=SOON))).endpoint.service_id == 1
        assert SystemOneEvaluator.snapshot(_agent(_svc(eos=FAR))).endpoint.model == "nimble-latest"

    async def test_the_tool_of_a_retired_service_says_so_to_the_calling_llm(self, blocked_logs):
        with patch.object(SystemOneEvaluator, "evaluate", AsyncMock()) as evaluate:
            tool = await IACTSystemOneTool.create(_agent(_svc(eos=PAST)), user_context={"user_id": 1})
            content, artifact = await tool._arun(text="hello")
        evaluate.assert_not_awaited()
        assert tool.snapshot is None and "currently unavailable" in tool.description
        assert "retired" in content and artifact is None
        assert len(blocked_logs()) == 1       # the guard logs once; the tool does not log it again

    async def test_the_tool_of_an_active_service_evaluates(self):
        tool = await IACTSystemOneTool.create(_agent(_svc(eos=FAR)), user_context={"user_id": 1})
        assert tool.snapshot is not None and tool.unavailable is None

    async def test_test_connection_still_works_on_a_retired_service(self, repo):
        repo.get_by_id_and_app_id.return_value = _svc(eos=PAST)
        probe = AsyncMock(return_value={"ok": True, "message": "ok", "models": ["nimble-latest"], "limits": None})
        with patch.object(module.system_one_client, "probe", probe):
            saved = await SystemOneServiceService.test_connection(MagicMock(), 10, 1)
            status = await SystemOneServiceService.test_connection(MagicMock(), 10, 1, live_call=False)
            form = await SystemOneServiceService.test_connection_with_config(
                MagicMock(), 10, {"endpoint": "http://so.test", "api_key": "tok"}, service_id=1)
        assert saved["status"] == status["status"] == form["status"] == "success"
        assert probe.await_count == 3


# ==================== export / import ====================


class TestPorting:
    def test_export_carries_the_dates_and_never_the_token(self):
        exported = export_system_one_service(_svc(eos=SOON, notice="Move on."))
        dumped = exported.model_dump(mode="json")
        assert dumped["api_key"] is None
        assert dumped["end_of_service_at"].startswith(SOON.strftime("%Y-%m-%dT%H:%M:%S"))
        assert dumped["deprecation_notice"] == "Move on."

    def test_export_of_an_active_service_has_no_dates(self):
        exported = export_system_one_service(_svc())
        assert exported.end_of_service_at is None and exported.deprecation_notice is None

    def test_import_sets_the_dates_on_the_new_service(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None
        item = ExportSystemOneServiceSchema(
            name="Nimble", endpoint="http://so.test", model_name="nimble-latest",
            end_of_service_at=PAST, deprecation_notice="  gone  ")
        _, warnings = import_system_one_service(session, item, app_id=10)
        added = session.add.call_args[0][0]
        assert added.end_of_service_at == PAST and added.deprecation_notice == "gone"
        assert warnings                      # no token: the usual warning still applies

    def test_a_file_from_before_the_fields_existed_imports_as_active(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None
        item = ExportSystemOneServiceSchema(name="Nimble", endpoint="http://so.test", model_name="m")
        import_system_one_service(session, item, app_id=10)
        added = session.add.call_args[0][0]
        assert added.end_of_service_at is None and added.deprecation_notice is None

    def test_round_trip_keeps_the_lifecycle(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None
        exported = export_system_one_service(_svc(eos=SOON, notice="Move on."))
        reloaded = ExportSystemOneServiceSchema.model_validate(json.loads(exported.model_dump_json()))
        import_system_one_service(session, reloaded, app_id=11)
        added = session.add.call_args[0][0]
        assert added.end_of_service_at == SOON and added.deprecation_notice == "Move on."
