"""Question definitions (input) and evaluation results (output) of System One agents."""
from typing import Annotated, Dict, List, Literal, Optional, Union

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, ValidationError, field_validator

QuestionKey = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]{1,40}$")]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]       # instructions
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]  # criteria
OptionKey = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Prob = Annotated[float, Field(ge=0.0, le=1.0)]
MAX_QUESTIONS, MIN_OPTIONS, MAX_OPTIONS = 64, 2, 26  # limits of the System One server


class _QuestionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: QuestionKey
    instructions: Text


class NoulCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid")
    true: ShortText
    false: ShortText


class NoulQuestion(_QuestionBase):
    type: Literal["noul"]
    criteria: Optional[NoulCriteria] = None
    threshold: Prob = 0.5


class ChoiceOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: OptionKey
    description: Optional[Annotated[str, StringConstraints(max_length=500)]] = None


class ChoiceQuestion(_QuestionBase):
    type: Literal["choice"]
    criteria: Annotated[List[ChoiceOption], Field(min_length=MIN_OPTIONS, max_length=MAX_OPTIONS)]
    min_probability: Optional[Prob] = None

    @field_validator("criteria")
    @classmethod
    def _unique_options(cls, v):
        seen = set()
        for option in v:
            folded = option.key.casefold()
            if folded in seen:
                raise ValueError(f"duplicate option '{option.key}' (options are compared ignoring case)")
            seen.add(folded)
        return v


class ScoreQuestion(_QuestionBase):
    type: Literal["score"]
    criteria: Annotated[List[ShortText], Field(min_length=MIN_OPTIONS, max_length=MAX_OPTIONS)]
    min_probability: Optional[Prob] = None


Question = Annotated[Union[NoulQuestion, ChoiceQuestion, ScoreQuestion], Field(discriminator="type")]


def _unique_keys(questions):
    seen = set()
    for question in questions:
        if question.key in seen:
            raise ValueError(f"duplicate question key '{question.key}'")
        seen.add(question.key)
    return questions


QuestionList = Annotated[
    List[Question], Field(min_length=1, max_length=MAX_QUESTIONS), AfterValidator(_unique_keys)
]


def questions_error_message(exc: ValidationError) -> str:
    """One readable line for the first problem of a question list, e.g. ``questions.0.key: String should match ...``."""
    first = exc.errors()[0]
    where = ".".join(str(part) for part in first["loc"])
    return f"questions{'.' + where if where else ''}: {first['msg']}"


# ----------------------------- results -----------------------------

class NoulAnswer(BaseModel):
    type: Literal["noul"] = "noul"
    decision: bool
    probability: float
    threshold: float


class ChoiceAnswer(BaseModel):
    type: Literal["choice"] = "choice"
    decision: Optional[str]            # None = below min_probability
    choice: str                        # what the server picked
    probability: float                 # of the picked option
    probabilities: Dict[str, float]
    confidence: float
    min_probability: Optional[float] = None


class ScoreAnswer(BaseModel):
    type: Literal["score"] = "score"
    decision: Optional[str]            # text of the most probable level; None = below min_probability
    level_index: int                   # most probable level (NOT the rounded expected score)
    probability: float                 # of that level
    expected_score: float              # the server's expected index (a float)
    legend: Dict[str, str]
    probabilities: Dict[str, float]
    confidence: float
    min_probability: Optional[float] = None


Answer = Annotated[Union[NoulAnswer, ChoiceAnswer, ScoreAnswer], Field(discriminator="type")]


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class SystemOneResult(BaseModel):
    answers: Dict[str, Answer]
    state_reduction: Literal["none", "summarized", "truncated"] = "none"
    original_chars: int
    state_chars: int
    model: str
    usage: Optional[Usage] = None


class SystemOneToolInput(BaseModel):
    text: str = Field(description="Text to evaluate: a message, a document excerpt or an answer to judge.")
