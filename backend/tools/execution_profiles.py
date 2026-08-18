"""
Execution Profiles for Mattin AI.

A provider-agnostic abstraction that controls model behaviour
(primarily reasoning depth) through four profiles: FAST, BALANCED, DEEP, MAX.

The rest of the application never sees provider-specific reasoning
 parameters — the ``ExecutionProfileRegistry`` and ``RuntimeConfigBuilder``
 handle the mapping automatically.
"""

from __future__ import annotations

import re
import enum
import dataclasses
from typing import Dict, List, Optional, Any

from tools.ai.model_catalog import PROVIDER_OPENAI, PROVIDER_ANTHROPIC
from tools.ai.model_catalog import (
    PROVIDER_MISTRAL,
    PROVIDER_GOOGLE,
    PROVIDER_GOOGLE_CLOUD,
    PROVIDER_AZURE,
    PROVIDER_OPENROUTER,
    PROVIDER_CUSTOM,
)

# ====================================================================
# ExecutionProfile enum
# ====================================================================


class ExecutionProfile(enum.IntEnum):
    """Profiles are integer levels that the **entire application** uses.

    Internally each provider maps these levels to its own reasoning
    parameters (reasoning effort, thinking tokens, etc.).  The rest of
    Mattin AI should never see those provider-specific values — it
    only works with ``ExecutionProfile``.
    """

    FAST = 0
    BALANCED = 1
    DEEP = 2
    MAX = 3


# ====================================================================
# ProviderCapability
# ====================================================================


@dataclasses.dataclass(frozen=True)
class ProviderCapability:
    """Describes how a provider handles reasoning / thinking.

    The registry contains one ``ProviderCapability`` instance per
    provider.  Each provider definition states:

    * Whether reasoning is supported at all.
    * The runtime kwarg name that carries the value
      (``reasoning_effort``, ``thinking_budget``, ``reasoning_level``,
      or a free-form key for future mechanisms).
    * How the four execution levels map to provider-specific values.
    * A default execution profile for the provider.

    When a new provider needs reasoning support, developers only
    **add an entry to the registry** — no other code path changes.
    """

    supported: bool = False

    # The exact model kwarg that LangChain / provider SDK expects
    # (e.g. ``reasoning_effort``, ``thinking_budget``, ``reasoning_level``).
    reasoning_kwarg: Optional[str] = None

    # Mapping from ExecutionProfile -> the value the provider SDK understands.
    profile_values: Dict[ExecutionProfile, Any] = dataclasses.field(default_factory=dict)

    # When reasoning is enabled, which profile the provider should start
    # with (usually FAST or BALANCED).
    default_profile: ExecutionProfile = ExecutionProfile.BALANCED

    # When True and a reasoning profile is active, the runtime builder
    # will add the kwarg to the model kwargs sent to LangChain.
    @property
    def has_reasoning_config(self) -> bool:
        return self.supported and self.reasoning_kwarg is not None


# ====================================================================
# ModelCapability
# ====================================================================


