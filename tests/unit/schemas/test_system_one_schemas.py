import pytest
from pydantic import TypeAdapter, ValidationError

from schemas.system_one_schemas import Question, QuestionList

q = TypeAdapter(Question)
ql = TypeAdapter(QuestionList)

NOUL = {"key": "is_urgent", "type": "noul", "instructions": "Is this message urgent?"}
CHOICE = {"key": "area", "type": "choice", "instructions": "Which department?",
          "criteria": [{"key": "billing", "description": "Invoices"}, {"key": "support"}]}
SCORE = {"key": "anger", "type": "score", "instructions": "How angry?",
         "criteria": ["Calm", "Annoyed", "Angry"]}


def test_valid_questions_parse_with_defaults():
    assert q.validate_python(NOUL).threshold == 0.5
    assert q.validate_python(CHOICE).min_probability is None
    assert q.validate_python(SCORE).criteria == ["Calm", "Annoyed", "Angry"]


@pytest.mark.parametrize("bad", [
    {**NOUL, "key": "Has Space"}, {**NOUL, "key": ""}, {**NOUL, "key": "x" * 41},
    {**NOUL, "instructions": "  "}, {**NOUL, "threshold": 1.5}, {**NOUL, "threshold": -0.1},
    {**CHOICE, "criteria": [{"key": "only"}]},
    {**CHOICE, "criteria": [{"key": "Billing"}, {"key": "billing"}]},      # case-insensitive dup
    {**CHOICE, "criteria": [{"key": " "}, {"key": "b"}]},
    {**SCORE, "criteria": ["only"]}, {**SCORE, "criteria": ["a", ""]},
    {**SCORE, "min_probability": 2},
    {**NOUL, "type": "other"},
])
def test_invalid_questions_rejected(bad):
    with pytest.raises(ValidationError):
        q.validate_python(bad)


def test_accents_and_spaces_in_options_are_accepted():
    ok = {**CHOICE, "criteria": [{"key": "facturación"}, {"key": "soporte técnico"}]}
    assert len(q.validate_python(ok).criteria) == 2


def test_question_list_bounds_and_unique_keys():
    assert len(ql.validate_python([NOUL])) == 1
    with pytest.raises(ValidationError):
        ql.validate_python([])
    with pytest.raises(ValidationError) as e:
        ql.validate_python([NOUL, NOUL])
    assert "is_urgent" in str(e.value)


# ---------------------------------- the size of a question is judged against the prompt budget, not per field

def test_long_question_text_is_valid_shape_the_budget_rule_lives_with_the_agent():
    assert q.validate_python({"key": "q", "type": "score", "instructions": "x" * 5000, "criteria": ["y" * 900, "z"]})


def test_the_upper_limits_belong_to_the_server_not_to_the_schema():
    # Each server reports its own (/v1/limits): the form checks against them, the schema only checks shape.
    assert len(ql.validate_python([{**NOUL, "key": f"q{i}"} for i in range(200)])) == 200
    assert len(q.validate_python({**CHOICE, "criteria": [{"key": f"o{i}"} for i in range(40)]}).criteria) == 40
    assert len(q.validate_python({**SCORE, "criteria": [f"l{i}" for i in range(40)]}).criteria) == 40


def test_yes_and_no_meanings_are_independent_and_optional_like_the_servers():
    # The server defaults them to "Yes" / "No" separately: giving only one is valid.
    only_yes = q.validate_python({**NOUL, "criteria": {"true": "Needs an answer today"}})
    assert only_yes.criteria.true == "Needs an answer today" and only_yes.criteria.false is None
    only_no = q.validate_python({**NOUL, "criteria": {"false": "Can wait"}})
    assert only_no.criteria.true is None and only_no.criteria.false == "Can wait"


def test_a_score_question_chooses_which_end_of_the_scale_is_green():
    assert q.validate_python(SCORE).color_start == "green"                     # default: the first level is the best
    assert q.validate_python({**SCORE, "color_start": "red"}).color_start == "red"
    with pytest.raises(ValidationError):
        q.validate_python({**SCORE, "color_start": "blue"})
