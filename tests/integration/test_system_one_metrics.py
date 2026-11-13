"""System One metrics rows are really persisted (committed rows + the recorder's own DB session)."""
import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from services import agent_metrics_recorder
from services.system_one_evaluator import SystemOneEvaluator
from tools.system_one_client import SystemOneError

pytestmark = pytest.mark.integration

QUESTIONS = [
    {"key": "urgent", "type": "noul", "instructions": "Is it urgent?", "threshold": 0.8},
    {"key": "area", "type": "choice", "instructions": "Which area?", "min_probability": 0.6,
     "criteria": [{"key": "billing"}, {"key": "tech"}]},
]
RAW = {"model": "nimble-latest", "usage": {"input_tokens": 120, "output_tokens": 3},
       "answers": {"urgent": {"type": "noul", "noul": 0.91},
                   "area": {"type": "choice", "choice": "billing", "confidence": 0.39,
                            "probabilities": {"billing": 0.73, "tech": 0.27}}}}


@pytest.fixture
def committed(test_engine):
    """A real (committed) app + agent: the recorder writes with its own session, invisible to savepoints."""
    from db.database import SessionLocal
    from models.app import App
    from models.system_one_agent import SystemOneAgent
    from models.system_one_service import SystemOneService
    from models.user import User

    tag = uuid.uuid4().hex[:8]
    db = SessionLocal()
    user = User(email=f"so-metrics-{tag}@test.com", name="M", is_active=True, platform_role="editor")
    db.add(user)
    db.flush()
    app = App(name=f"SO metrics {tag}", slug=f"so-metrics-{tag}", owner_id=user.user_id)
    db.add(app)
    db.flush()
    svc = SystemOneService(name="Nimble", endpoint="http://so.test", description="nimble-latest",
                           app_id=app.app_id, create_date=datetime.now())
    db.add(svc)
    db.flush()
    agent = SystemOneAgent(name="Triage", app_id=app.app_id, system_one_service_id=svc.service_id,
                           questions=QUESTIONS, max_state_chars=6000, create_date=datetime.now())
    db.add(agent)
    db.commit()
    ids = (user.user_id, app.app_id, svc.service_id, agent.agent_id)
    snapshot = SystemOneEvaluator.snapshot(agent)
    try:
        yield SimpleNamespaceLike(snapshot=snapshot, agent_id=agent.agent_id, app_id=app.app_id)
    finally:
        db.rollback()
        for model, pk in ((SystemOneAgent, ids[3]), (SystemOneService, ids[2]), (App, ids[1]), (User, ids[0])):
            obj = db.get(model, pk) if model is not SystemOneAgent else db.query(SystemOneAgent).get(pk)
            if obj is not None:
                db.delete(obj)
                db.commit()
        db.close()


class SimpleNamespaceLike:
    def __init__(self, **kw):
        self.__dict__.update(kw)


async def drain_writes():
    pending = list(agent_metrics_recorder._pending_writes)
    if pending:
        await asyncio.gather(*pending)


def rows(agent_id):
    from db.database import SessionLocal
    from models.agent_execution_event import AgentExecutionEvent
    from models.agent_system_one_answer import AgentSystemOneAnswer

    db = SessionLocal()
    try:
        events = db.query(AgentExecutionEvent).filter(AgentExecutionEvent.agent_id == agent_id).all()
        answers = (db.query(AgentSystemOneAnswer)
                   .filter(AgentSystemOneAnswer.event_id.in_([e.event_id for e in events])).all()) if events else []
        return events, answers
    finally:
        db.close()