@dataclasses.dataclass(frozen=True)
class ModelCapability:
    """Per-model (or per-prefix) overrides for a provider's capabilities.

    A ``ModelCapability`` inherits everything from its parent
    ``ProviderCapability`` unless explicitly overridden.  Prefix
    matching lets administrators define behaviour for an entire
    model family with a single entry (e.g. ``gpt-4o`` covers
    ``gpt-4o-2024-05-13``, ``gpt-4o-mini``, etc.).

    Some models use a *different* reasoning mechanism than their
    provider's default (e.g. OpenAI o1 models use ``max_completion_tokens``
    instead of ``reasoning_effort``).  ``model_reasoning_kwarg`` and
    ``model_reasoning_config`` provide an escape hatch for this case
    without scattering provider-specific logic throughout the inference
    layer.
    """

    # Regex prefix to match against the model id (e.g. ``o1``,
    # ``claude-3-5``, ``gemini-2``).  If ``regex_pattern`` is empty
    # the capability applies to a single specific model id
    # (``model_id`` field).
    regex_pattern: str = ""

    # The provider this rule applies to (e.g. "OpenAI", "Anthropic").
    # When ``regex_pattern`` is empty this field is ignored.
    provider: str = ""

    # When a regex_prefix is set this is ignored.
    model_id: str = ""

    # Capability overrides — only non-None values are applied.
    supports_reasoning: Optional[bool] = None
    # Override the provider's profiling values (e.g. make a model
    # support DEEP but not MAX).  If ``None`` the provider defaults
    # are inherited.
    profile_values: Optional[Dict[ExecutionProfile, Any]] = None

    # Disable temperature for this model (some reasoning models
    # reject temperature when thinking is enabled).
    disable_temperature: bool = False

    # Other capability flags (mirrors ProviderCapabilities from
    # schemas.provider_models_schemas for discovery consistency).
    supports_vision: Optional[bool] = None
    supports_json_mode: Optional[bool] = None

    # When set, the runtime will force temperature to this exact value
    # regardless of what the user or agent specifies.  Use this when a
    # model accepts the temperature parameter but only the default (1.0)
    # value is valid — passing anything else produces an API error.
    #
    # ``None`` means "do not force temperature".
    force_temperature: Optional[float] = None

    # Model-specific reasoning kwarg name.  When present this value
    # overrides the provider's ``reasoning_kwarg`` — the model will
    # receive this kwarg *instead* of the provider default.
    #
    # Use this when a model uses a different reasoning mechanism than
    # its provider (e.g. o1 uses ``max_completion_tokens`` instead of
    # ``reasoning_effort``).
    model_reasoning_kwarg: Optional[str] = None

    # Model-specific reasoning values mapping profiles to values for
    # the *model-specific* kwarg.  Only used when ``model_reasoning_kwarg``
    # is set.
    model_reasoning_config: Dict[ExecutionProfile, Any] = dataclasses.field(default_factory=dict)

    @classmethod
    def for_model(cls, provider: str, model_id: str) -> "ModelCapability":
        """Find the most specific ModelCapability for *model_id*.

        Walks the **global model overrides** registry (``_MODEL_OVERRIDES``)
        and returns the first matching rule — exact match takes
        precedence over the longest prefix match.
        """
        lid = model_id.lower() if model_id else ""

        # 1. Exact match
        for rule in _MODEL_OVERRIDES:
            if rule.provider == provider and rule.model_id == model_id:
                return rule

        # 2. Longest prefix match
        best_match: Optional["ModelCapability"] = None
        best_len = 0

        for rule in _MODEL_OVERRIDES:
            if rule.provider != provider:
                continue
            if not rule.regex_pattern:
                continue
            if re.search(rule.regex_pattern, lid):
                pat_len = len(rule.regex_pattern)
                if pat_len > best_len:
                    best_len = pat_len
                    best_match = rule

        if best_match is not None:
            return best_match

        # 3. Fallback — sentinel that means "use provider defaults".
        return ModelCapability()

    def apply_provider_defaults(self, provider_cap: ProviderCapability) -> ProviderCapability:
        """Return a new ``ProviderCapability`` with overrides applied."""
        pc = dataclasses.replace(provider_cap)

        if self.supports_reasoning is not None:
            pc = dataclasses.replace(pc, supported=self.supports_reasoning)

        if self.profile_values is not None:
            pc = dataclasses.replace(pc, profile_values=dict(self.profile_values))

        return pc

    @property
    def should_disable_temperature(self) -> bool:
        if not self.supports_reasoning:
            return False
        return self.disable_temperature

    @property
    def effective_force_temperature(self) -> Optional[float]:
        """Return the temperature value to force, or None if no forcing needed."""
        if self.force_temperature is not None:
            return self.force_temperature
        return None


# ====================================================================
# RuntimeConfig
# ====================================================================


