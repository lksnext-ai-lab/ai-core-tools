from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from models.middleware import MiddlewareType
from utils.config import Config

# ==================== PER-TYPE CONFIG ====================
#
# Each middleware type has a strict config model. Configs are validated on write
# (CreateUpdateMiddlewareSchema) and re-validated when the agent chain is built, so
# a malformed stored config can never reach a LangChain middleware constructor.

AI_SERVICE_PATTERN = r"^(agent_llm|ai_service:\d+)$"
# Detectors built into langchain's PIIMiddleware (no custom detector needed).
BuiltinPIIType = Literal["email", "credit_card", "ip", "mac_address", "url"]
HITLDecision = Literal["approve", "edit", "reject"]
DEFAULT_APPROVAL_TIMEOUT_SECONDS = 3600
MIN_APPROVAL_TIMEOUT_SECONDS = 60
# Upper bound for any middleware's approval timeout (env, default 7 days).
MAX_APPROVAL_TIMEOUT_SECONDS: int = Config.get_int_env_var("HITL_MAX_APPROVAL_TTL_SECONDS", default=604_800)


class _StrictConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SummarizationConfig(_StrictConfig):
    summarization_model: str = Field("agent_llm", pattern=AI_SERVICE_PATTERN)
    # None = derived from the agent model's context window (see tools/middleware/factory.py).
    trigger_tokens: Optional[int] = Field(None, ge=500, le=1_000_000)
    keep_messages: int = Field(20, ge=1, le=500)
    # None = summarize the whole older history (bounded by the trigger), as Deep Agents does.
    trim_tokens: Optional[int] = Field(None, ge=500, le=1_000_000)


class CallLimitConfig(_StrictConfig):
    max_calls: int = Field(..., ge=1, le=10_000)


class LLMDetectorConfig(_StrictConfig):
    enabled: bool = False
    ai_service: str = Field("agent_llm", pattern=AI_SERVICE_PATTERN)
    extra_entities: List[str] = Field(default_factory=list, max_length=20)

    @field_validator("extra_entities")
    @classmethod
    def _clean_entities(cls, v: List[str]) -> List[str]:
        cleaned = list(dict.fromkeys(e.strip() for e in v if e and e.strip()))
        if any(len(e) > 50 for e in cleaned):
            raise ValueError("each extra entity must be at most 50 characters")
        return cleaned


class PIIConfig(_StrictConfig):
    pii_types: List[BuiltinPIIType] = Field(..., min_length=1)
    strategy: Literal["redact", "mask", "hash", "block"] = "redact"
    apply_to_input: bool = True
    apply_to_output: bool = True
    apply_to_tool_results: bool = True
    llm_detector: Optional[LLMDetectorConfig] = None

    @model_validator(mode="after")
    def _check(self) -> "PIIConfig":
        self.pii_types = list(dict.fromkeys(self.pii_types))
        if not (self.apply_to_input or self.apply_to_output or self.apply_to_tool_results):
            raise ValueError("enable at least one of apply_to_input, apply_to_output or apply_to_tool_results")
        return self


class HITLToolConfig(_StrictConfig):
    allowed_decisions: List[HITLDecision] = Field(..., min_length=1)

    @field_validator("allowed_decisions")
    @classmethod
    def _dedupe(cls, v: List[str]) -> List[str]:
        return list(dict.fromkeys(v))


class HITLConfig(_StrictConfig):
    interrupt_on: Dict[str, HITLToolConfig] = Field(..., min_length=1)
    description_prefix: str = Field("Tool execution requires approval", max_length=500)
    # An unanswered approval is rejected after this long (never approved).
    approval_timeout_seconds: int = Field(DEFAULT_APPROVAL_TIMEOUT_SECONDS, ge=MIN_APPROVAL_TIMEOUT_SECONDS)

    @field_validator("approval_timeout_seconds")
    @classmethod
    def _cap_timeout(cls, v: int) -> int:
        if v > MAX_APPROVAL_TIMEOUT_SECONDS:
            raise ValueError(f"approval_timeout_seconds must be at most {MAX_APPROVAL_TIMEOUT_SECONDS}")
        return v

    @field_validator("interrupt_on")
    @classmethod
    def _tool_names(cls, v: Dict[str, HITLToolConfig]) -> Dict[str, HITLToolConfig]:
        for name in v:
            if not name or len(name) > 128:
                raise ValueError("tool names must be 1-128 characters")
        return v


