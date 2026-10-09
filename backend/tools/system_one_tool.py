"""A System One agent used as a tool by another agent.

Typed input (``{text}``), a description generated from the agent's questions (so the calling LLM knows what
it will get back), a compact JSON the LLM reads and the full ``SystemOneResult`` as the tool message artifact.
A failing System One never aborts the calling agent's turn: the LLM gets a message and can carry on.
"""
import json
from typing import Any, Dict, List, Literal, Optional, Tuple, Type

from fastapi import HTTPException
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from schemas.system_one_schemas import ChoiceAnswer, NoulAnswer, ScoreAnswer, SystemOneResult, SystemOneToolInput
from services.system_one_evaluator import SystemOneEvaluator, SystemOneSnapshot
from utils.logger import get_logger
from utils.schema_utils import sanitize_identifier

logger = get_logger(__name__)

_DEFAULT_DESCRIPTION = "Evaluates a text with System One."


def _question_line(question) -> str:
    if question.type == "noul":
        kind = "yes/no"
    elif question.type == "choice":
        kind = "choice: " + " | ".join(o.key for o in question.criteria)
    else:
        kind = f"score 0-{len(question.criteria) - 1}: " + ", ".join(question.criteria)
    return f"- {question.key} ({kind}): {question.instructions}"


def build_tool_description(snapshot: SystemOneSnapshot) -> str:
    """Agent description plus one line per question; regenerated whenever the tool is built."""
    head = snapshot.agent_description.strip() or _DEFAULT_DESCRIPTION
    questions = "\n".join(_question_line(q) for q in snapshot.questions)
    return (
        f"{head}\n"
        "Evaluates the given text and returns a JSON object with one entry per question:\n"
        f"{questions}\n"
        "Each entry has a \"decision\" (null when the answer does not reach the question's minimum probability) "
        "and its probabilities. Input: the text to evaluate."
    )


def _r(value: float) -> float:
    return round(float(value), 3)


def _content_entry(answer) -> Dict[str, Any]:
    if isinstance(answer, NoulAnswer):
        return {"decision": answer.decision, "probability": _r(answer.probability)}
    if isinstance(answer, ChoiceAnswer):
        return {
            "decision": answer.decision,
            "probability": _r(answer.probability),
            "probabilities": {k: _r(v) for k, v in answer.probabilities.items()},
            "confidence": _r(answer.confidence),
        }
    assert isinstance(answer, ScoreAnswer)
    return {
        "decision": answer.decision,
        "probability": _r(answer.probability),
        "probabilities": {answer.legend.get(k, k): _r(v) for k, v in answer.probabilities.items()},
        "expected_score": _r(answer.expected_score),
        "confidence": _r(answer.confidence),
    }


def format_tool_content(result: SystemOneResult) -> str:
    """The compact JSON the calling LLM reads (the full result travels as the artifact)."""
    content: Dict[str, Any] = {key: _content_entry(answer) for key, answer in result.answers.items()}
    content["state_reduction"] = result.state_reduction
    return json.dumps(content, ensure_ascii=False, separators=(",", ":"))


def _error_text(exc: HTTPException) -> str:
    if exc.status_code == 503:
        return "System One is unavailable or overloaded; try again later."
    if exc.status_code == 504:
        return "System One timed out; try again later."
    if exc.status_code == 502:
        return "System One returned an unexpected response."
    if exc.status_code == 422:
        return f"System One rejected the request: {exc.detail}"
    return f"System One could not evaluate the text: {exc.detail}"


class IACTSystemOneTool(BaseTool):
    """Agent-as-tool for a System One agent."""

    name: str = "system_one_agent_tool"
    description: str = _DEFAULT_DESCRIPTION
    args_schema: Type[BaseModel] = SystemOneToolInput
    response_format: Literal["content", "content_and_artifact"] = "content_and_artifact"
    snapshot: Any = None
    user_context: Optional[Dict[str, Any]] = None
    attached_files: Optional[List[Dict]] = None

    @classmethod
    async def create(cls, agent, user_context: Optional[Dict] = None, attached_files: Optional[List[Dict]] = None,
                     user_message: Optional[str] = None) -> "IACTSystemOneTool":
        snapshot = SystemOneEvaluator.snapshot(agent)
        return cls(
            name=sanitize_identifier(agent.name),
            description=build_tool_description(snapshot),
            snapshot=snapshot,
            user_context=user_context,
            attached_files=attached_files or [],
        )

    def _run(self, *args: Any, **kwargs: Any):
        raise NotImplementedError("System One tools are async only")

    async def _arun(self, text: str, run_manager: Any = None, **kwargs: Any) -> Tuple[str, Optional[SystemOneResult]]:
        context = self.user_context or {}
        evaluation_context = {
            **context,
            "parent_execution_id": context.get("current_event_id"),
            "caller_type_override": "AGENT_AS_TOOL",
        }
        # Images attached to the parent's turn are its own context, not this tool's input (text only).
        files = [f for f in (self.attached_files or []) if f.get("type") != "image"]
        try:
            result = await SystemOneEvaluator().evaluate(self.snapshot, text, files, evaluation_context)
        except HTTPException as exc:
            return _error_text(exc), None
        except Exception as exc:
            # Only the exception type is logged and returned: its message may carry request details.
            logger.error("System One tool failed (agent_id=%s): %s", self.snapshot.agent_id, type(exc).__name__)
            return "System One failed to evaluate the text.", None
        return format_tool_content(result), result