@dataclasses.dataclass(frozen=True)
class RuntimeConfig:
    """Minimal, provider-agnostic config for the inference layer.

    The agent LLM builder passes **only** this object to the runtime
    kwarg generator — the caller never queries provider definitions
    directly.
    """

    # Identity
    provider: str
    model_id: str

    # Execution profile chosen by the user / inherited from the AIService.
    execution_profile: ExecutionProfile

    # Reasoning runtime parameter: the kwarg name and value that will
    # be sent to the LLM client (e.g. ("reasoning_effort", "high")).
    # ``None`` when reasoning is not supported for this model/profile.
    reasoning_kwarg: Optional[str] = None
    reasoning_value: Optional[Any] = None

    # Model-specific reasoning kwarg/overriding the provider default.
    # These fields are set when a model uses a different reasoning
    # mechanism than its provider (e.g. o1 models use
    # ``max_completion_tokens`` instead of ``reasoning_effort``).
    model_reasoning_kwarg: Optional[str] = None
    model_reasoning_value: Optional[Any] = None

    # Capability flags — precomputed from provider + model override so
    # the inference layer only looks at runtime config.
    supports_reasoning: bool = False
    supports_vision: bool = False
    supports_json_mode: bool = False

    # When the provider disables temperature alongside reasoning
    # (some models reject ``temperature`` when thinking is on).
    disable_temperature: bool = False

    # When the model requires temperature to be a specific value (e.g. 1.0)
    # regardless of what the user or agent specifies.
    force_temperature: Optional[float] = None

    # Execution-profile metadata (default profile, available levels).
    # Exposed so callers can validate overrides.
    default_profile: ExecutionProfile = ExecutionProfile.BALANCED

    # Execution profile limits — how much the model can do at each level.
    # Provider-level defaults, possibly overridden at model level.
    profile_values: Dict[ExecutionProfile, Any] = dataclasses.field(default_factory=dict)


# ====================================================================
# RuntimeConfigBuilder
# ====================================================================


class RuntimeConfigBuilder:
    """Builds a :class:`RuntimeConfig` from provider, model, and profile.

    Resolution order:

    1. Look up the provider's ``ProviderCapability`` in the global registry.
    2. Apply ``ModelCapability`` overrides from the global overrides.
    3. Populate the ``RuntimeConfig`` with the resolved kwarg mapping.

    **Model-specific reasoning** takes priority: when a ``ModelCapability``
    sets ``model_reasoning_kwarg``, the runtime uses that kwarg *instead* of
    the provider's ``reasoning_kwarg`` and looks up values from
    ``model_reasoning_config`` rather than ``profile_values``.
    """

    @staticmethod
    def build(
        provider: str,
        model_id: str,
        execution_profile: ExecutionProfile,
    ) -> RuntimeConfig:
        # 1. Provider defaults
        provider_cap = _REGISTRY.get(provider) or ProviderCapability()

        # 2. Model overrides
        model_cap = ModelCapability.for_model(provider, model_id)
        resolved = model_cap.apply_provider_defaults(provider_cap)

        # 3. Resolve specific value for the chosen profile

        # --- Model-specific reasoning (overrides provider default) ---
        reasoning_kwarg: Optional[str] = None
        reasoning_value: Optional[Any] = None
        model_reasoning_kwarg: Optional[str] = None
        model_reasoning_value: Optional[Any] = None

        if model_cap.model_reasoning_kwarg:
            # Model overrides the provider's reasoning mechanism.
            model_reasoning_kwarg = model_cap.model_reasoning_kwarg
            model_reasoning_value = model_cap.model_reasoning_config.get(execution_profile)
        elif resolved.has_reasoning_config:
            # Fall back to provider-level reasoning.
            reasoning_kwarg = resolved.reasoning_kwarg
            profile_val = resolved.profile_values.get(execution_profile)
            if profile_val is not None:
                reasoning_value = profile_val

        # 4. Compute derived capability flags
        caps = model_cap.supports_reasoning or resolved.supported
        disallow_temp = model_cap.should_disable_temperature and caps
        force_temp = model_cap.effective_force_temperature

        return RuntimeConfig(
            provider=provider,
            model_id=model_id,
            execution_profile=execution_profile,
            reasoning_kwarg=reasoning_kwarg,
            reasoning_value=reasoning_value,
            model_reasoning_kwarg=model_reasoning_kwarg,
            model_reasoning_value=model_reasoning_value,
            supports_reasoning=caps,
            supports_vision=model_cap.supports_vision or False,
            supports_json_mode=model_cap.supports_json_mode or False,
            disable_temperature=disallow_temp,
            force_temperature=force_temp,
            default_profile=resolved.default_profile,
            profile_values=dict(resolved.profile_values),
        )


# ====================================================================
# Runtime kwarg builder
# ====================================================================