class GuardrailsInput(_StrictConfig):
    block_malicious_prompts: bool = True
    block_jailbreak: bool = True


class GuardrailsOutput(_StrictConfig):
    prevent_pii_leakage: bool = True
    block_toxic_biased: bool = True
    enforce_business_facts: bool = True


class GuardrailsConfig(_StrictConfig):
    input: GuardrailsInput = Field(default_factory=GuardrailsInput)
    output: GuardrailsOutput = Field(default_factory=GuardrailsOutput)
    custom_prompt: str = Field("", max_length=4000)


CONFIG_MODELS: Dict[MiddlewareType, type[BaseModel]] = {
    MiddlewareType.SUMMARIZATION: SummarizationConfig,
    MiddlewareType.MODEL_CALL_LIMIT: CallLimitConfig,
    MiddlewareType.TOOL_CALL_LIMIT: CallLimitConfig,
    MiddlewareType.PII: PIIConfig,
    MiddlewareType.HUMAN_IN_THE_LOOP: HITLConfig,
    MiddlewareType.GUARDRAILS: GuardrailsConfig,
}


def parse_middleware_config(middleware_type: MiddlewareType, config: Optional[Dict[str, Any]]) -> BaseModel:
    """Validate a raw config dict for the given type. Raises pydantic.ValidationError."""
    return CONFIG_MODELS[middleware_type].model_validate(config or {})


def referenced_ai_service_ids(config: BaseModel) -> List[int]:
    """AIService ids referenced by a validated config (``ai_service:<id>`` values)."""
    refs: List[str] = []
    if isinstance(config, SummarizationConfig):
        refs.append(config.summarization_model)
    elif isinstance(config, PIIConfig) and config.llm_detector and config.llm_detector.enabled:
        refs.append(config.llm_detector.ai_service)
    return [int(r.split(":", 1)[1]) for r in refs if r.startswith("ai_service:")]


# ==================== API SCHEMAS ====================

class MiddlewareListItemSchema(BaseModel):
    """Schema for middleware list items"""
    middleware_id: int
    name: str
    description: Optional[str] = ""
    middleware_type: str
    config: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class MiddlewareDetailSchema(MiddlewareListItemSchema):
    """Schema for detailed middleware information"""


class CreateUpdateMiddlewareSchema(BaseModel):
    """Create/update payload. ``config`` is validated against ``middleware_type``."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field("", max_length=1000)
    middleware_type: MiddlewareType
    config: Optional[Dict[str, Any]] = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v

    @field_validator("middleware_type", mode="before")
    @classmethod
    def _type_from_value(cls, v: Any) -> Any:
        # Accept the public value ("pii"), as the API always has.
        if isinstance(v, str):
            try:
                return MiddlewareType(v)
            except ValueError:
                valid = ", ".join(t.value for t in MiddlewareType)
                raise ValueError(f"must be one of: {valid}") from None
        return v

    @model_validator(mode="after")
    def _validate_config(self) -> "CreateUpdateMiddlewareSchema":
        try:
            parsed = parse_middleware_config(self.middleware_type, self.config)
        except ValidationError as exc:
            first = exc.errors()[0]
            loc = ".".join(str(p) for p in first["loc"]) or "config"
            raise ValueError(f"invalid config for {self.middleware_type.value} ({loc}): {first['msg']}") from None
        self.config = parsed.model_dump()
        return self
