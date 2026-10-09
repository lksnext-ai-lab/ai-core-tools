"""IACTSystemOneTool: typed input, generated description, compact content + typed artifact, graceful errors."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from pydantic import TypeAdapter

from models.system_one_agent import SystemOneAgent
from models.system_one_service import SystemOneService
from schemas.system_one_schemas import Question, SystemOneResult
from services.system_one_evaluator import SystemOneEvaluator, SystemOneSnapshot
from tools import system_one_tool as module
from tools.agentTools import _tag_untyped_tools, discover_tool
from tools.system_one_client import Endpoint
from tools.system_one_decisions import decide_all
from tools.system_one_tool import IACTSystemOneTool, build_tool_description, format_tool_content

QA = TypeAdapter(Question).validate_python
QUESTIONS = [
    QA({"key": "is_urgent", "type": "noul", "instructions": "Is this urgent?"}),
    QA({"key": "area", "type": "choice", "instructions": "Which department?", "min_probability": 0.6,
        "criteria": [{"key": "billing"}, {"key": "support"}]}),
    QA({"key": "anger", "type": "score", "instructions": "How angry?", "criteria": ["Calm", "Annoyed", "Angry"]}),
]
RAW = {
    "is_urgent": {"type": "noul", "noul": 0.9123456},
    "area": {"type": "choice", "choice": "billing", "confidence": 0.39,
             "probabilities": {"billing": 0.7312, "support": 0.2688}},
    "anger": {"type": "score", "score": 1.9087, "confidence": 0.188, "legend": {"0": "Calm", "1": "Annoyed", "2": "Angry"},
              "probabilities": {"0": 0.025, "1": 0.262, "2": 0.713}},
}


def snap(description="Classifies support tickets", questions=None):
    return SystemOneSnapshot(
        agent_id=3, app_id=9, agent_name="Triage Bot", questions=questions or QUESTIONS,
        endpoint=Endpoint(base_url="http://so.test", model="nimble-latest", api_key=None, max_concurrency=1, service_id=4),
        max_state_chars=6000, summarize=None,
        metrics_subject=SimpleNamespace(app_id=9, agent_id=3, service_id=None, ai_service=None, output_parser_id=None),
        agent_description=description,
    )


def result(reduction="none"):
    return SystemOneResult(answers=decide_all(QUESTIONS, RAW), state_reduction=reduction, original_chars=100,
                           state_chars=100, model="nimble-latest")


async def make_tool(**kw):
    s = kw.pop("snapshot", snap())
    with patch.object(SystemOneEvaluator, "snapshot", return_value=s):
        agent = SimpleNamespace(agent_id=3, name="Triage Bot")
        return await IACTSystemOneTool.create(agent, **kw)


# --------------------------------------------------------------- description

def test_description_is_generated_from_the_questions():
    d = build_tool_description(snap())
    assert d.startswith("Classifies support tickets")
    assert "is_urgent (yes/no)" in d and "Is this urgent?" in d
    assert "area (choice: billing | support)" in d and "Which department?" in d
    assert "anger (score 0-2: Calm, Annoyed, Angry)" in d
    assert "null" in d                                         # decision may be null when below the minimum


def test_description_changes_when_the_questions_change():
    only = [QA({"key": "only_one", "type": "noul", "instructions": "Q?"})]
    d = build_tool_description(snap(questions=only))
    assert "only_one (yes/no)" in d and "area" not in d


def test_description_has_a_default_when_the_agent_has_none():
    assert build_tool_description(snap(description="")).startswith("Evaluates a text with System One")


# -------------------------------------------------------------------- schema

async def test_input_schema_is_exactly_text():
    tool = await make_tool()
    schema = tool.args_schema.model_json_schema()
    assert set(schema["properties"]) == {"text"} and schema["properties"]["text"]["type"] == "string"
    assert schema["required"] == ["text"] and tool.name == "Triage_Bot" or tool.name.startswith("Triage")


# ------------------------------------------------------------------- content

def test_content_is_compact_json_with_decisions():
    content = json.loads(format_tool_content(result()))
    assert content["state_reduction"] == "none"
    assert content["is_urgent"] == {"decision": True, "probability": 0.912}
    assert content["area"]["decision"] == "billing" and content["area"]["probability"] == 0.731
    assert content["area"]["probabilities"] == {"billing": 0.731, "support": 0.269} and content["area"]["confidence"] == 0.39
    assert content["anger"]["decision"] == "Angry" and content["anger"]["probability"] == 0.713
    assert "original_chars" not in json.dumps(content) and "legend" not in json.dumps(content)


def test_content_reports_summarization_and_null_decisions():
    raw = json.loads(json.dumps(RAW))
    raw["area"]["probabilities"] = {"billing": 0.55, "support": 0.45}
    r = SystemOneResult(answers=decide_all(QUESTIONS, raw), state_reduction="summarized", original_chars=9, state_chars=3, model="m")
    content = json.loads(format_tool_content(r))
    assert content["state_reduction"] == "summarized" and content["area"]["decision"] is None


# --------------------------------------------------------------------- _arun

async def test_arun_returns_content_and_the_typed_artifact():
    tool = await make_tool(user_context={"user_id": 1, "current_event_id": "parent-evt"},
                           attached_files=[{"filename": "a.txt", "content": "BODY", "type": "text"},
                                           {"filename": "i.png", "content": "b64", "type": "image"}])
    with patch.object(SystemOneEvaluator, "evaluate", AsyncMock(return_value=result())) as ev:
        content, artifact = await tool._arun(text="please help")
    assert json.loads(content)["is_urgent"]["decision"] is True and isinstance(artifact, SystemOneResult)
    snapshot, text, files, ctx = ev.await_args.args
    assert snapshot.agent_id == 3 and text == "please help"
    assert files == [{"filename": "a.txt", "content": "BODY", "type": "text"}]     # the parent's images are not input
    assert ctx["caller_type_override"] == "AGENT_AS_TOOL" and ctx["parent_execution_id"] == "parent-evt" and ctx["user_id"] == 1


async def test_through_langchain_the_tool_message_carries_the_artifact():
    tool = await make_tool()
    with patch.object(SystemOneEvaluator, "evaluate", AsyncMock(return_value=result())):
        message = await tool.ainvoke({"name": tool.name, "args": {"text": "hi"}, "id": "call-1", "type": "tool_call"})
    assert json.loads(message.content)["area"]["decision"] == "billing"
    assert isinstance(message.artifact, SystemOneResult)


def test_the_artifact_survives_the_checkpointer_serializer():
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    serde = JsonPlusSerializer()
    restored = serde.loads_typed(serde.dumps_typed(result()))
    assert restored == result() or restored.model_dump() == result().model_dump()


@pytest.mark.parametrize("status,fragment", [
    (503, "unavailable"), (504, "timed out"), (502, "unexpected"), (422, "rejected"), (400, "empty"),
])
async def test_server_problems_come_back_as_text_and_do_not_raise(status, fragment):
    tool = await make_tool()
    with patch.object(SystemOneEvaluator, "evaluate", AsyncMock(side_effect=HTTPException(status, "the detail: empty"))):
        content, artifact = await tool._arun(text="hi")
    assert artifact is None and fragment in content.lower()


async def test_unexpected_errors_are_contained_too():
    tool = await make_tool()
    with patch.object(SystemOneEvaluator, "evaluate", AsyncMock(side_effect=RuntimeError("secret internals"))):
        content, artifact = await tool._arun(text="hi")
    assert artifact is None and "System One" in content and "secret internals" not in content


def test_sync_run_is_not_supported():
    tool = IACTSystemOneTool.model_construct(name="x", description="d", snapshot=snap())
    with pytest.raises(NotImplementedError):
        tool._run(text="hi")


# --------------------------------------------------- create / discover / tags

async def test_create_snapshots_a_real_agent_and_names_the_tool():
    service = SystemOneService(service_id=4, name="Nimble", endpoint="http://so.test", description="nimble-latest", app_id=9)
    agent = SystemOneAgent(agent_id=3, name="Triage Bot!", description="Routes tickets", app_id=9, max_state_chars=6000,
                           questions=[q.model_dump(mode="json") for q in QUESTIONS])
    agent.system_one_service = service
    tool = await IACTSystemOneTool.create(agent, user_context={"user_id": 1})
    assert " " not in tool.name and "!" not in tool.name and tool.name.startswith("Triage")
    assert tool.description.startswith("Routes tickets") and "area (choice" in tool.description
    assert tool.snapshot.endpoint.service_id == 4


async def test_discover_tool_routes_system_one_agents():
    sentinel = object()
    agent = SimpleNamespace(type="system_one_agent")
    with patch.object(IACTSystemOneTool, "create", AsyncMock(return_value=sentinel)) as create:
        out = await discover_tool(agent, user_context={"u": 1}, attached_files=[{"filename": "f"}], user_message="hi")
    assert out is sentinel
    assert create.await_args.args == (agent,) and create.await_args.kwargs["user_context"] == {"u": 1}
    assert create.await_args.kwargs["attached_files"] == [{"filename": "f"}]


async def test_the_tool_is_tagged_as_an_agent_with_its_sub_agent_id():
    from services.agent_metrics_collector import METRICS_SUB_AGENT_ID_KEY, METRICS_TOOL_TYPE_KEY

    tool = await make_tool()
    _tag_untyped_tools([tool])
    assert tool.metadata[METRICS_TOOL_TYPE_KEY] == "AGENT" and tool.metadata[METRICS_SUB_AGENT_ID_KEY] == 3
