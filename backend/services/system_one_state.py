"""Build the text ("state") a System One agent evaluates, and make it fit the server's token budget.

The server measures 8192 tokens PER QUESTION PROMPT (the state plus that one question), so the budget
left for the state is ``max_state_chars`` minus the longest question. A text that does not fit is
summarized with the agent's optional LLM; without it (or if the summary fails) it is truncated.
The reduction is always reported, never silent: deciding on half a document without knowing is worse
than an error.
"""
import re
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, List, Literal, Optional, Tuple

from schemas.system_one_schemas import ChoiceQuestion, NoulQuestion, Question
from utils.logger import get_logger

logger = get_logger(__name__)

_MIN_BUDGET_CHARS = 200
_QUESTION_MARGIN_CHARS = 50
MIN_TEXT_ROOM_CHARS = 500   # what a question must leave of the per-prompt budget for the text itself
_BUDGET_ERROR = re.compile(r"Longest prompt has (\d+) tokens; limit is (\d+)")

Summarizer = Callable[[str, List[Question], int], Awaitable[str]]


@dataclass
class ReducedState:
    text: str
    mode: Literal["none", "summarized", "truncated"]
    original_chars: int


def build_state(text: str, files: List[Dict]) -> str:
    """The text plus the extracted text of each attachment (``files`` come from the attachment pipeline)."""
    pieces = [text.strip()] if text and text.strip() else []
    for file in files or []:
        if file.get("type") == "image":
            raise ValueError("System One evaluates text only: images are not supported")
        content = file.get("content") or ""
        if content.strip():                       # e.g. a scanned PDF has no extractable text
            pieces.append(f"--- {file['filename']} ---\n{content.strip()}")
    return "\n\n".join(pieces)


def question_overhead_chars(questions: List[Question]) -> int:
    """Characters of the longest question prompt (instructions plus options/levels) plus a margin."""
    def size(q: Question) -> int:
        total = len(q.instructions)
        if isinstance(q, NoulQuestion):
            if q.criteria:
                total += len(q.criteria.true) + len(q.criteria.false)
        elif isinstance(q, ChoiceQuestion):
            total += sum(len(o.key) + len(o.description or "") for o in q.criteria)
        else:
            total += sum(len(level) for level in q.criteria)
        return total

    return max((size(q) for q in questions), default=0) + _QUESTION_MARGIN_CHARS


def parse_budget_error(message: str) -> Optional[Tuple[int, int]]:
    """``(tokens, limit)`` from the server's "Longest prompt has N tokens; limit is L" error."""
    match = _BUDGET_ERROR.search(message or "")
    return (int(match.group(1)), int(match.group(2))) if match else None


def shrink_factor(n_tokens: int, limit: int) -> float:
    """Fraction of the text to keep so that it fits ``limit`` tokens, with a 10% margin."""
    if n_tokens <= 0 or limit <= 0:
        return 0.5
    return min(limit / n_tokens * 0.9, 0.9)


def truncate_at_word(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    if not text[max_chars].isspace():
        boundary = max(cut.rfind(" "), cut.rfind("\n"), cut.rfind("\t"))
        if boundary > 0:
            cut = cut[:boundary]
    return cut.rstrip()


async def reduce_state(state: str, questions: List[Question], max_state_chars: int,
                       summarize: Optional[Summarizer]) -> ReducedState:
    original = len(state)
    budget = max(max_state_chars - question_overhead_chars(questions), _MIN_BUDGET_CHARS)
    if original <= budget:
        return ReducedState(state, "none", original)

    if summarize is not None:
        try:
            summary = (await summarize(state, questions, budget) or "").strip()
        except Exception:
            logger.warning("[system_one] summarization failed; truncating instead", exc_info=True)
            summary = ""
        if summary:
            if len(summary) <= budget:
                return ReducedState(summary, "summarized", original)
            return ReducedState(truncate_at_word(summary, budget), "truncated", original)

    return ReducedState(truncate_at_word(state, budget), "truncated", original)
