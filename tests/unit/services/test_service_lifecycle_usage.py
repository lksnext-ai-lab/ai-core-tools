"""Unit tests for ServiceLifecycleService usage lookups and moves (queries mocked)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from repositories.service_usage_repository import ServiceSnapshot, UsageAgentRow, UsageSiloRow
from services.service_lifecycle_service import ServiceLifecycleService
from utils.error_handlers import ConflictError, NotFoundError
from utils.error_handlers import ValidationError as AppValidationError

MODULE = "services.service_lifecycle_service"
FUTURE = datetime.now(timezone.utc) + timedelta(days=100)
PAST = datetime.now(timezone.utc) - timedelta(days=1)


def snap(service_id, app_id=1, eos=None):
    return ServiceSnapshot(service_id, f"svc{service_id}", app_id, eos, None)


@pytest.fixture
def queries(monkeypatch):
    q = MagicMock()
    q.move_agents.return_value = [4, 5]
    q.count_agents_on_ai_service.return_value = 2
    monkeypatch.setattr(f"{MODULE}.ServiceUsageQueries", q)
    return q


def _services(q, source, target):
    table = {s.service_id: s for s in (source, target) if s}
    q.service_snapshot.side_effect = lambda db, model, sid: table.get(sid)


def move(db, expected=None, target=20):
    return ServiceLifecycleService.move_agents(db, 1, 10, target, expected, 99)


def move_sandbox(db, expected_agents=2, expected_apps=1, target=20):
    return ServiceLifecycleService.move_sandbox_usage(
        db, 1, 10, target, expected_agents, expected_apps, 99
    )


def test_move_success(queries):
    _services(queries, snap(10), snap(20))
    db = MagicMock()
    result = move(db, expected=2)
    assert result.moved_agent_ids == [4, 5] and result.count == 2
    db.commit.assert_called_once()


def test_move_system_target_allowed_and_zero_matches(queries):
    _services(queries, snap(10), snap(20, app_id=None))
    queries.move_agents.return_value = []
    assert move(MagicMock()).count == 0


def test_move_source_of_other_app_is_not_found(queries):
    _services(queries, snap(10, app_id=2), snap(20))
    db = MagicMock()
    with pytest.raises(NotFoundError):
        move(db)
    queries.move_agents.assert_not_called()


def test_move_missing_source(queries):
    _services(queries, None, snap(20))
    with pytest.raises(NotFoundError):
        move(MagicMock())


def test_move_same_target(queries):
    _services(queries, snap(10), snap(20))
    with pytest.raises(AppValidationError):
        move(MagicMock(), target=10)


@pytest.mark.parametrize("target", [None, snap(20, app_id=2), snap(20, eos=PAST)])
def test_move_invalid_target(queries, target):
    _services(queries, snap(10), target)
    db = MagicMock()
    with pytest.raises(AppValidationError):
        move(db)
    queries.move_agents.assert_not_called()
    db.commit.assert_not_called()


def test_move_retired_source_is_allowed(queries):
    _services(queries, snap(10, eos=PAST), snap(20, eos=FUTURE))
    assert move(MagicMock()).count == 2


def test_move_count_mismatch_conflict(queries):
    _services(queries, snap(10), snap(20))
    queries.move_agents.return_value = [1, 2, 3]
    db = MagicMock()
    with pytest.raises(ConflictError) as exc:
        move(db, expected=2)
    assert exc.value.status_code == 409 and "3" in exc.value.message
    db.rollback.assert_called_once()
    db.commit.assert_not_called()
    queries.count_agents_on_ai_service.assert_not_called()


def test_move_rolls_back_on_error(queries):
    _services(queries, snap(10), snap(20))
    queries.move_agents.side_effect = RuntimeError("boom")
    db = MagicMock()
    with pytest.raises(RuntimeError):
        move(db)
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_move_sandbox_usage_updates_direct_agents_and_app_default(queries):
    _services(queries, snap(10), snap(20, app_id=None))
    queries.move_sandbox_usage.return_value = ([4, 5], [1])
    db = MagicMock()

    result = move_sandbox(db, expected_agents=2, expected_apps=1)

    assert result.moved_agent_ids == [4, 5]
    assert result.updated_app_ids == [1]
    queries.move_sandbox_usage.assert_called_once_with(db, 1, 10, 20)
    db.commit.assert_called_once()


def test_move_sandbox_usage_allows_default_only_move(queries):
    _services(queries, snap(10), snap(20))
    queries.move_sandbox_usage.return_value = ([], [1])

    result = move_sandbox(MagicMock(), expected_agents=0, expected_apps=1)

    assert result.moved_agent_ids == []
    assert result.updated_app_ids == [1]


def test_move_sandbox_usage_conflict_rolls_back_both_updates(queries):
    _services(queries, snap(10), snap(20))
    queries.move_sandbox_usage.return_value = ([4], [1])
    db = MagicMock()

    with pytest.raises(ConflictError, match="sandbox usage changed"):
        move_sandbox(db, expected_agents=2, expected_apps=1)

    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_move_sandbox_usage_rejects_target_from_another_app(queries):
    _services(queries, snap(10), snap(20, app_id=2))
    db = MagicMock()

    with pytest.raises(AppValidationError):
        move_sandbox(db)

    queries.move_sandbox_usage.assert_not_called()
    db.commit.assert_not_called()


def agent_row(**kw):
    base = dict(agent_id=1, name="a", app_id=1, app_name="App", service_id=None, vision_service_id=None,
                transcription_service_id=None, video_ai_service_id=None, media_embedding_service_id=None, silo_id=None)
    return SimpleNamespace(**{**base, **kw})


def test_ai_agent_roles_aggregated():
    row = agent_row(service_id=7, vision_service_id=7, video_ai_service_id=7, transcription_service_id=8)
    assert ServiceLifecycleService.agent_roles(row, "ai", 7) == ["llm", "ocr_vision", "video"]


def test_embedding_agent_roles():
    row = agent_row(media_embedding_service_id=5, silo_id=3)
    assert ServiceLifecycleService.agent_roles(row, "embedding", 5, {3}) == ["media_embedding", "silo_embedding"]
    assert ServiceLifecycleService.agent_roles(row, "embedding", 5, set()) == ["media_embedding"]


def test_silo_roles():
    row = SimpleNamespace(embedding_service_id=None, transcription_service_id=7, video_ai_service_id=7)
    assert ServiceLifecycleService.silo_roles(row, "ai", 7) == ["transcription", "video"]
    row.embedding_service_id = 7
    assert ServiceLifecycleService.silo_roles(row, "embedding", 7) == ["embedding"]


@pytest.fixture
def usage_env(monkeypatch, queries):
    monkeypatch.setattr(ServiceLifecycleService, "warning_days", staticmethod(lambda db: 30))
    queries.ai_agents.return_value = [agent_row(service_id=7), agent_row(agent_id=2, name="b", transcription_service_id=7)]
    for name in ("ai_silos", "ai_repositories", "ai_tasks", "embedding_agents", "embedding_silos",
                 "embedding_repositories", "embedding_tasks"):
        getattr(queries, name).return_value = []
    monkeypatch.setattr(f"{MODULE}.MiddlewareService.using_ai_service", MagicMock(return_value=[]))
    return queries


def test_get_usage_app_scope_hides_app_name_and_filters(usage_env):
    usage_env.service_snapshot.return_value = snap(7, app_id=None, eos=PAST)
    result = ServiceLifecycleService.get_usage(MagicMock(), "ai", 7, 1)
    assert result.is_system and result.lifecycle_status == "retired"
    assert [a.roles for a in result.agents] == [["llm"], ["transcription"]]
    assert all(a.app_name is None for a in result.agents)
    usage_env.ai_agents.assert_called_once_with(usage_env.ai_agents.call_args.args[0], 7, 1)


def test_get_usage_admin_scope_includes_app_name(usage_env):
    usage_env.service_snapshot.return_value = snap(7, app_id=None)
    result = ServiceLifecycleService.get_usage(MagicMock(), "ai", 7, None)
    assert result.agents[0].app_name == "App"
    usage_env.ai_agents.assert_called_once()
    assert usage_env.ai_agents.call_args.args[2] is None


@pytest.mark.parametrize("app_id,owner", [(1, 2), (None, 1)])
def test_get_usage_hidden_service_returns_none(usage_env, app_id, owner):
    usage_env.service_snapshot.return_value = snap(7, app_id=owner)
    assert ServiceLifecycleService.get_usage(MagicMock(), "ai", 7, app_id) is None
    usage_env.ai_agents.assert_not_called()


def test_get_usage_missing_service(usage_env):
    usage_env.service_snapshot.return_value = None
    assert ServiceLifecycleService.get_usage(MagicMock(), "ai", 7, 1) is None


def test_get_usage_embedding_silo_embedding_role(usage_env):
    usage_env.service_snapshot.return_value = snap(5, app_id=1)
    usage_env.embedding_silos.return_value = [
        UsageSiloRow(3, "silo", 1, "App", 5, None, None)
    ]
    usage_env.embedding_agents.return_value = [agent_row(silo_id=3)]
    result = ServiceLifecycleService.get_usage(MagicMock(), "embedding", 5, 1)
    assert result.agents[0].roles == ["silo_embedding"]
    assert result.silos[0].roles == ["embedding"]
    assert result.middlewares == []


def test_get_usage_middlewares_only_in_app_scope(usage_env, monkeypatch):
    mw = SimpleNamespace(middleware_id=9, name="pii", middleware_type="PII", app_id=1)
    using = MagicMock(return_value=[mw])
    monkeypatch.setattr(f"{MODULE}.MiddlewareService.using_ai_service", using)
    usage_env.middleware_agent_ids.return_value = {9: [1]}
    usage_env.service_snapshot.return_value = snap(7, app_id=1)
    result = ServiceLifecycleService.get_usage(MagicMock(), "ai", 7, 1)
    assert result.middlewares[0].agent_ids == [1]
    usage_env.service_snapshot.return_value = snap(7, app_id=None)
    admin = ServiceLifecycleService.get_usage(MagicMock(), "ai", 7, None)
    assert admin.middlewares == []
    assert using.call_count == 1


def test_names_using_ai_service_wrapper(monkeypatch):
    from services.middleware_service import MiddlewareService

    monkeypatch.setattr(
        MiddlewareService, "using_ai_service",
        staticmethod(lambda db, app_id, sid: [SimpleNamespace(name="a"), SimpleNamespace(name="b")]),
    )
    assert MiddlewareService.names_using_ai_service(MagicMock(), 1, 2) == ["a", "b"]


def test_move_sandbox_usage_missing_source_not_found(queries):
    _services(queries, None, snap(20))
    db = MagicMock()
    with pytest.raises(NotFoundError):
        move_sandbox(db)
    queries.move_sandbox_usage.assert_not_called()
    db.commit.assert_not_called()


def test_move_sandbox_usage_source_of_other_app_not_found(queries):
    _services(queries, snap(10, app_id=2), snap(20))
    with pytest.raises(NotFoundError):
        move_sandbox(MagicMock())
    queries.move_sandbox_usage.assert_not_called()


def test_move_sandbox_usage_same_target_rejected(queries):
    _services(queries, snap(10), snap(20))
    db = MagicMock()
    with pytest.raises(AppValidationError):
        move_sandbox(db, target=10)
    queries.move_sandbox_usage.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize("target", [None, snap(20, eos=PAST)])
def test_move_sandbox_usage_missing_or_retired_target_rejected(queries, target):
    _services(queries, snap(10), target)
    db = MagicMock()
    with pytest.raises(AppValidationError):
        move_sandbox(db)
    queries.move_sandbox_usage.assert_not_called()
    db.commit.assert_not_called()


def test_move_sandbox_usage_app_count_only_mismatch_conflicts(queries):
    _services(queries, snap(10), snap(20))
    queries.move_sandbox_usage.return_value = ([4, 5], [])
    db = MagicMock()
    with pytest.raises(ConflictError):
        move_sandbox(db, expected_agents=2, expected_apps=1)
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_move_sandbox_usage_unexpected_error_rolls_back(queries):
    _services(queries, snap(10), snap(20))
    queries.move_sandbox_usage.side_effect = RuntimeError("boom")
    db = MagicMock()
    with pytest.raises(RuntimeError):
        move_sandbox(db)
    db.rollback.assert_called_once()
    db.commit.assert_not_called()
