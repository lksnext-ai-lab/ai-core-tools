"""SystemOneEvaluator: state building, reduction, the server call, decisions and metrics (client mocked)."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import TypeAdapter

from models.ai_service import AIService
from models.system_one_agent import SystemOneAgent
from models.system_one_service import SystemOneService
from schemas.system_one_schemas import Question
from services import system_one_evaluator as module
from services.system_one_evaluator import SystemOneEvaluator, SystemOneSnapshot
from tools.system_one_client import Endpoint, SystemOneError

QA = TypeAdapter(Question).validate_python
QUESTIONS = [
    QA({"key": "urgent", "type": "noul", "instructions": "Is it urgent?", "threshold": 0.8}),
    QA({"key": "area", "type": "choice", "instructions": "Which area?", "min_probability": 0.6,
        "criteria": [{"key": "billing"}, {"key": "tech"}]}),
    QA({"key": "anger", "type": "score", "instructions": "How angry?", "criteria": ["Calm", "Angry"]}),
]
RAW = {
    "model": "nimble-latest",
    "usage": {"input_tokens": 400, "output_tokens": 4},
    "answers": {
        "urgent": {"type": "noul", "noul": 0.91},
        "area": {"type": "choice", "choice": "billing", "confidence": 0.39,
                 "probabilities": {"billing": 0.73, "tech": 0.27}},
        "anger": {"type": "score", "score": 0.7, "confidence": 0.2, "legend": {"0": "Calm", "1": "Angry"},
                  "probabilities": {"0": 0.6, "1": 0.4}},
    },
}
BUDGET_MSG = "Longest prompt has 40159 tokens; limit is 8192. Nothing was truncated."


def snapshot(summarize=None, max_state_chars=6000, questions=None):
    return SystemOneSnapshot(
        agent_id=3, app_id=9, agent_name="Triage", questions=questions or QUESTIONS,
        endpoint=Endpoint(base_url="http://so.test", model="nimble-latest", api_key="tok", max_concurrency=2, service_id=4),
        max_state_chars=max_state_chars, summarize=summarize,
        metrics_subject=SimpleNamespace(app_id=9, agent_id=3, service_id=None, ai_service=None, output_parser_id=None),
    )


@pytest.fixture
def mocks():
    with patch.object(module.system_one_client, "evaluate", AsyncMock(return_value=RAW)) as ev, \
         patch.object(module, "record_agent_execution") as rec:
        yield SimpleNamespace(evaluate=ev, record=rec)


async def run(snap, text="please call me today", files=None, ctx=None):
    return await SystemOneEvaluator().evaluate(snap, text, files or [], ctx if ctx is not None else {"user_id": 1})


# ------------------------------------------------------------------- success

async def test_happy_path_returns_typed_decisions(mocks):
    result = await run(snapshot())
    assert list(result.answers) == ["urgent", "area", "anger"]
    assert result.answers["urgent"].decision is True
    assert result.answers["area"].decision == "billing" and result.answers["area"].confidence == 0.39
    assert result.answers["anger"].decision == "Calm" and result.answers["anger"].expected_score == 0.7
    assert (result.state_reduction, result.model) == ("none", "nimble-latest")
    assert (result.usage.input_tokens, result.usage.output_tokens) == (400, 4)
    assert (result.original_chars, result.state_chars) == (len("please call me today"),) * 2
    mocks.evaluate.assert_awaited_once()
    endpoint, state, questions = mocks.evaluate.await_args.args
    assert endpoint.service_id == 4 and state == "please call me today" and questions == QUESTIONS


async def test_attachments_are_added_to_the_state(mocks):
    await run(snapshot(), "see attached", [{"filename": "a.pdf", "content": "PDF BODY", "type": "pdf"}])
    state = mocks.evaluate.await_args.args[1]
    assert state.startswith("see attached") and "a.pdf" in state and "PDF BODY" in state


# ----------------------------------------------------------- input rejection

@pytest.mark.parametrize("text,files", [
    ("", []), ("   \n", []),
    ("", [{"filename": "scan.pdf", "content": "  ", "type": "pdf"}]),          # scanned PDF, no text
])
async def test_nothing_to_evaluate_is_a_400_without_calling_the_server(mocks, text, files):
    with pytest.raises(HTTPException) as e:
        await run(snapshot(), text, files)
    assert e.value.status_code == 400 and "empty" in e.value.detail.lower()
    mocks.evaluate.assert_not_awaited()
    mocks.record.assert_not_called()          # rejected input is not an execution


async def test_images_are_rejected_as_text_only(mocks):
    with pytest.raises(HTTPException) as e:
        await run(snapshot(), "x", [{"filename": "i.png", "content": "b64", "type": "image"}])
    assert e.value.status_code == 400 and "text" in e.value.detail.lower()
    mocks.evaluate.assert_not_awaited()


# ------------------------------------------------------------ state reduction

async def test_long_text_is_summarized_when_the_agent_has_a_summarizer(mocks):
    summarize = AsyncMock(return_value="short summary")
    result = await run(snapshot(summarize=summarize, max_state_chars=1000), "word " * 5000)
    assert result.state_reduction == "summarized" and result.state_chars == len("short summary")
    assert result.original_chars == len(("word " * 5000).strip())
    assert mocks.evaluate.await_args.args[1] == "short summary"


async def test_long_text_is_truncated_without_a_summarizer(mocks):
    result = await run(snapshot(max_state_chars=1000), "word " * 5000)
    assert result.state_reduction == "truncated" and result.state_chars < 1000 and result.original_chars == len(("word " * 5000).strip())
    assert len(mocks.evaluate.await_args.args[1]) == result.state_chars


async def test_failing_summarizer_falls_back_to_truncation(mocks):
    result = await run(snapshot(summarize=AsyncMock(side_effect=RuntimeError("llm down")), max_state_chars=1000), "word " * 5000)
    assert result.state_reduction == "truncated"


# ------------------------------------------------------- budget error + retry

async def test_budget_422_retries_once_with_a_proportionally_smaller_state(mocks):
    mocks.evaluate.side_effect = [SystemOneError("invalid_request", BUDGET_MSG, 422), RAW]
    result = await run(snapshot(max_state_chars=6000), "word " * 1000)
    assert result.state_reduction == "truncated" and mocks.evaluate.await_count == 2
    first, second = (c.args[1] for c in mocks.evaluate.await_args_list)
    assert len(second) < len(first) * 0.25


async def test_second_budget_failure_is_a_422(mocks):
    mocks.evaluate.side_effect = SystemOneError("invalid_request", BUDGET_MSG, 422)
    with pytest.raises(HTTPException) as e:
        await run(snapshot(), "word " * 1000)
    assert e.value.status_code == 422 and mocks.evaluate.await_count == 2


async def test_other_invalid_requests_are_not_retried(mocks):
    mocks.evaluate.side_effect = SystemOneError("invalid_request", "Unknown model: nope", 422)
    with pytest.raises(HTTPException) as e:
        await run(snapshot())
    assert e.value.status_code == 422 and "Unknown model" in e.value.detail and mocks.evaluate.await_count == 1


# --------------------------------------------------------------------- errors

@pytest.mark.parametrize("kind,status", [("unavailable", 503), ("overloaded", 503), ("timeout", 504),
                                         ("unauthorized", 502), ("invalid_request", 422), ("invalid_response", 502)])
async def test_server_errors_map_to_http_errors_and_are_recorded(mocks, kind, status):
    mocks.evaluate.side_effect = SystemOneError(kind, f"boom {kind}", None)
    with pytest.raises(HTTPException) as e:
        await run(snapshot())
    assert e.value.status_code == status and f"boom {kind}" in e.value.detail
    kw = mocks.record.call_args.kwargs
    assert (kw["status"], kw["error_code"]) == ("ERROR", kind)
    assert not kw["system_one_answers"]                    # a failed evaluation leaves no answer rows


async def test_an_invalid_answer_from_the_server_is_an_error_not_a_crash(mocks):
    bad = json.loads(json.dumps(RAW))
    bad["answers"]["area"]["choice"] = "ghost"
    mocks.evaluate.return_value = bad
    with pytest.raises(HTTPException) as e:
        await run(snapshot())
    assert e.value.status_code == 502
    assert mocks.record.call_args.kwargs["status"] == "ERROR"


@pytest.mark.parametrize("usage", [{"input_tokens": "lots", "output_tokens": 1}, {"input_tokens": None}, ["a"], "x", 7, {}])
async def test_a_malformed_usage_does_not_lose_a_good_evaluation(mocks, usage):
    raw = json.loads(json.dumps(RAW))
    raw["usage"] = usage
    mocks.evaluate.return_value = raw
    result = await run(snapshot())
    assert result.answers["urgent"].decision is True
    assert result.usage is None or (result.usage.input_tokens >= 0)
    assert mocks.record.call_args.kwargs["status"] == "SUCCESS"


# -------------------------------------------------------------------- metrics

async def test_success_records_one_event_with_one_row_per_question(mocks):
    ctx = {"user_id": 7, "parent_execution_id": "abc", "caller_type_override": "AGENT_AS_TOOL"}
    await run(snapshot(), "hello there", [{"filename": "a.txt", "content": "x", "type": "text"}], ctx)
    mocks.record.assert_called_once()
    kw = mocks.record.call_args.kwargs
    assert kw["status"] == "SUCCESS" and kw["error_code"] is None and kw["fresh_agent"].agent_id == 3
    assert kw["user_context"] == ctx and kw["message"] == "hello there" and kw["result"] is None
    over = kw["event_overrides"]
    assert (over["input_tokens"], over["output_tokens"], over["total_tokens"]) == (400, 4, 404)
    assert (over["model_name"], over["provider"], over["llm_calls"]) == ("nimble-latest", "system_one", 0)
    assert (over["had_files"], over["file_count"], over["had_images"]) == (True, 1, False)
    rows = {r["question_key"]: r for r in kw["system_one_answers"]}
    assert set(rows) == {"urgent", "area", "anger"}
    assert rows["urgent"]["question_type"] == "noul" and rows["urgent"]["decision"] == "true" and rows["urgent"]["probability"] == 0.91
    assert rows["area"]["decision"] == "billing" and rows["area"]["confidence"] == 0.39
    assert rows["area"]["probabilities"] == {"billing": 0.73, "tech": 0.27}
    assert rows["anger"]["expected_score"] == 0.7 and rows["anger"]["state_reduction"] == "none"


async def test_undetermined_decision_is_recorded_as_null(mocks):
    raw = json.loads(json.dumps(RAW))
    raw["answers"]["area"]["probabilities"] = {"billing": 0.55, "tech": 0.45}
    mocks.evaluate.return_value = raw
    await run(snapshot())
    rows = {r["question_key"]: r for r in mocks.record.call_args.kwargs["system_one_answers"]}
    assert rows["area"]["decision"] is None and rows["area"]["probability"] == 0.55


async def test_summarization_counts_as_an_llm_call(mocks):
    await run(snapshot(summarize=AsyncMock(return_value="s"), max_state_chars=1000), "word " * 5000)
    assert mocks.record.call_args.kwargs["event_overrides"]["llm_calls"] == 1
    assert all(r["state_reduction"] == "summarized" for r in mocks.record.call_args.kwargs["system_one_answers"])


async def test_the_state_never_reaches_the_log(mocks, caplog):
    caplog.set_level("DEBUG")
    await run(snapshot(), "TOP SECRET CONTENT")
    assert "TOP SECRET" not in caplog.text and "tok" not in [r.getMessage() for r in caplog.records]


# ------------------------------------------------------------------- snapshot

def _agent(summarization_service=None, extra='{"max_concurrency": 3}', description="nimble-v2"):
    service = SystemOneService(service_id=4, name="Nimble", endpoint="http://so.test", api_key="tok",
                               description=description, extra_config=extra, app_id=9)
    agent = SystemOneAgent(agent_id=3, name="Triage", app_id=9, questions=[q.model_dump(mode="json") for q in QUESTIONS],
                           max_state_chars=4000)
    agent.system_one_service = service
    agent.summarization_service = summarization_service
    return agent


def test_snapshot_copies_everything_the_evaluation_needs():
    snap = SystemOneEvaluator.snapshot(_agent())
    assert snap.endpoint == Endpoint(base_url="http://so.test", model="nimble-v2", api_key="tok",
                                     max_concurrency=3, service_id=4)
    assert [q.key for q in snap.questions] == ["urgent", "area", "anger"]
    assert (snap.agent_id, snap.app_id, snap.agent_name, snap.max_state_chars) == (3, 9, "Triage", 4000)
    assert snap.summarize is None
    assert snap.metrics_subject.agent_id == 3 and snap.metrics_subject.service_id is None


def test_snapshot_defaults_model_and_concurrency():
    snap = SystemOneEvaluator.snapshot(_agent(extra=None, description=None))
    assert snap.endpoint.model == "nimble-latest" and snap.endpoint.max_concurrency == 1


async def test_snapshot_builds_a_summarizer_from_the_llm_service():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=SimpleNamespace(content="the summary"))
    with patch.object(module, "create_llm_from_service", return_value=llm) as build:
        snap = SystemOneEvaluator.snapshot(_agent(summarization_service=AIService(service_id=11, name="LLM")))
    assert snap.summarize is not None and build.call_args.kwargs.get("temperature") == 0
    out = await snap.summarize("long " * 10, QUESTIONS, 500)
    assert out == "the summary"
    prompt = llm.ainvoke.await_args.args[0]
    assert "Is it urgent?" in prompt and "Which area?" in prompt and "500" in prompt


async def test_summarizer_handles_block_content_and_caps_the_input():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=SimpleNamespace(content=[{"type": "text", "text": "part one "}, {"type": "text", "text": "part two"}]))
    with patch.object(module, "create_llm_from_service", return_value=llm):
        snap = SystemOneEvaluator.snapshot(_agent(summarization_service=AIService(service_id=11, name="LLM")))
    assert await snap.summarize("x" * 500_000, QUESTIONS, 500) == "part one part two"
    assert len(llm.ainvoke.await_args.args[0]) < 200_000


def test_snapshot_survives_an_llm_that_cannot_be_built():
    with patch.object(module, "create_llm_from_service", side_effect=RuntimeError("no key")):
        snap = SystemOneEvaluator.snapshot(_agent(summarization_service=AIService(service_id=11, name="LLM")))
    assert snap.summarize is None
