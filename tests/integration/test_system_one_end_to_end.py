"""End to end: a normal agent using System One agents as tools, with real committed rows.

The parent agent is built with the real ``create_agent`` (LLM and LangChain agent patched); the System One tool it
registers is then invoked as LangChain would, and the metrics are read back from the database.
"""
import asyncio
import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import agent_metrics_recorder
from services.agent_metrics_collector import METRICS_SUB_AGENT_ID_KEY, METRICS_TOOL_TYPE_KEY
from tools.system_one_client import SystemOneError
from tools.system_one_tool import IACTSystemOneTool

pytestmark = pytest.mark.integration

PARENT_EVENT = str(uuid.uuid4())
QUESTIONS = [
    {"key": "urgent", "type": "noul", "instructions": "Is it urgent?", "threshold": 0.8},
    {"key": "area", "type": "choice", "instructions": "Which area?", "min_probability": 0.6,
     "criteria": [{"key": "billing"}, {"key": "tech"}]},
]
RAW = {"model": "nimble-latest", "usage": {"input_tokens": 90, "output_tokens": 3},
       "answers": {"urgent": {"type": "noul", "noul": 0.91},
                   "area": {"type": "choice", "choice": "billing", "confidence": 0.39,
                            "probabilities": {"billing": 0.73, "tech": 0.27}}}}


class World:
    pass


@pytest.fixture
def world(test_engine):
    from db.database import SessionLocal
    from models.agent import Agent, AgentTool
    from models.app import App
    from models.system_one_agent import SystemOneAgent
    from models.system_one_service import SystemOneService
    from models.user import User

    tag = uuid.uuid4().hex[:8]
    db = SessionLocal()
    user = User(email=f"so-e2e-{tag}@test.com", name="E2E", is_active=True, platform_role="editor")
    db.add(user)
    db.flush()
    app = App(name=f"SO e2e {tag}", slug=f"so-e2e-{tag}", owner_id=user.user_id)
    db.add(app)
    db.flush()
    svc = SystemOneService(name="Nimble", endpoint="http://so.test", description="nimble-latest",
                           app_id=app.app_id, create_date=datetime.now())
    db.add(svc)
    db.flush()
    so_agent = SystemOneAgent(name="Triage", description="Classifies tickets", app_id=app.app_id,
                              system_one_service_id=svc.service_id, questions=QUESTIONS, max_state_chars=6000,
                              is_tool=True, create_date=datetime.now())
    sub_agent = Agent(name="Helper", app_id=app.app_id, is_tool=True, system_prompt="help", has_memory=False,
                      create_date=datetime.now())
    parent = Agent(name="Boss", app_id=app.app_id, system_prompt="boss", has_memory=False, create_date=datetime.now())
    db.add_all([so_agent, sub_agent, parent])
    db.flush()
    db.add_all([AgentTool(agent_id=parent.agent_id, tool_id=so_agent.agent_id),
                AgentTool(agent_id=parent.agent_id, tool_id=sub_agent.agent_id),
                AgentTool(agent_id=sub_agent.agent_id, tool_id=so_agent.agent_id)])
    db.commit()

    w = World()
    w.db, w.app_id, w.user_id = db, app.app_id, user.user_id
    w.service_id, w.so_id, w.sub_id, w.parent_id = svc.service_id, so_agent.agent_id, sub_agent.agent_id, parent.agent_id
    yield w
    try:
        db.rollback()
        from models.agent import Agent as A
        from repositories.agent_repository import AgentRepository

        for agent_id in (w.parent_id, w.sub_id, w.so_id):
            AgentRepository.delete_by_id(db, agent_id)
        for model, pk in ((SystemOneService, w.service_id), (App, w.app_id), (User, w.user_id)):
            obj = db.get(model, pk)
            if obj is not None:
                db.delete(obj)
                db.commit()
    finally:
        db.close()


async def build_parent(w, user_context=None):
    """Run the real create_agent and return (tools given to the parent's LangChain agent, all create calls)."""
    from tools.agentTools import create_agent

    parent = w.db.get(__import__("models.agent", fromlist=["Agent"]).Agent, w.parent_id)
    calls = []

    def capture(**kwargs):
        calls.append(kwargs)
        return MagicMock()

    with patch("tools.agentTools.get_llm", return_value=MagicMock()), \
         patch("tools.agentTools.get_output_parser", return_value=None), \
         patch("tools.agentTools.create_langchain_agent", side_effect=capture), \
         patch("tools.agentTools.MCPClientManager.get_client", new=AsyncMock(return_value=None)):
        await create_agent(parent, user_context=user_context or {"user_id": w.user_id, "current_event_id": PARENT_EVENT})
    return calls


def so_tools(calls):
    return [t for c in calls for t in c["tools"] if isinstance(t, IACTSystemOneTool)]


async def drain():
    pending = list(agent_metrics_recorder._pending_writes)
    if pending:
        await asyncio.gather(*pending)


def events_of(agent_id):
    from db.database import SessionLocal
    from models.agent_execution_event import AgentExecutionEvent
    from models.agent_system_one_answer import AgentSystemOneAnswer

    db = SessionLocal()
    try:
        events = db.query(AgentExecutionEvent).filter(AgentExecutionEvent.agent_id == agent_id).all()
        answers = db.query(AgentSystemOneAnswer).filter(
            AgentSystemOneAnswer.event_id.in_([e.event_id for e in events])).all() if events else []
        return events, answers
    finally:
        db.close()


def call_message(tool, text="please call me back"):
    return {"name": tool.name, "args": {"text": text}, "id": "call-1", "type": "tool_call"}


def evaluate_patch(**kw):
    return patch("services.system_one_evaluator.system_one_client.evaluate", AsyncMock(**({"return_value": RAW} | kw)))