async def test_success_persists_the_event_and_one_row_per_question(committed):
    with patch("services.system_one_evaluator.system_one_client.evaluate", AsyncMock(return_value=RAW)):
        await SystemOneEvaluator().evaluate(committed.snapshot, "please call", [], {"user_id": None, "api_key_id": None})
    await drain_writes()
    events, answers = rows(committed.agent_id)
    assert len(events) == 1
    e = events[0]
    assert (e.status.value if hasattr(e.status, "value") else e.status) == "SUCCESS"
    assert (e.provider, e.model_name, e.input_tokens, e.output_tokens, e.total_tokens) == ("system_one", "nimble-latest", 120, 3, 123)
    by_key = {a.question_key: a for a in answers}
    assert set(by_key) == {"urgent", "area"}
    assert (by_key["urgent"].question_type, by_key["urgent"].decision, by_key["urgent"].probability) == ("noul", "true", 0.91)
    assert (by_key["area"].decision, by_key["area"].confidence, by_key["area"].state_reduction) == ("billing", 0.39, "none")
    assert by_key["area"].probabilities == {"billing": 0.73, "tech": 0.27}


async def test_failed_evaluation_leaves_an_error_event_and_no_answer_rows(committed):
    from fastapi import HTTPException

    boom = AsyncMock(side_effect=SystemOneError("overloaded", "busy", 529))
    with patch("services.system_one_evaluator.system_one_client.evaluate", boom):
        with pytest.raises(HTTPException):
            await SystemOneEvaluator().evaluate(committed.snapshot, "please call", [], {})
    await drain_writes()
    events, answers = rows(committed.agent_id)
    assert len(events) == 1 and answers == []
    assert (events[0].status.value if hasattr(events[0].status, "value") else events[0].status) == "ERROR"
    assert events[0].error_code == "overloaded"


async def test_deleting_the_event_deletes_its_answers(committed):
    from db.database import SessionLocal
    from models.agent_execution_event import AgentExecutionEvent

    with patch("services.system_one_evaluator.system_one_client.evaluate", AsyncMock(return_value=RAW)):
        await SystemOneEvaluator().evaluate(committed.snapshot, "please call", [], {})
    await drain_writes()
    db = SessionLocal()
    try:
        db.query(AgentExecutionEvent).filter(AgentExecutionEvent.agent_id == committed.agent_id).delete()
        db.commit()
    finally:
        db.close()
    assert rows(committed.agent_id) == ([], [])


async def test_summarization_is_persisted_on_its_own_and_summed_apart_from_the_system_one_tokens(committed):
    from dataclasses import replace
    from db.database import SessionLocal
    from services.metrics_query_service import MetricsQueryService, MetricsScope
    from services.system_one_state import SummaryOutput

    summarize = AsyncMock(return_value=SummaryOutput("short summary", input_tokens=900, output_tokens=120))
    snapshot = replace(committed.snapshot, summarize=summarize, max_state_chars=1000)
    with patch("services.system_one_evaluator.system_one_client.evaluate", AsyncMock(return_value=RAW)):
        await SystemOneEvaluator().evaluate(snapshot, "word " * 5000, [], {"user_id": None, "api_key_id": None})
        await SystemOneEvaluator().evaluate(committed.snapshot, "a short text", [], {"user_id": None, "api_key_id": None})
    await drain_writes()

    events, _ = rows(committed.agent_id)
    by_calls = {e.summarization_calls: e for e in events}
    assert set(by_calls) == {0, 1}
    summarized = by_calls[1]
    assert (summarized.summarization_input_tokens, summarized.summarization_output_tokens) == (900, 120)
    assert (summarized.input_tokens, summarized.output_tokens, summarized.llm_calls) == (120, 3, 0)   # the server's own
    assert (by_calls[0].summarization_input_tokens, by_calls[0].summarization_output_tokens) == (0, 0)

    db = SessionLocal()
    try:
        stats = MetricsQueryService.summary(db, MetricsScope(app_id=committed.app_id, agent_id=committed.agent_id), "24h").current
    finally:
        db.close()
    assert (stats.summarization_calls, stats.summarization_input_tokens, stats.summarization_output_tokens) == (1, 900, 120)
    assert (stats.input_tokens, stats.output_tokens, stats.llm_calls) == (240, 6, 0)
