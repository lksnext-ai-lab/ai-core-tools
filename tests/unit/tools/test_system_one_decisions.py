import pytest
from pydantic import TypeAdapter

from schemas.system_one_schemas import Question
from tools.system_one_client import SystemOneError
from tools.system_one_decisions import decide, decide_all

QA = TypeAdapter(Question).validate_python
NOUL = QA({"key": "u", "type": "noul", "instructions": "q", "threshold": 0.8})
CHOICE = QA({"key": "a", "type": "choice", "instructions": "q", "min_probability": 0.6,
             "criteria": [{"key": "billing"}, {"key": "tech"}, {"key": "sales"}]})
SCORE = QA({"key": "s", "type": "score", "instructions": "q", "min_probability": 0.4,
            "criteria": ["Calm", "Annoyed", "Angry", "Furious"]})
LEGEND = {"0": "Calm", "1": "Annoyed", "2": "Angry", "3": "Furious"}


def test_noul_exactly_at_threshold_is_true():
    assert decide(NOUL, {"type": "noul", "noul": 0.8}).decision is True
    assert decide(NOUL, {"type": "noul", "noul": 0.79}).decision is False
    a = decide(NOUL, {"type": "noul", "noul": 0.91})
    assert (a.probability, a.threshold) == (0.91, 0.8)


def test_choice_below_min_probability_is_null_but_keeps_probabilities():
    raw = {"type": "choice", "choice": "tech", "confidence": 0.3,
           "probabilities": {"billing": 0.3, "tech": 0.5, "sales": 0.2}}
    a = decide(CHOICE, raw)
    assert a.decision is None and a.choice == "tech" and a.probability == 0.5
    assert a.probabilities["billing"] == 0.3 and a.confidence == 0.3


def test_choice_above_min_probability_returns_option_even_with_low_confidence():
    raw = {"type": "choice", "choice": "billing", "confidence": 0.39,
           "probabilities": {"billing": 0.73, "tech": 0.03, "sales": 0.24}}
    a = decide(CHOICE, raw)
    assert a.decision == "billing" and a.confidence == 0.39      # confidence does NOT gate the decision


def test_choice_without_min_probability_always_decides():
    q = QA({"key": "a", "type": "choice", "instructions": "q", "criteria": [{"key": "x"}, {"key": "y"}]})
    raw = {"type": "choice", "choice": "x", "confidence": 0.01, "probabilities": {"x": 0.51, "y": 0.49}}
    assert decide(q, raw).decision == "x"


def test_choice_tie_follows_the_servers_choice():
    raw = {"type": "choice", "choice": "tech", "confidence": 0.0,
           "probabilities": {"billing": 0.4, "tech": 0.4, "sales": 0.2}}
    assert decide(QA({**CHOICE.model_dump(), "min_probability": None}), raw).decision == "tech"


def test_score_bimodal_picks_most_probable_level_never_the_rounded_expected():
    raw = {"type": "score", "score": 1.5, "confidence": 0.1, "legend": LEGEND,
           "probabilities": {"0": 0.46, "1": 0.04, "2": 0.04, "3": 0.46}}
    a = decide(SCORE, raw)
    assert a.level_index in (0, 3)           # never 1 or 2 (the rounding of 1.5)
    assert a.expected_score == 1.5
    assert a.decision in ("Calm", "Furious")


def test_score_tie_prefers_the_lower_level():
    raw = {"type": "score", "score": 1.5, "confidence": 0.1, "legend": LEGEND,
           "probabilities": {"0": 0.46, "1": 0.04, "2": 0.04, "3": 0.46}}
    assert decide(SCORE, raw).level_index == 0


def test_score_real_server_shape():
    raw = {"type": "score", "score": 1.9086953184378705, "confidence": 0.18831437979400756,
           "legend": LEGEND,
           "probabilities": {"0": 0.0249, "1": 0.2620, "2": 0.4925, "3": 0.2206}}
    a = decide(SCORE, raw)
    assert (a.level_index, a.decision) == (2, "Angry")
    assert a.expected_score == raw["score"]


def test_score_below_min_probability_is_null():
    raw = {"type": "score", "score": 1.5, "confidence": 0.1, "legend": LEGEND,
           "probabilities": {"0": 0.3, "1": 0.3, "2": 0.2, "3": 0.2}}
    a = decide(SCORE, raw)
    assert a.decision is None and a.level_index == 0 and a.probability == 0.3


def test_choice_unknown_option_from_server_is_invalid_response():
    raw = {"type": "choice", "choice": "ghost", "confidence": 0.5,
           "probabilities": {"billing": 0.5, "tech": 0.3, "sales": 0.2}}
    with pytest.raises(SystemOneError) as e:
        decide(CHOICE, raw)
    assert e.value.kind == "invalid_response"


def test_score_level_outside_the_question_is_invalid_response():
    raw = {"type": "score", "score": 1.0, "confidence": 0.1, "legend": LEGEND,
           "probabilities": {"0": 0.1, "7": 0.9}}
    with pytest.raises(SystemOneError) as e:
        decide(SCORE, raw)
    assert e.value.kind == "invalid_response"


def test_decide_all_keeps_question_order():
    raws = {
        "s": {"type": "score", "score": 0.1, "confidence": 0.5, "legend": LEGEND,
              "probabilities": {"0": 0.9, "1": 0.05, "2": 0.03, "3": 0.02}},
        "u": {"type": "noul", "noul": 0.5},
    }
    out = decide_all([NOUL, SCORE], raws)
    assert list(out) == ["u", "s"] and out["u"].type == "noul" and out["s"].type == "score"