# ------------------------------------------------------------------ registration

async def test_a_normal_agent_gets_the_system_one_agent_as_a_typed_tool(world):
    calls = await build_parent(world)
    parent_tools = [t for t in calls[-1]["tools"] if isinstance(t, IACTSystemOneTool)]
    assert len(parent_tools) == 1
    tool = parent_tools[0]
    assert set(tool.args_schema.model_json_schema()["properties"]) == {"text"}
    assert "urgent (yes/no)" in tool.description and "area (choice: billing | tech)" in tool.description
    assert tool.metadata[METRICS_TOOL_TYPE_KEY] == "AGENT" and tool.metadata[METRICS_SUB_AGENT_ID_KEY] == world.so_id


async def test_editing_the_questions_changes_the_next_description(world):
    from models.system_one_agent import SystemOneAgent

    first = so_tools(await build_parent(world))[0].description
    agent = world.db.query(SystemOneAgent).get(world.so_id)
    agent.questions = [{"key": "only_one", "type": "noul", "instructions": "Q?"}]
    world.db.commit()
    world.db.expire_all()
    second = so_tools(await build_parent(world))[0].description
    assert "urgent" in first and "only_one (yes/no)" in second and "urgent" not in second


# ----------------------------------------------------------------- tool calls

async def test_calling_the_tool_returns_typed_json_and_records_a_child_event(world):
    tool = [t for t in (await build_parent(world))[-1]["tools"] if isinstance(t, IACTSystemOneTool)][0]
    with evaluate_patch():
        message = await tool.ainvoke(call_message(tool))
    content = json.loads(message.content)
    assert content["urgent"]["decision"] is True and content["area"]["decision"] == "billing"
    assert message.artifact.answers["area"].decision == "billing"
    await drain()
    events, answers = events_of(world.so_id)
    assert len(events) == 1
    e = events[0]
    assert str(e.parent_execution_id) == PARENT_EVENT
    assert (e.caller_type.value if hasattr(e.caller_type, "value") else e.caller_type) == "AGENT_AS_TOOL"
    assert {a.question_key for a in answers} == {"urgent", "area"} and all(a.event_id == e.event_id for a in answers)


async def test_a_system_one_failure_reaches_the_llm_as_text_and_the_turn_goes_on(world):
    tool = [t for t in (await build_parent(world))[-1]["tools"] if isinstance(t, IACTSystemOneTool)][0]
    with evaluate_patch(side_effect=SystemOneError("overloaded", "busy", 529)):
        message = await tool.ainvoke(call_message(tool))          # must not raise
    assert "overloaded" in message.content.lower() and message.artifact is None
    await drain()
    events, answers = events_of(world.so_id)
    assert len(events) == 1 and answers == []
    assert (events[0].status.value if hasattr(events[0].status, "value") else events[0].status) == "ERROR"
    assert events[0].error_code == "overloaded"


async def test_an_empty_text_is_text_for_the_llm_not_an_exception(world):
    tool = [t for t in (await build_parent(world))[-1]["tools"] if isinstance(t, IACTSystemOneTool)][0]
    with evaluate_patch() as ev:
        message = await tool.ainvoke(call_message(tool, text="   "))
    assert "empty" in message.content.lower()
    ev.assert_not_awaited()
    await drain()
    assert events_of(world.so_id) == ([], [])                      # rejected input is not an execution


# ------------------------------------------------------------------- two levels

async def test_a_system_one_tool_inside_a_sub_agent_links_to_the_top_level_event(world):
    calls = await build_parent(world)
    sub_agent_call = next(c for c in calls if any(isinstance(t, IACTSystemOneTool) for t in c["tools"]) and c is not calls[-1])
    nested = [t for t in sub_agent_call["tools"] if isinstance(t, IACTSystemOneTool)][0]
    assert nested.user_context["current_event_id"] == PARENT_EVENT           # the context travels down
    with evaluate_patch():
        await nested.ainvoke(call_message(nested))
    await drain()
    events, _ = events_of(world.so_id)
    assert [str(e.parent_execution_id) for e in events] == [PARENT_EVENT]
    assert len(so_tools(calls)) == 2                                         # one under the parent, one under the sub-agent


# --------------------------------------------------------------------- deletion

async def test_deleting_the_agent_with_metrics_history_leaves_nothing_behind(world):
    from repositories.agent_repository import AgentRepository

    tool = [t for t in (await build_parent(world))[-1]["tools"] if isinstance(t, IACTSystemOneTool)][0]
    with evaluate_patch():
        await tool.ainvoke(call_message(tool))
    await drain()
    assert len(events_of(world.so_id)[0]) == 1
    world.db.expire_all()
    assert AgentRepository.delete_by_id(world.db, world.so_id) is True
    assert events_of(world.so_id) == ([], [])                                # event and answer rows cascaded away


async def test_deleting_the_app_removes_agents_services_and_metrics(world):
    from models.agent_execution_event import AgentExecutionEvent
    from models.system_one_agent import SystemOneAgent
    from models.system_one_service import SystemOneService
    from services.app_service import AppService

    tool = [t for t in (await build_parent(world))[-1]["tools"] if isinstance(t, IACTSystemOneTool)][0]
    with evaluate_patch():
        await tool.ainvoke(call_message(tool))
    await drain()
    world.db.expire_all()
    assert AppService(world.db).delete_app(world.app_id) is True
    world.db.expire_all()
    assert world.db.query(SystemOneAgent).filter(SystemOneAgent.agent_id == world.so_id).count() == 0
    assert world.db.query(SystemOneService).filter(SystemOneService.service_id == world.service_id).count() == 0
    assert world.db.query(AgentExecutionEvent).filter(AgentExecutionEvent.app_id == world.app_id).count() == 0
