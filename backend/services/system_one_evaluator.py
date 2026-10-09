"""One System One evaluation: build the state, make it fit, ask the server, decide, record metrics.

The evaluator works on a ``SystemOneSnapshot`` (plain values, no ORM objects) built while the DB session is
alive. That makes it safe to run from places that have no session (a tool called by another agent) and from
worker threads, where lazy-loading a detached agent would fail.

v1 is text only: images are rejected, not ignored.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pydantic import TypeAdapter

from models.system_one_agent import SystemOneAgent
from schemas.system_one_schemas import Question, QuestionList, SystemOneResult, Usage
from services.agent_metrics_recorder import record_agent_execution
from services.system_one_service_service import max_concurrency_of
from services.system_one_state import (
    ReducedState, Summarizer, build_state, parse_budget_error, reduce_state, shrink_factor, truncate_at_word,
)
from tools import system_one_client
from tools.aiServiceTools import create_llm_from_service
from tools.system_one_client import Endpoint, SystemOneError
from tools.system_one_decisions import decide_all
from utils.logger import get_logger

logger = get_logger(__name__)

_SUMMARY_INPUT_CAP_CHARS = 120_000      # what we hand to the summarizing LLM at most
_PROVIDER = "system_one"
_HTTP_STATUS = {
    "unavailable": 503, "overloaded": 503, "timeout": 504,
    "unauthorized": 502, "invalid_request": 422, "invalid_response": 502,
}


@dataclass(frozen=True)
class SystemOneSnapshot:
    agent_id: int
    app_id: int
    agent_name: str
    questions: List[Question]
    endpoint: Endpoint
    max_state_chars: int
    summarize: Optional[Summarizer]
    metrics_subject: Any            # what the metrics recorder reads from an agent (ids only)
    agent_description: str = ""


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block if isinstance(block, str) else str(block.get("text", "")) for block in content
            if isinstance(block, (str, dict))
        )
    return ""


def _question_lines(questions: List[Question]) -> str:
    lines = []
    for q in questions:
        line = f"- {q.instructions}"
        if q.type == "choice":
            line += " Options: " + ", ".join(o.key for o in q.criteria)
        elif q.type == "score":
            line += " Levels: " + ", ".join(q.criteria)
        lines.append(line)
    return "\n".join(lines)


def _make_summarizer(llm: Any) -> Summarizer:
    async def summarize(text: str, questions: List[Question], budget: int) -> str:
        # "At most": asking for a size close to the budget made the LLM write ~5x more and take ~10x longer in a
        # real test (110 s vs 11 s), so the summary is allowed to be short.
        prompt = (
            f"Summarize the text below in at most {budget} characters. Keep every detail needed to answer "
            f"these questions about it:\n{_question_lines(questions)}\n\n"
            f"Reply with the summary only.\n\nText:\n{text[:_SUMMARY_INPUT_CAP_CHARS]}"
        )
        reply = await llm.ainvoke(prompt)
        return _text_of(getattr(reply, "content", reply))

    return summarize


def _parse_usage(raw: Dict[str, Any]) -> Optional[Usage]:
    """Token usage as reported by the server; a malformed value must not lose an otherwise good evaluation."""
    usage = raw.get("usage")
    if not isinstance(usage, dict):
        return None
    try:
        return Usage(input_tokens=int(usage["input_tokens"]), output_tokens=int(usage["output_tokens"]))
    except (KeyError, TypeError, ValueError):
        return None


def _serialize_decision(decision: Any) -> Optional[str]:
    if decision is None:
        return None
    if isinstance(decision, bool):
        return "true" if decision else "false"
    return str(decision)


def _answer_rows(result: SystemOneResult) -> List[Dict[str, Any]]:
    return [
        {
            "question_key": key,
            "question_type": answer.type,
            "decision": _serialize_decision(answer.decision),
            "probability": answer.probability,
            "expected_score": getattr(answer, "expected_score", None),
            "confidence": getattr(answer, "confidence", None),
            "probabilities": getattr(answer, "probabilities", None),
            "state_reduction": result.state_reduction,
        }
        for key, answer in result.answers.items()
    ]


_GENERIC = {
    "invalid_request": "System One rejected the request. Check the agent's questions and the size of the text.",
    "unavailable": "System One is unavailable",
    "overloaded": "System One is busy, try again shortly",
    "timeout": "System One did not answer in time",
    "unauthorized": "System One rejected the service credentials",
    "invalid_response": "System One returned an unexpected response",
}


def _public_detail(exc: SystemOneError) -> str:
    """What callers (viewers, API keys) may read about a failure.

    Anything built from an HTTP response (``status`` set) carries text the server — or whatever answers at
    the configured URL — chose, so it is logged for the administrator but not echoed. The one exception is
    the token-budget message, which tells the caller their text is too long.
    """
    if exc.status is None or parse_budget_error(exc.message) is not None:
        return exc.message
    logger.warning("[system_one] %s (HTTP %s): %s", exc.kind, exc.status, exc.message[:200])
    return _GENERIC[exc.kind]


class SystemOneEvaluator:

    @staticmethod
    def snapshot(agent: SystemOneAgent) -> SystemOneSnapshot:
        """Copy what an evaluation needs out of the ORM agent (call while its session is alive)."""
        service = agent.system_one_service
        if service is None:
            raise HTTPException(
                status_code=409,
                detail="This agent has no System One service (it was deleted): choose another one in the agent's settings",
            )
        if not service.description:
            raise HTTPException(
                status_code=409,
                detail="The agent's System One service has no model: edit the service and choose one",
            )
        endpoint = Endpoint(
            base_url=service.endpoint or "",
            model=service.description,
            api_key=service.api_key,
            max_concurrency=max_concurrency_of(service),
            service_id=service.service_id,
        )
        summarize = None
        if agent.summarization_service is not None:
            try:
                summarize = _make_summarizer(create_llm_from_service(agent.summarization_service, temperature=0))
            except Exception:
                logger.warning("[system_one] summarization LLM of agent %s could not be built; "
                               "long texts will be truncated", agent.agent_id, exc_info=True)
        return SystemOneSnapshot(
            agent_id=agent.agent_id,
            app_id=agent.app_id,
            agent_name=agent.name or "",
            agent_description=agent.description or "",
            questions=TypeAdapter(QuestionList).validate_python(agent.questions),
            endpoint=endpoint,
            max_state_chars=agent.max_state_chars or 6000,
            summarize=summarize,
            metrics_subject=SimpleNamespace(app_id=agent.app_id, agent_id=agent.agent_id, service_id=None,
                                            ai_service=None, output_parser_id=None),
        )

    @staticmethod
    async def _call(snapshot: SystemOneSnapshot, reduced: ReducedState):
        """Ask the server; on its "Longest prompt has N tokens" error shrink the state once and retry."""
        try:
            return await system_one_client.evaluate(snapshot.endpoint, reduced.text, snapshot.questions), reduced
        except SystemOneError as exc:
            parsed = parse_budget_error(exc.message) if exc.kind == "invalid_request" else None
            if parsed is None:
                raise
            shrunk = truncate_at_word(reduced.text, int(len(reduced.text) * shrink_factor(*parsed)))
            if not shrunk.strip():
                raise
            reduced = ReducedState(shrunk, "truncated", reduced.original_chars)
            logger.info("[system_one] state over the server's token budget; retrying with %d chars", len(shrunk))
            return await system_one_client.evaluate(snapshot.endpoint, reduced.text, snapshot.questions), reduced

    async def evaluate(self, snapshot: SystemOneSnapshot, text: str, files: List[Dict],
                       user_context: Dict[str, Any]) -> SystemOneResult:
        try:
            state = build_state(text, files)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if not state.strip():
            raise HTTPException(
                status_code=400,
                detail="Nothing to evaluate: the text is empty and the attachments contain no extractable text",
            )

        started_at, clock = datetime.utcnow(), perf_counter()
        result: Optional[SystemOneResult] = None
        failure: Optional[Exception] = None
        summarized = False
        try:
            reduced = await reduce_state(state, snapshot.questions, snapshot.max_state_chars, snapshot.summarize)
            summarized = reduced.mode == "summarized"
            raw, reduced = await self._call(snapshot, reduced)
            result = SystemOneResult(
                answers=decide_all(snapshot.questions, raw["answers"]),
                state_reduction=reduced.mode,
                original_chars=reduced.original_chars,
                state_chars=len(reduced.text),
                evaluated_text=reduced.text if reduced.mode != "none" else None,
                model=str(raw.get("model") or snapshot.endpoint.model),
                usage=_parse_usage(raw),
            )
            return result
        except SystemOneError as exc:
            failure = exc
            raise HTTPException(status_code=_HTTP_STATUS[exc.kind], detail=_public_detail(exc)) from exc
        except Exception as exc:
            failure = exc
            raise
        finally:
            self._record(snapshot, text, files, user_context, started_at, clock, result, failure, summarized)

    @staticmethod
    def _record(snapshot, text, files, user_context, started_at, clock, result, failure, summarized) -> None:
        finished_at = datetime.utcnow()
        duration_ms = int((perf_counter() - clock) * 1000)
        overrides: Dict[str, Any] = {
            "model_name": result.model if result else snapshot.endpoint.model,
            "provider": _PROVIDER,
            "llm_calls": 1 if summarized else 0,
            "had_files": len(files) > 0,
            "file_count": len(files),
            "had_images": False,
        }
        if result is not None and result.usage is not None:
            overrides.update(
                input_tokens=result.usage.input_tokens,
                output_tokens=result.usage.output_tokens,
                total_tokens=result.usage.input_tokens + result.usage.output_tokens,
            )
        error_code = error_message = None
        if failure is not None:
            error_code = failure.kind if isinstance(failure, SystemOneError) else type(failure).__name__
            error_message = str(failure)[:2000]
        record_agent_execution(
            event_id=str(uuid.uuid4()),
            fresh_agent=snapshot.metrics_subject,
            user_context=user_context,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            status="ERROR" if failure is not None else "SUCCESS",
            error_code=error_code,
            error_message=error_message,
            result=None,
            image_files=[],
            message=text,
            event_overrides=overrides,
            system_one_answers=_answer_rows(result) if result is not None else None,
        )
        logger.info(
            "[system_one] agent_id=%s questions=%d reduction=%s duration_ms=%d status=%s",
            snapshot.agent_id, len(snapshot.questions), result.state_reduction if result else "-",
            duration_ms, "ERROR" if failure is not None else "SUCCESS",
        )