def build_runtime_kwargs(
    runtime_config: RuntimeConfig,
    temperature: Optional[float] = None,
    additional_kwargs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Turn a :class:`RuntimeConfig` into model kwargs for the LLM client.

    This is the **single generic function** the inference layer calls to
    produce the kwargs dictionary for ``ChatOpenAI(...)``,
    ``ChatAnthropic(...)``, etc.

    Usage::

        rc = RuntimeConfigBuilder.build(
            provider="OpenAI",
            model_id="gpt-4o",
            execution_profile=ExecutionProfile.DEEP,
        )
        kwargs = build_runtime_kwargs(rc, temperature=0.7)
        # kwargs = {"reasoning_effort": "high", "temperature": 0.7}
        llm = ChatOpenAI(**kwargs, api_key=...)

    Adding a new provider with a new reasoning mechanism only requires
    registering it in ``_REGISTRY`` — the kwarg builder stays unchanged.
    """
    kwargs: Dict[str, Any] = {}

    # Temperature — three possible modes driven by RuntimeConfig:
    #   1. force_temperature: send the model's required value (e.g. 1.0)
    #   2. disable_temperature: omit temperature entirely
    #   3. default: send the caller-supplied temperature (may be None)
    if runtime_config.force_temperature is not None:
        kwargs["temperature"] = runtime_config.force_temperature
    elif temperature is not None and not runtime_config.disable_temperature:
        kwargs["temperature"] = temperature

    # Provider-level reasoning parameter
    if runtime_config.reasoning_kwarg is not None and runtime_config.reasoning_value is not None:
        kwargs[runtime_config.reasoning_kwarg] = runtime_config.reasoning_value

    # Model-specific reasoning parameter (overrides provider default)
    # This handles models like o1 that use a different reasoning mechanism
    if runtime_config.model_reasoning_kwarg is not None and runtime_config.model_reasoning_value is not None:
        kwargs[runtime_config.model_reasoning_kwarg] = runtime_config.model_reasoning_value

    # Additional override kwargs (retrievers, custom metadata…)
    if additional_kwargs:
        kwargs.update(additional_kwargs)

    return kwargs


# ====================================================================
# Global registry — provider capabilities
# ====================================================================

_REGISTRY: Dict[str, ProviderCapability] = {}


def register_provider_capability(capability: ProviderCapability, provider: str) -> None:
    """Register (or update) a provider's reasoning configuration.

    Call this at module-initialisation time to define how each
    provider maps execution profiles to its own parameters.
    """
    _REGISTRY[provider] = capability


def get_provider_capability(provider: str) -> ProviderCapability:
    """Return the capability for *provider*, or a disabled sentinel."""
    return _REGISTRY.get(provider) or ProviderCapability()


# ====================================================================
# Global model overrides registry
# ====================================================================

_MODEL_OVERRIDES: List[ModelCapability] = []


def register_model_override(override: ModelCapability) -> None:
    """Append a per-model override to the global registry."""
    _MODEL_OVERRIDES.append(override)


def clear_model_overrides() -> None:
    """Clear all model overrides.  Useful for tests."""
    _MODEL_OVERRIDES.clear()


# ====================================================================
# Built-in provider capabilities
# ====================================================================


def _register_builtin_capabilities() -> None:
    """Wire up reasoning capabilities for every supported provider."""

    # ------ OpenAI — reasoning_effort parameter (non-o-series, gpt-4o+)
    # "low" | "medium" | "high"  or None when disabled.
    # NOTE: o1 models deliberately do NOT use reasoning_effort — they use
    # max_completion_tokens and are handled via model overrides.
    register_provider_capability(
        ProviderCapability(
            supported=True,
            reasoning_kwarg="reasoning_effort",
            profile_values={
                ExecutionProfile.FAST: "low",
                ExecutionProfile.BALANCED: "medium",
                ExecutionProfile.DEEP: "high",
                ExecutionProfile.MAX: "high",
            },
            default_profile=ExecutionProfile.BALANCED,
        ),
        PROVIDER_OPENAI,
    )

    # ------ Anthropic — thinking_budget parameter (optional)
    # integer token budget (0-125000)
    register_provider_capability(
        ProviderCapability(
            supported=True,
            reasoning_kwarg="thinking_budget",
            profile_values={
                ExecutionProfile.FAST: 1024,
                ExecutionProfile.BALANCED: 5000,
                ExecutionProfile.DEEP: 50000,
                ExecutionProfile.MAX: 125000,
            },
            default_profile=ExecutionProfile.BALANCED,
        ),
        PROVIDER_ANTHROPIC,
    )

    # ------ MistralAI — no native reasoning parameter yet
    register_provider_capability(
        ProviderCapability(
            supported=False,
            default_profile=ExecutionProfile.BALANCED,
        ),
        PROVIDER_MISTRAL,
    )

    # ------ Google Gemini — thinking_budget token budget
    # Gemini API rejects thinking_budget outside [-1, 65535].
    # Cap DEEP/MAX at 65535 to keep profile range safe across all
    # Gemini models (flash-lite, pro, etc.).
    register_provider_capability(
        ProviderCapability(
            supported=True,
            reasoning_kwarg="thinking_budget",
            profile_values={
                ExecutionProfile.FAST: 1024,
                ExecutionProfile.BALANCED: 5000,
                ExecutionProfile.DEEP: 65535,
                ExecutionProfile.MAX: 65535,
            },
            default_profile=ExecutionProfile.BALANCED,
        ),
        PROVIDER_GOOGLE,
    )

    # ------ Google Cloud (Vertex AI) — same mechanism as Gemini
    # Vertex AI also uses Gemini API, capped at 65535.
    register_provider_capability(
        ProviderCapability(
            supported=True,
            reasoning_kwarg="thinking_budget",
            profile_values={
                ExecutionProfile.FAST: 1024,
                ExecutionProfile.BALANCED: 5000,
                ExecutionProfile.DEEP: 65535,
                ExecutionProfile.MAX: 65535,
            },
            default_profile=ExecutionProfile.BALANCED,
        ),
        PROVIDER_GOOGLE_CLOUD,
    )

    # ------ Azure OpenAI — supports reasoning_effort via Azure's API
    register_provider_capability(
        ProviderCapability(
            supported=True,
            reasoning_kwarg="reasoning_effort",
            profile_values={
                ExecutionProfile.FAST: "low",
                ExecutionProfile.BALANCED: "medium",
                ExecutionProfile.DEEP: "high",
                ExecutionProfile.MAX: "high",
            },
            default_profile=ExecutionProfile.BALANCED,
        ),
        PROVIDER_AZURE,
    )

    # ------ OpenRouter — passes reasoning parameter through to underlying
    # model (provider-agnostic — OpenRouter normalises reasoning_effort).
    register_provider_capability(
        ProviderCapability(
            supported=True,
            reasoning_kwarg="reasoning_effort",
            profile_values={
                ExecutionProfile.FAST: "low",
                ExecutionProfile.BALANCED: "medium",
                ExecutionProfile.DEEP: "high",
                ExecutionProfile.MAX: "high",
            },
            default_profile=ExecutionProfile.BALANCED,
        ),
        PROVIDER_OPENROUTER,
    )

    # ------ Custom / Ollama — may support reasoning parameters but
    # default to disabled until the user configures it.
    register_provider_capability(
        ProviderCapability(
            supported=False,
            default_profile=ExecutionProfile.BALANCED,
        ),
        PROVIDER_CUSTOM,
    )


# ====================================================================
# Built-in model overrides
# ====================================================================


def _register_builtin_model_overrides() -> None:
    """Register per-model capability overrides."""

    # OpenAI o1 models: do NOT use reasoning_effort — they use
    # max_completion_tokens for controlling reasoning depth.
    # Temperature is disabled.
    register_model_override(
        ModelCapability(
            provider=PROVIDER_OPENAI,
            regex_pattern=r"^o1",
            supports_reasoning=True,
            disable_temperature=True,
            supports_vision=True,
            model_reasoning_kwarg="max_completion_tokens",
            model_reasoning_config={
                ExecutionProfile.FAST: 128,
                ExecutionProfile.BALANCED: 512,
                ExecutionProfile.DEEP: 1024,
                ExecutionProfile.MAX: 2048,
            },
        )
    )

    # OpenAI o3+ models: use reasoning_effort like the provider default,
    # but are reasoning-only (no temperature).
    register_model_override(
        ModelCapability(
            provider=PROVIDER_OPENAI,
            regex_pattern=r"^o3",
            supports_reasoning=True,
            disable_temperature=True,
            supports_vision=True,
        )
    )

    # Claude models: reasoning is always enabled; vision support.
    register_model_override(
        ModelCapability(
            provider=PROVIDER_ANTHROPIC,
            regex_pattern=r"^claude-(?:opus|sonnet|haiku)-\d",
            supports_vision=True,
        )
    )

    # Gemini 2.x+ models: multimodal, reasoning supported.
    # Excludes flash-flashlite and all flash variants that don't support
    # Gemini thinking (the API rejects thinking_config for those models).
    register_model_override(
        ModelCapability(
            provider=PROVIDER_GOOGLE,
            regex_pattern=r"^gemini-(?!\d.*flash)",
            supports_reasoning=True,
            supports_vision=True,
        )
    )

    register_model_override(
        ModelCapability(
            provider=PROVIDER_GOOGLE,
            regex_pattern=r"^gemini-1\.5",
            supports_reasoning=True,
            supports_vision=True,
        )
    )

    # OpenAI gpt-5.{1,2,3}-chat-latest — only accept reasoning_effort=medium
    # (all other levels throw 400).  They also reject temperature != 1.0.
    # Force both so these models work at every execution profile.
    # Must be placed BEFORE the gpt-5.4+ rule so it takes precedence
    # (longest/winner regex matching).
    register_model_override(
        ModelCapability(
            provider=PROVIDER_OPENAI,
            regex_pattern=r"^gpt-5\.(?:1|2|3)-chat-latest$",
            profile_values={
                ExecutionProfile.FAST: "medium",
                ExecutionProfile.BALANCED: "medium",
                ExecutionProfile.DEEP: "medium",
                ExecutionProfile.MAX: "medium",
            },
            force_temperature=1.0,
        )
    )

    register_model_override(
        ModelCapability(
            provider=PROVIDER_OPENAI,
            regex_pattern=r"^gpt-5-chat-latest$",
            supports_reasoning=False,
        )
    )

    # OpenAI gpt-5.{4,5,6,...}-chat-latest and similar post-5.3 models
    # reject reasoning_effort when function tools are used (they expect
    # /v1/responses instead of /v1/chat/completions).  The safest approach:
    # disable reasoning entirely for these models in the chat completions
    # path.  The regex uses `[0-9]+` to match any minor version number
    # (gpt-5.X), including multi-digit ones like gpt-5.10, gpt-5.99, etc.
    # [4-9] matches single digits 4-9; [1-9][0-9]+ matches only 2+ digit
    # versions (10, 11, …) so gpt-5.1/5.2/5.3 never match this branch.
    register_model_override(
        ModelCapability(
            provider=PROVIDER_OPENAI,
            regex_pattern=r"^gpt-5\.[4-9]",
            supports_reasoning=False,
        )
    )

    register_model_override(
        ModelCapability(
            provider=PROVIDER_OPENAI,
            regex_pattern=r"(^|-)search(-|$)",
            supports_reasoning=False,
        )
    )

    # gpt-4.1-series (`gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`) — these
    # models reject temperature != 1.0 and only accept reasoning_effort=medium
    # regardless of execution profile.  This covers every gpt-4.1 variant
    # including future `-chat-latest` suffixes.
    register_model_override(
        ModelCapability(
            provider=PROVIDER_OPENAI,
            regex_pattern=r"^gpt-4\.1",
            supports_reasoning=True,
            profile_values={
                ExecutionProfile.FAST: "medium",
                ExecutionProfile.BALANCED: "medium",
                ExecutionProfile.DEEP: "medium",
                ExecutionProfile.MAX: "medium",
            },
            force_temperature=1.0,
        )
    )

    register_model_override(
        ModelCapability(
            provider=PROVIDER_GOOGLE,
            regex_pattern=r"^gemini-2\.5",
            profile_values={
                ExecutionProfile.FAST: 1024,
                ExecutionProfile.BALANCED: 5000,
                ExecutionProfile.DEEP: 24576,
                ExecutionProfile.MAX: 24576,
            }
        )
    )


# ====================================================================
# Module initialisation
# ====================================================================


_register_builtin_capabilities()
_register_builtin_model_overrides()
