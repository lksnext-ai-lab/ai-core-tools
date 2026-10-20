"""Smoke test of the "used by" / bulk-move SQL: app scope isolation and the single UPDATE ... RETURNING."""

import pytest

from models.agent import Agent
from models.ai_service import AIService
from models.app import App
from models.embedding_service import EmbeddingService
from models.ocr_agent import OCRAgent
from models.silo import Silo
from services.service_lifecycle_service import ServiceLifecycleService

pytestmark = pytest.mark.integration


def _service(name, app_id):
    return AIService(name=name, provider="OpenAI", api_key="k", app_id=app_id)  # pragma: allowlist secret


def test_app_scope_isolated_and_move(db, fake_app):
    other = App(name="usage-other-app")
    db.add(other)
    db.flush()
    system = _service("usage-system", None)
    mine, target = _service("usage-mine", fake_app.app_id), _service("usage-target", fake_app.app_id)
    emb = EmbeddingService(name="usage-emb", provider="OpenAI", app_id=None)
    db.add_all([system, mine, target, emb])
    db.flush()
    silo = Silo(name="usage-silo", app_id=fake_app.app_id, embedding_service_id=emb.service_id)
    db.add(silo)
    db.flush()
    mk = lambda cls, app, svc, **kw: cls(name=f"usage-{cls.__name__}-{app}-{svc}", description="d",  # noqa: E731
                                         system_prompt="s", app_id=app, service_id=svc, temperature=0.5, **kw)
    a_mine = mk(Agent, fake_app.app_id, system.service_id, silo_id=silo.silo_id)
    a_ocr = mk(OCRAgent, fake_app.app_id, system.service_id, vision_service_id=system.service_id)
    a_other = mk(Agent, other.app_id, system.service_id)
    db.add_all([a_mine, a_ocr, a_other])
    db.flush()

    usage = ServiceLifecycleService.get_usage(db, "ai", system.service_id, fake_app.app_id)
    ids = {a.agent_id: a.roles for a in usage.agents}
    assert set(ids) == {a_mine.agent_id, a_ocr.agent_id}
    assert ids[a_ocr.agent_id] == ["llm", "ocr_vision"]
    assert all(a.app_name is None for a in usage.agents)

    admin = ServiceLifecycleService.get_usage(db, "ai", system.service_id, None)
    assert {a.agent_id for a in admin.agents} == {a_mine.agent_id, a_ocr.agent_id, a_other.agent_id}
    assert all(a.app_name for a in admin.agents)
    assert ServiceLifecycleService.get_usage(db, "ai", mine.service_id, None) is None
    assert ServiceLifecycleService.get_usage(db, "ai", mine.service_id, other.app_id) is None

    emb_usage = ServiceLifecycleService.get_usage(db, "embedding", emb.service_id, fake_app.app_id)
    assert [s.silo_id for s in emb_usage.silos] == [silo.silo_id]
    assert [a.roles for a in emb_usage.agents] == [["silo_embedding"]]

    result = ServiceLifecycleService.move_agents(db, fake_app.app_id, system.service_id, target.service_id, 2, 1)
    assert sorted(result.moved_agent_ids) == sorted([a_mine.agent_id, a_ocr.agent_id])
    db.expire_all()
    assert a_other.service_id == system.service_id
    assert a_mine.service_id == target.service_id
