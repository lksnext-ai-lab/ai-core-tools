"""Unit tests for the pure dependency-warning builders of ServiceLifecycleService (AD-8)."""

from datetime import datetime, timedelta, timezone

from repositories.service_usage_repository import AgentRefs, ServiceSnapshot, SiloRefs
from services.service_lifecycle_service import LifecycleContext, ServiceLifecycleService

NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _snap(service_id, name, days=None, notice=None):
    eos = None if days is None else NOW + timedelta(days=days)
    return ServiceSnapshot(service_id, name, 1, eos, notice)


def _agent(**kwargs):
    base = dict(
        agent_id=1, service_id=None, vision_service_id=None, transcription_service_id=None,
        video_ai_service_id=None, media_embedding_service_id=None, silo_id=None,
    )
    base.update(kwargs)
    return AgentRefs(**base)


def _ctx(ai=(), embedding=(), silos=(), middlewares=None, agent_middlewares=None, warning_days=30):
    return LifecycleContext(
        warning_days=warning_days,
        now=NOW,
        services={"ai": {s.service_id: s for s in ai}, "embedding": {s.service_id: s for s in embedding}},
        silos={s.silo_id: s for s in silos},
        middlewares=middlewares or {},
        agent_middlewares=agent_middlewares or {},
    )


class TestWarningsForAgent:
    def test_deprecated_llm_and_retired_silo_embedding_retired_first(self):
        ctx = _ctx(
            ai=[_snap(1, "gpt", days=10, notice="move to gpt-5")],
            embedding=[_snap(2, "emb", days=-1)],
            silos=[SiloRefs(7, "Docs", 2, None, None)],
        )
        warnings = ServiceLifecycleService.warnings_for_agent(_agent(service_id=1, silo_id=7), ctx)

        assert [(w.role, w.lifecycle_status, w.via) for w in warnings] == [
            ("silo_embedding", "retired", "Docs"),
            ("llm", "deprecated", None),
        ]
        assert warnings[1].deprecation_notice == "move to gpt-5"
        assert warnings[1].kind == "ai" and warnings[0].kind == "embedding"

    def test_active_services_produce_nothing(self):
        ctx = _ctx(ai=[_snap(1, "gpt", days=365), _snap(2, "other")], embedding=[_snap(3, "emb")],
                   silos=[SiloRefs(7, "Docs", 3, None, None)])
        assert ServiceLifecycleService.warnings_for_agent(_agent(service_id=1, silo_id=7), ctx) == []
        assert ServiceLifecycleService.warnings_for_agent(_agent(service_id=2), ctx) == []

    def test_dependency_only_through_middleware(self):
        ctx = _ctx(
            ai=[_snap(5, "summariser", days=-3)],
            middlewares={9: ("Summaries", [5])},
            agent_middlewares={1: [9]},
        )
        warnings = ServiceLifecycleService.warnings_for_agent(_agent(), ctx)
        assert [(w.service_id, w.role, w.via, w.lifecycle_status) for w in warnings] == [
            (5, "middleware", "Summaries", "retired")
        ]

    def test_middleware_of_another_agent_is_ignored(self):
        ctx = _ctx(ai=[_snap(5, "s", days=-3)], middlewares={9: ("M", [5])}, agent_middlewares={2: [9]})
        assert ServiceLifecycleService.warnings_for_agent(_agent(agent_id=1), ctx) == []

    def test_ocr_vision_media_and_transcription_roles(self):
        ctx = _ctx(
            ai=[_snap(1, "vision", days=5), _snap(2, "whisper", days=6), _snap(3, "gemini", days=7)],
            embedding=[_snap(4, "media-emb", days=8)],
        )
        row = _agent(vision_service_id=1, transcription_service_id=2, video_ai_service_id=3,
                     media_embedding_service_id=4)
        warnings = ServiceLifecycleService.warnings_for_agent(row, ctx)
        assert [w.role for w in warnings] == ["ocr_vision", "transcription", "video", "media_embedding"]

    def test_same_dependency_reported_once(self):
        ctx = _ctx(ai=[_snap(1, "gpt", days=1)])
        warnings = ServiceLifecycleService.warnings_for_agent(_agent(service_id=1, vision_service_id=1), ctx)
        assert [w.role for w in warnings] == ["llm", "ocr_vision"]  # different roles kept
        assert len(ServiceLifecycleService.warnings_for_agent(_agent(service_id=1), ctx)) == 1

    def test_unknown_or_foreign_service_id_is_skipped(self):
        assert ServiceLifecycleService.warnings_for_agent(_agent(service_id=99, silo_id=99), _ctx()) == []

    def test_none_row_gives_empty_list(self):
        assert ServiceLifecycleService.warnings_for_agent(None, _ctx()) == []

    def test_zero_warning_days_has_no_deprecated_phase(self):
        ctx = _ctx(ai=[_snap(1, "gpt", days=10)], warning_days=0)
        assert ServiceLifecycleService.warnings_for_agent(_agent(service_id=1), ctx) == []

    def test_sorted_by_date_within_status(self):
        ctx = _ctx(ai=[_snap(1, "late", days=20), _snap(2, "soon", days=2)])
        warnings = ServiceLifecycleService.warnings_for_agent(
            _agent(service_id=1, transcription_service_id=2), ctx
        )
        assert [w.service_name for w in warnings] == ["soon", "late"]


class TestWarningsForSiloAndTask:
    def test_silo_embedding_transcription_and_video(self):
        ctx = _ctx(
            ai=[_snap(2, "whisper", days=4), _snap(3, "gemini", days=-1)],
            embedding=[_snap(1, "emb", days=9)],
            silos=[SiloRefs(7, "Docs", 1, 2, 3)],
        )
        warnings = ServiceLifecycleService.warnings_for_silo(7, ctx)
        assert [(w.role, w.lifecycle_status) for w in warnings] == [
            ("video", "retired"), ("transcription", "deprecated"), ("embedding", "deprecated"),
        ]

    def test_unknown_silo_or_none(self):
        assert ServiceLifecycleService.warnings_for_silo(5, _ctx()) == []
        assert ServiceLifecycleService.warnings_for_silo(None, _ctx()) == []

    def test_task_uses_its_agents_warnings(self):
        ctx = _ctx(ai=[_snap(1, "gpt", days=3)])
        ctx.agent_refs = {4: _agent(agent_id=4, service_id=1)}
        task = type("T", (), {"agent_id": 4})()
        other = type("T", (), {"agent_id": 5})()
        assert [w.role for w in ServiceLifecycleService.warnings_for_task(task, ctx)] == ["llm"]
        assert ServiceLifecycleService.warnings_for_task(other, ctx) == []


class TestOptionFields:
    def test_option_fields(self):
        svc = type("S", (), {"end_of_service_at": datetime.now(timezone.utc) - timedelta(days=1),
                             "deprecation_notice": "n"})()
        out = ServiceLifecycleService.option_fields(svc, 30)
        assert out["lifecycle_status"] == "retired" and out["deprecation_notice"] == "n"

    def test_option_fields_without_lifecycle(self):
        out = ServiceLifecycleService.option_fields(object(), 30)
        assert out == {"end_of_service_at": None, "deprecation_notice": None, "lifecycle_status": "active"}
