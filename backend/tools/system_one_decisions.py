"""Turn the raw System One answer of each question into a typed decision.

``decision`` is the usable result; the probabilities stay alongside it. ``confidence`` (1 minus the
normalized entropy of ALL options) is returned but never gates a decision: it can be low even when the
picked option is clearly the best (measured: 0.73 for the picked option with confidence 0.39).
"""
from typing import Any, Dict, List

from schemas.system_one_schemas import (
    Answer, ChoiceAnswer, ChoiceQuestion, NoulAnswer, NoulQuestion, Question, ScoreAnswer, ScoreQuestion,
)
from tools.system_one_client import SystemOneError


def _invalid(message: str) -> SystemOneError:
    return SystemOneError("invalid_response", f"Unexpected System One response: {message}")


def _decide_noul(question: NoulQuestion, raw: Dict[str, Any]) -> NoulAnswer:
    probability = float(raw["noul"])
    return NoulAnswer(
        decision=probability >= question.threshold,   # exactly at the threshold counts as yes
        probability=probability,
        threshold=question.threshold,
    )


def _below_minimum(question, probability: float) -> bool:
    return question.min_probability is not None and probability < question.min_probability


def _decide_choice(question: ChoiceQuestion, raw: Dict[str, Any]) -> ChoiceAnswer:
    probabilities = {str(k): float(v) for k, v in raw["probabilities"].items()}
    choice = raw["choice"]                            # the server's pick settles ties
    if choice not in probabilities:
        raise _invalid(f"'{question.key}' picked '{choice}', which is not one of its options")
    probability = probabilities[choice]
    return ChoiceAnswer(
        decision=None if _below_minimum(question, probability) else choice,
        choice=choice,
        probability=probability,
        probabilities=probabilities,
        confidence=float(raw["confidence"]),
        min_probability=question.min_probability,
    )


def _decide_score(question: ScoreQuestion, raw: Dict[str, Any]) -> ScoreAnswer:
    probabilities = {str(k): float(v) for k, v in raw["probabilities"].items()}
    try:
        # Most probable level; on a tie the lower level wins. NOT round(expected): with a bimodal
        # distribution the rounded expected value is a level nobody picked.
        level_index = int(max(probabilities, key=lambda k: (probabilities[k], -int(k))))
    except ValueError:
        raise _invalid(f"'{question.key}' has non-numeric levels")
    if not 0 <= level_index < len(question.criteria):
        raise _invalid(f"'{question.key}' picked level {level_index}, outside its {len(question.criteria)} levels")
    probability = probabilities[str(level_index)]
    return ScoreAnswer(
        decision=None if _below_minimum(question, probability) else question.criteria[level_index],
        level_index=level_index,
        probability=probability,
        expected_score=float(raw["score"]),
        legend={str(k): str(v) for k, v in raw["legend"].items()},
        probabilities=probabilities,
        confidence=float(raw["confidence"]),
        min_probability=question.min_probability,
    )


def decide(question: Question, raw: Dict[str, Any]) -> Answer:
    if isinstance(question, NoulQuestion):
        return _decide_noul(question, raw)
    if isinstance(question, ChoiceQuestion):
        return _decide_choice(question, raw)
    return _decide_score(question, raw)


def decide_all(questions: List[Question], raw_answers: Dict[str, Any]) -> Dict[str, Answer]:
    """Decisions keyed by question key, in the order the questions were defined."""
    return {q.key: decide(q, raw_answers[q.key]) for q in questions}
