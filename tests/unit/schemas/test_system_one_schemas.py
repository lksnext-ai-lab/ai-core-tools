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
    {**CHOICE, "criteria": [{"key": f"o{i}"} for i in range(27)]},
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
    with pytest.raises(ValidationError):
        ql.validate_python([{**NOUL, "key": f"q{i}"} for i in range(65)])
    with pytest.raises(ValidationError) as e:
        ql.validate_python([NOUL, NOUL])
    assert "is_urgent" in str(e.value)


# ------------------------------------------------ text fields are bounded (agent JSON is stored and sent)

@pytest.mark.parametrize("question", [
    {"key": "q", "type": "noul", "instructions": "x" * 4001},
    {"key": "q", "type": "noul", "instructions": "ok", "criteria": {"true": "x" * 501, "false": "no"}},
    {"key": "q", "type": "choice", "instructions": "ok", "criteria": [{"key": "a" * 101}, {"key": "b"}]},
    {"key": "q", "type": "choice", "instructions": "ok", "criteria": [{"key": "a", "description": "x" * 501}, {"key": "b"}]},
    {"key": "q", "type": "score", "instructions": "ok", "criteria": ["x" * 501, "high"]},
])
def test_overlong_question_text_is_rejected(question):
    with pytest.raises(ValidationError):
        TypeAdapter(Question).validate_python(question)


def test_text_at_the_limit_is_accepted():
    TypeAdapter(Question).validate_python({"key": "q", "type": "score", "instructions": "x" * 4000,
                                           "criteria": ["x" * 500, "y"]})
