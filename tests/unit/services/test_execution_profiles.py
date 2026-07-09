"""Comprehensive unit tests for the execution profiles system.

Covers ExecutionProfile enum, ProviderCapability / ModelCapability dataclasses,
RuntimeConfigBuilder, build_runtime_kwargs, and the global registries.
"""

from __future__ import annotations

import dataclasses

import pytest
from tools.execution_profiles import (
    ExecutionProfile,
    ProviderCapability,
    ModelCapability,
    RuntimeConfig,
    RuntimeConfigBuilder,
    build_runtime_kwargs,
    get_provider_capability,
    register_provider_capability,
    register_model_override,
    clear_model_overrides,
    _REGISTRY,
    _MODEL_OVERRIDES,
)
from tools.ai.model_catalog import (
    PROVIDER_OPENAI,
    PROVIDER_ANTHROPIC,
    PROVIDER_MISTRAL,
    PROVIDER_GOOGLE,
    PROVIDER_GOOGLE_CLOUD,
    PROVIDER_AZURE,
    PROVIDER_OPENROUTER,
    PROVIDER_CUSTOM,
)


# ========================================================================
# Fixtures
# ========================================================================


@pytest.fixture(autouse=True)
def _clear_overrides():
    """Clear model overrides before every test to avoid cross-test pollution."""
    clear_model_overrides()
    yield


# === Helper: register builtins for tests that need them ===


def _restore_builtins():
    """Re-register built-in model overrides (o1, claude, gemini) on top of
    cleared state.  Tests that call clear_model_overrides() mid-body use
    this to restore the baseline before continuing."""
    from tools import execution_profiles as _ep
    _MODEL_OVERRIDES.clear()  # Prevents duplicates on repeated calls
    _ep._register_builtin_model_overrides()


@pytest.fixture
def built_in_providers():
    """Return the set of providers registered by _register_builtin_capabilities()."""
    builtin = {
        PROVIDER_OPENAI,
        PROVIDER_ANTHROPIC,
        PROVIDER_MISTRAL,
        PROVIDER_GOOGLE,
        PROVIDER_GOOGLE_CLOUD,
        PROVIDER_AZURE,
        PROVIDER_OPENROUTER,
        PROVIDER_CUSTOM,
    }
    return builtin


@pytest.fixture
def register_test_provider():
    """Register a temporary provider and unregister it after the test."""
    providers_added = []

    def _register(cap, provider_name):
        _REGISTRY[provider_name] = cap
        providers_added.append(provider_name)
        return cap

    yield _register

    for name in providers_added:
        _REGISTRY.pop(name, None)


# ========================================================================
# 1-4. ExecutionProfile enum tests
# ========================================================================


@pytest.mark.parametrize("name,value", [
    ("FAST", 0),
    ("BALANCED", 1),
    ("DEEP", 2),
    ("MAX", 3),
])
def test_execution_profile_values(name, value):
    """Verify the four profiles exist with correct integer values."""
    profile = ExecutionProfile[name]
    assert profile.value == value


def test_execution_profile_intenum_ordering():
    """Verify IntEnum ordering: FAST < BALANCED < DEEP < MAX."""
    assert ExecutionProfile.FAST < ExecutionProfile.BALANCED
    assert ExecutionProfile.BALANCED < ExecutionProfile.DEEP
    assert ExecutionProfile.DEEP < ExecutionProfile.MAX
    assert ExecutionProfile.FAST < ExecutionProfile.MAX


@pytest.mark.parametrize("name", ["FAST", "BALANCED", "DEEP", "MAX"])
def test_execution_profile_by_name_access(name):
    """Verify by-name access works for all profiles."""
    assert hasattr(ExecutionProfile, name)
    profile = getattr(ExecutionProfile, name)
    assert isinstance(profile, ExecutionProfile)


def test_execution_profile_reverse_lookup():
    """Verify reverse lookup: ExecutionProfile(0) == ExecutionProfile.FAST."""
    assert ExecutionProfile(0) == ExecutionProfile.FAST
    assert ExecutionProfile(1) == ExecutionProfile.BALANCED
    assert ExecutionProfile(2) == ExecutionProfile.DEEP
    assert ExecutionProfile(3) == ExecutionProfile.MAX


# ========================================================================
# 5-15. ProviderCapability tests
# ========================================================================


@pytest.mark.parametrize("provider,expected_kwarg", [
    (PROVIDER_OPENAI, "reasoning_effort"),
    (PROVIDER_AZURE, "reasoning_effort"),
    (PROVIDER_OPENROUTER, "reasoning_effort"),
])
def test_provider_reasoning_with_reasoning_effort(provider, expected_kwarg):
    """Verify providers that use reasoning_effort kwarg."""
    cap = get_provider_capability(provider)
    assert cap.supported is True
    assert cap.reasoning_kwarg == expected_kwarg
    assert cap.has_reasoning_config is True


@pytest.mark.parametrize("provider", [
    PROVIDER_OPENAI,
    PROVIDER_AZURE,
    PROVIDER_OPENROUTER,
])
def test_provider_profile_values_strings(provider):
    """Verify string-based profile values for reasoning_effort providers."""
    cap = get_provider_capability(provider)
    assert cap.profile_values[ExecutionProfile.FAST] == "low"
    assert cap.profile_values[ExecutionProfile.BALANCED] == "medium"
    assert cap.profile_values[ExecutionProfile.DEEP] == "high"
    assert cap.profile_values[ExecutionProfile.MAX] == "high"


@pytest.mark.parametrize("provider", [
    PROVIDER_OPENAI,
    PROVIDER_AZURE,
    PROVIDER_OPENROUTER,
])
def test_provider_default_profile_balanced(provider):
    """Verify default profile is BALANCED for reasoning_effort providers."""
    cap = get_provider_capability(provider)
    assert cap.default_profile == ExecutionProfile.BALANCED


def test_anthropic_reasoning_with_thinking_budget():
    """Verify Anthropic has reasoning supported with kwarg thinking_budget."""
    cap = get_provider_capability(PROVIDER_ANTHROPIC)
    assert cap.supported is True
    assert cap.reasoning_kwarg == "thinking_budget"
    assert cap.has_reasoning_config is True


def test_anthropic_profile_values():
    """Verify Anthropic profile_values: integers (1024, 5000, 50000, 125000)."""
    cap = get_provider_capability(PROVIDER_ANTHROPIC)
    assert cap.profile_values[ExecutionProfile.FAST] == 1024
    assert cap.profile_values[ExecutionProfile.BALANCED] == 5000
    assert cap.profile_values[ExecutionProfile.DEEP] == 50000
    assert cap.profile_values[ExecutionProfile.MAX] == 125000


def test_mistral_reasoning_not_supported():
    """Verify MistralAI has reasoning NOT supported."""
    cap = get_provider_capability(PROVIDER_MISTRAL)
    assert cap.supported is False
    assert cap.reasoning_kwarg is None
    assert cap.has_reasoning_config is False


@pytest.mark.parametrize("provider", [
    PROVIDER_GOOGLE,
    PROVIDER_GOOGLE_CLOUD,
])
def test_google_family_reasoning(provider):
    """Verify Google and GoogleCloud have reasoning supported with thinking_budget."""
    cap = get_provider_capability(provider)
    assert cap.supported is True
    assert cap.reasoning_kwarg == "thinking_budget"
    assert cap.has_reasoning_config is True


def test_google_family_profile_values():
    """Verify Google family profile values match Anthropic (integers)."""
    for provider in (PROVIDER_GOOGLE, PROVIDER_GOOGLE_CLOUD):
        cap = get_provider_capability(provider)
        assert cap.profile_values[ExecutionProfile.FAST] == 1024
        assert cap.profile_values[ExecutionProfile.BALANCED] == 5000
        assert cap.profile_values[ExecutionProfile.DEEP] == 50000
        assert cap.profile_values[ExecutionProfile.MAX] == 125000


def test_custom_provider_not_supported():
    """Verify Custom provider has reasoning NOT supported."""
    cap = get_provider_capability(PROVIDER_CUSTOM)
    assert cap.supported is False
    assert cap.reasoning_kwarg is None
    assert cap.has_reasoning_config is False


@pytest.mark.parametrize("provider,expected_supported", [
    (PROVIDER_OPENAI, True),
    (PROVIDER_ANTHROPIC, True),
    (PROVIDER_GOOGLE, True),
    (PROVIDER_GOOGLE_CLOUD, True),
    (PROVIDER_AZURE, True),
    (PROVIDER_OPENROUTER, True),
    (PROVIDER_MISTRAL, False),
    (PROVIDER_CUSTOM, False),
])
def test_has_reasoning_config(provider, expected_supported):
    """Verify has_reasoning_config property works correctly for all built-in providers."""
    cap = get_provider_capability(provider)
    assert cap.has_reasoning_config is expected_supported


@pytest.mark.parametrize("supported, kwarg, expected", [
    (True, "reasoning_effort", True),
    (True, None, False),
    (False, "reasoning_effort", False),
    (False, None, False),
])
def test_has_reasoning_config_logic(supported, kwarg, expected):
    """Verify has_reasoning_config is True only when both supported and kwarg non-None."""
    cap = ProviderCapability(supported=supported, reasoning_kwarg=kwarg)
    assert cap.has_reasoning_config is expected


# ========================================================================
# 16-20. ModelCapability tests
# ========================================================================


def test_model_capability_exact_match_o1():
    """Verify o1 gets overrides: reasoning enabled, temperature disabled, max_completion_tokens kwarg."""
    _restore_builtins()  # Ensure builtins are present
    cap = ModelCapability.for_model(PROVIDER_OPENAI, "o1")
    assert cap.regex_pattern == "^o1"
    assert cap.supports_reasoning is True
    assert cap.disable_temperature is True
    assert cap.supports_vision is True
    assert cap.model_reasoning_kwarg == "max_completion_tokens"
    assert ExecutionProfile.FAST in cap.model_reasoning_config


def test_model_capability_prefix_matching():
    """Verify prefix matching works for model families."""
    _restore_builtins()
    # o1 prefix: max_completion_tokens, no temperature
    for model in ("o1", "o1-mini", "o1-2024-12-17"):
        cap = ModelCapability.for_model(PROVIDER_OPENAI, model)
        assert cap.regex_pattern == "^o1"
        assert cap.supports_reasoning is True
        assert cap.model_reasoning_kwarg == "max_completion_tokens"

    # o3 prefix: reasoning_effort (inherits provider default), no temperature
    for model in ("o3", "o3-mini"):
        cap = ModelCapability.for_model(PROVIDER_OPENAI, model)
        assert cap.regex_pattern == "^o3"
        assert cap.supports_reasoning is True
        assert cap.disable_temperature is True
        # o3 uses the default reasoning_effort (no model_reasoning_kwarg)

    # ^gemini-[2-9] should match gemini-2, gemini-2.5, etc.
    for model in ("gemini-2.0-pro", "gemini-2.5", "gemini-3"):
        cap = ModelCapability.for_model(PROVIDER_GOOGLE, model)
        assert cap.regex_pattern == "^gemini-[2-9]"


def test_model_capability_override_inheritance():
    """Verify override applied to provider defaults (not replacing everything)."""
    # Clear any user-registered overrides first
    clear_model_overrides()
    from tools import execution_profiles as _ep
    _ep._register_builtin_model_overrides()

    # Register a model override that only changes supports_vision
    register_model_override(
        ModelCapability(
            provider=PROVIDER_OPENAI,
            regex_pattern=r"^gpt-4o",
            supports_vision=True,
        )
    )

    # Get the override
    cap = ModelCapability.for_model(PROVIDER_OPENAI, "gpt-4o-pro")
    assert cap.supports_vision is True

    # Apply provider defaults — should inherit provider's reasoning config
    provider_cap = get_provider_capability(PROVIDER_OPENAI)
    resolved = cap.apply_provider_defaults(provider_cap)
    assert resolved.supported is True  # inherited from provider
    assert resolved.reasoning_kwarg == "reasoning_effort"


def test_disable_temperature_o_series():
    """Verify disable_temperature works for o-series models."""
    _restore_builtins()
    for model in ("o1", "o3", "o1-mini-predictions"):
        cap = ModelCapability.for_model(PROVIDER_OPENAI, model)
        assert cap.should_disable_temperature is True


@pytest.mark.parametrize("model", ["gpt-3.5-turbo", "gpt-4", "custom-model-x"])
def test_model_capability_for_model_unknown(model):
    """Verify for_model returns empty sentinel for models with no override."""
    cap = ModelCapability.for_model(PROVIDER_OPENAI, model)
    # Unknown models have no regex_pattern and empty model_id
    assert cap.regex_pattern == ""
    assert cap.model_id == ""
    assert cap.supports_reasoning is None
    assert cap.disable_temperature is False
    assert cap.should_disable_temperature is False


def test_model_capability_model_id_exact_match():
    """Test exact match when model_id is set (not regex)."""
    _restore_builtins()
    register_model_override(
        ModelCapability(
            provider=PROVIDER_OPENAI,
            model_id="gpt-4o-specific",
            supports_reasoning=True,
        )
    )
    cap = ModelCapability.for_model(PROVIDER_OPENAI, "gpt-4o-specific")
    assert cap.model_id == "gpt-4o-specific"
    assert cap.supports_reasoning is True


def test_model_capability_precedence_exact_over_prefix():
    """Verify exact match takes precedence over prefix match."""
    _restore_builtins()
    register_model_override(
        ModelCapability(
            provider=PROVIDER_OPENAI,
            model_id="o1",
            disable_temperature=False,
        )
    )

    # Exact match should be applied even though o1 also matches ^o\d
    cap = ModelCapability.for_model(PROVIDER_OPENAI, "o1")
    # The for_model method returns the ModelCapability object from the registry
    # For model_id "o1" with supports_reasoning=None, we need to check
    # that the exact match o1 rule is returned (the one with disable_temperature=False)
    # But wait — the built-in override has regex_pattern r"^o\d" for o1.
    # The exact match check happens first: rule.model_id == model_id.
    # So the ModelCapability(model_id="o1", disable_temperature=False) should be returned.
    assert cap.model_id == "o1"
    assert cap.disable_temperature is False


# ========================================================================
# 21-28. RuntimeConfigBuilder tests
# ========================================================================


class TestRuntimeConfigBuilderOpenAI:
    """Build and verify RuntimeConfig for OpenAI providers."""

    @pytest.mark.parametrize("profile,expected_value", [
        (ExecutionProfile.FAST, "low"),
        (ExecutionProfile.BALANCED, "medium"),
        (ExecutionProfile.DEEP, "high"),
        (ExecutionProfile.MAX, "high"),
    ])
    def test_openai_gpt4o_reasoning_values(self, profile, expected_value):
        """OpenAI gpt-4o at various profiles should produce correct reasoning values."""
        rc = RuntimeConfigBuilder.build(PROVIDER_OPENAI, "gpt-4o", profile)
        assert rc.reasoning_kwarg == "reasoning_effort"
        assert rc.reasoning_value == expected_value

    def test_openai_o3_reasoning(self):
        """OpenAI o3 should use provider default reasoning_effort with temperature disabled."""
        _restore_builtins()
        rc = RuntimeConfigBuilder.build(PROVIDER_OPENAI, "o3", ExecutionProfile.DEEP)
        # o3 uses provider default reasoning_effort (no model_reasoning_kwarg)
        assert rc.model_reasoning_kwarg is None
        assert rc.model_reasoning_value is None
        assert rc.reasoning_kwarg == "reasoning_effort"
        assert rc.reasoning_value == "high"
        assert rc.disable_temperature is True
        assert rc.supports_reasoning is True

    def test_openai_o1_model_specific_reasoning(self):
        """OpenAI o1 should use max_completion_tokens instead of reasoning_effort."""
        _restore_builtins()
        for profile, expected_token in [
            (ExecutionProfile.FAST, 128),
            (ExecutionProfile.BALANCED, 512),
            (ExecutionProfile.DEEP, 1024),
            (ExecutionProfile.MAX, 2048),
        ]:
            rc = RuntimeConfigBuilder.build(PROVIDER_OPENAI, "o1", profile)
            assert rc.model_reasoning_kwarg == "max_completion_tokens"
            assert rc.model_reasoning_value == expected_token
            # Should NOT use provider default reasoning_effort for o1
            assert rc.reasoning_kwarg is None
            assert rc.reasoning_value is None
            assert rc.disable_temperature is True
            assert rc.supports_reasoning is True

    def test_openai_o1_model_reasoning_override_prevents_provider_kwarg(self):
        """When model_reasoning_kwarg is set, the provider's kwarg must not appear."""
        _restore_builtins()
        rc = RuntimeConfigBuilder.build(PROVIDER_OPENAI, "o1", ExecutionProfile.MAX)
        # The model overrides the provider's reasoning mechanism entirely
        assert rc.reasoning_kwarg is None
        assert rc.reasoning_value is None
        # But the model-specific config takes effect
        assert rc.model_reasoning_kwarg == "max_completion_tokens"
        assert rc.model_reasoning_value == 2048


class TestRuntimeConfigBuilderAnthropic:
    """Build and verify RuntimeConfig for Anthropic provider."""

    @pytest.mark.parametrize("profile,expected_value", [
        (ExecutionProfile.FAST, 1024),
        (ExecutionProfile.BALANCED, 5000),
        (ExecutionProfile.DEEP, 50000),
        (ExecutionProfile.MAX, 125000),
    ])
    def test_anthropic_thinking_budget_values(self, profile, expected_value):
        """Anthropic models should produce correct thinking_budget values."""
        rc = RuntimeConfigBuilder.build(PROVIDER_ANTHROPIC, "claude-sonnet-4", profile)
        assert rc.reasoning_kwarg == "thinking_budget"
        assert rc.reasoning_value == expected_value


class TestRuntimeConfigBuilderNoReasoning:
    """Build RuntimeConfig for providers/models that have no reasoning support."""

    def test_mistral_no_reasoning(self):
        """Mistral model at DEEP should have reasoning_kwarg=None."""
        rc = RuntimeConfigBuilder.build(PROVIDER_MISTRAL, "mistral-large", ExecutionProfile.DEEP)
        assert rc.reasoning_kwarg is None
        assert rc.reasoning_value is None
        assert rc.supports_reasoning is False

    def test_custom_no_reasoning(self):
        """Custom/Ollama model should not have reasoning config."""
        rc = RuntimeConfigBuilder.build(PROVIDER_CUSTOM, "ollama-model", ExecutionProfile.DEEP)
        assert rc.reasoning_kwarg is None
        assert rc.reasoning_value is None
        assert rc.supports_reasoning is False


class TestRuntimeConfigBuilderGoogle:
    """Build RuntimeConfig for Google / GoogleCloud providers."""

    @pytest.mark.parametrize("provider", [PROVIDER_GOOGLE, PROVIDER_GOOGLE_CLOUD])
    def test_google_thinking_budget(self, provider):
        """Google providers should use thinking_budget kwarg."""
        rc = RuntimeConfigBuilder.build(provider, "gemini-2.0-pro", ExecutionProfile.DEEP)
        assert rc.reasoning_kwarg == "thinking_budget"
        assert rc.reasoning_value == 50000


# ========================================================================
# 29-31. Runtime config builder inheritance tests
# ========================================================================


class TestModelOverrideInheritance:
    """Model override inheritance from provider capabilities."""

    def test_inherits_provider_supported_true(self):
        """Model override inherits provider's supported=True when not overridden."""
        _restore_builtins()
        register_model_override(
            ModelCapability(
                provider=PROVIDER_OPENAI,
                model_id="special-model",
                # supports_reasoning NOT set — should inherit provider's True
            )
        )
        rc = RuntimeConfigBuilder.build(PROVIDER_OPENAI, "special-model", ExecutionProfile.FAST)
        assert rc.supports_reasoning is True

    def test_model_override_disables_reasoning(self):
        """Model override with supports_reasoning=False disables reasoning."""
        _restore_builtins()
        register_model_override(
            ModelCapability(
                provider=PROVIDER_OPENAI,
                model_id="no-reason-model",
                supports_reasoning=False,
            )
        )
        rc = RuntimeConfigBuilder.build(PROVIDER_OPENAI, "no-reason-model", ExecutionProfile.DEEP)
        assert rc.supports_reasoning is False
        assert rc.reasoning_kwarg is None
        assert rc.reasoning_value is None

    def test_custom_profile_values_override(self):
        """Custom profile_values override from model level replaces provider defaults."""
        _restore_builtins()
        custom_values = {
            ExecutionProfile.FAST: "fast",
            ExecutionProfile.BALANCED: "med",
            ExecutionProfile.DEEP: "deep",
            ExecutionProfile.MAX: "max",
        }
        register_model_override(
            ModelCapability(
                provider=PROVIDER_OPENAI,
                model_id="custom-values-model",
                supports_reasoning=True,
                profile_values=custom_values,
            )
        )
        rc = RuntimeConfigBuilder.build(
            PROVIDER_OPENAI, "custom-values-model", ExecutionProfile.FAST
        )
        assert rc.profile_values == custom_values
        assert rc.reasoning_value == "fast"

        rc_deep = RuntimeConfigBuilder.build(
            PROVIDER_OPENAI, "custom-values-model", ExecutionProfile.DEEP
        )
        assert rc_deep.reasoning_value == "deep"


# ========================================================================
# 32-39. build_runtime_kwargs tests
# ========================================================================


class TestBuildRuntimeKwargs:
    """Test build_runtime_kwargs function."""

    def test_with_reasoning_enabled(self):
        """Build kwargs with reasoning enabled -> kwargs should contain reasoning_kwarg."""
        rc = RuntimeConfig(
            provider=PROVIDER_OPENAI,
            model_id="gpt-4o",
            execution_profile=ExecutionProfile.DEEP,
            reasoning_kwarg="reasoning_effort",
            reasoning_value="high",
            supports_reasoning=True,
        )
        kwargs = build_runtime_kwargs(rc)
        assert "reasoning_effort" in kwargs
        assert kwargs["reasoning_effort"] == "high"

    def test_with_reasoning_disabled(self):
        """Build kwargs with reasoning disabled -> kwargs should NOT contain reasoning_kwarg."""
        rc = RuntimeConfig(
            provider=PROVIDER_MISTRAL,
            model_id="mistral-large",
            execution_profile=ExecutionProfile.DEEP,
            reasoning_kwarg=None,
            reasoning_value=None,
            supports_reasoning=False,
        )
        kwargs = build_runtime_kwargs(rc)
        assert "reasoning_effort" not in kwargs
        assert kwargs == {}

    def test_with_temperature(self):
        """build_runtime_kwargs with temperature=0.7 -> should contain temperature."""
        rc = RuntimeConfig(
            provider=PROVIDER_OPENAI,
            model_id="gpt-4o",
            execution_profile=ExecutionProfile.FAST,
        )
        kwargs = build_runtime_kwargs(rc, temperature=0.7)
        assert "temperature" in kwargs
        assert kwargs["temperature"] == 0.7

    @pytest.mark.parametrize("temperature", [0.0, 0.7, 1.0, 0.15])
    def test_temperature_various_values(self, temperature):
        """Build kwargs with various temperature values."""
        rc = RuntimeConfig(
            provider=PROVIDER_OPENAI,
            model_id="gpt-4o",
            execution_profile=ExecutionProfile.FAST,
        )
        kwargs = build_runtime_kwargs(rc, temperature=temperature)
        assert kwargs["temperature"] == temperature

    def test_disable_temperature_excludes_temperature(self):
        """build_runtime_kwargs with disable_temperature=True -> excluded even if temperature passed."""
        rc = RuntimeConfig(
            provider=PROVIDER_OPENAI,
            model_id="o1",
            execution_profile=ExecutionProfile.MAX,
            disable_temperature=True,
            supports_reasoning=True,
        )
        kwargs = build_runtime_kwargs(rc, temperature=0.7)
        assert "temperature" not in kwargs

    def test_disable_temperature_false_includes_temperature(self):
        """build_runtime_kwargs with disable_temperature=False -> includes temperature."""
        rc = RuntimeConfig(
            provider=PROVIDER_OPENAI,
            model_id="gpt-4o",
            execution_profile=ExecutionProfile.DEEP,
            disable_temperature=False,
        )
        kwargs = build_runtime_kwargs(rc, temperature=0.7)
        assert "temperature" in kwargs
        assert kwargs["temperature"] == 0.7

    def test_additional_kwargs_merged(self):
        """build_runtime_kwargs with additional_kwargs -> merged into result."""
        rc = RuntimeConfig(
            provider=PROVIDER_OPENAI,
            model_id="gpt-4o",
            execution_profile=ExecutionProfile.FAST,
        )
        additional = {"top_p": 0.95, "presence_penalty": 0.1}
        kwargs = build_runtime_kwargs(rc, temperature=0.7, additional_kwargs=additional)
        assert kwargs["temperature"] == 0.7
        assert kwargs["top_p"] == 0.95
        assert kwargs["presence_penalty"] == 0.1

    def test_additional_kwargs_override_reasoning(self):
        """Additional kwargs can override reasoning values."""
        rc = RuntimeConfig(
            provider=PROVIDER_OPENAI,
            model_id="gpt-4o",
            execution_profile=ExecutionProfile.DEEP,
            reasoning_kwarg="reasoning_effort",
            reasoning_value="high",
        )
        kwargs = build_runtime_kwargs(rc, additional_kwargs={"reasoning_effort": "very_high"})
        assert kwargs["reasoning_effort"] == "very_high"

    def test_no_temperature_passed(self):
        """build_runtime_kwargs with no temperature arg -> should not include temperature."""
        rc = RuntimeConfig(
            provider=PROVIDER_OPENAI,
            model_id="gpt-4o",
            execution_profile=ExecutionProfile.FAST,
        )
        kwargs = build_runtime_kwargs(rc)
        assert "temperature" not in kwargs

    def test_anthropic_fast_profile(self):
        """Build kwargs for runtime config at FAST profile for Anthropic."""
        rc = RuntimeConfigBuilder.build(
            PROVIDER_ANTHROPIC,
            "claude-sonnet-4",
            ExecutionProfile.FAST,
        )
        kwargs = build_runtime_kwargs(rc, temperature=0.7)
        assert kwargs["thinking_budget"] == 1024
        assert kwargs["temperature"] == 0.7

    def test_anthropic_max_profile(self):
        """Build kwargs for runtime config at MAX profile for Anthropic."""
        rc = RuntimeConfigBuilder.build(
            PROVIDER_ANTHROPIC,
            "claude-opus-4",
            ExecutionProfile.MAX,
        )
        kwargs = build_runtime_kwargs(rc, temperature=0.5)
        assert kwargs["thinking_budget"] == 125000
        assert kwargs["temperature"] == 0.5

    def test_combined_reasoning_and_temperature_and_additional(self):
        """Build kwargs with reasoning, temperature, and additional kwargs all set."""
        rc = RuntimeConfigBuilder.build(
            PROVIDER_OPENAI,
            "gpt-4o",
            ExecutionProfile.BALANCED,
        )
        kwargs = build_runtime_kwargs(
            rc,
            temperature=0.8,
            additional_kwargs={"top_p": 0.9},
        )
        assert kwargs["reasoning_effort"] == "medium"
        assert kwargs["temperature"] == 0.8
        assert kwargs["top_p"] == 0.9

    def test_o1_model_reasoning_no_temperature_in_kwargs(self):
        """o1 models use max_completion_tokens (not reasoning_effort) and have no temperature."""
        _restore_builtins()
        rc = RuntimeConfigBuilder.build(PROVIDER_OPENAI, "o1", ExecutionProfile.MAX)
        kwargs = build_runtime_kwargs(rc, temperature=0.7)
        assert "temperature" not in kwargs
        # o1 uses model_reasoning_kwarg, not provider reasoning_effort
        assert "max_completion_tokens" in kwargs
        assert kwargs["max_completion_tokens"] == 2048
        assert "reasoning_effort" not in kwargs


# ========================================================================
# 40-42. Provider lookup tests
# ========================================================================


class TestProviderLookup:
    """Test provider registry lookup and manipulation functions."""

    def test_nonexistent_provider_returns_disabled(self):
        """get_provider_capability for non-existent provider returns disabled ProviderCapability."""
        cap = get_provider_capability("NonExistentProvider")
        assert isinstance(cap, ProviderCapability)
        assert cap.supported is False
        assert cap.reasoning_kwarg is None
        assert cap.has_reasoning_config is False
        assert cap.default_profile == ExecutionProfile.BALANCED

    def test_register_provider_capability(self, register_test_provider):
        """register_provider_capability adds new provider to registry."""
        new_cap = ProviderCapability(
            supported=True,
            reasoning_kwarg="custom_reasoning",
            profile_values={
                ExecutionProfile.FAST: 1,
                ExecutionProfile.DEEP: 222,
            },
            default_profile=ExecutionProfile.FAST,
        )
        register_test_provider(new_cap, "CustomNewProvider")

        cap = get_provider_capability("CustomNewProvider")
        assert cap is new_cap
        assert cap.supported is True
        assert cap.reasoning_kwarg == "custom_reasoning"
        assert cap.profile_values[ExecutionProfile.FAST] == 1
        assert cap.default_profile == ExecutionProfile.FAST

    def test_register_provider_overwrites(self, register_test_provider):
        """register_provider_capability overwrites existing entry."""
        cap1 = ProviderCapability(supported=True, default_profile=ExecutionProfile.FAST)
        cap2 = ProviderCapability(supported=False, default_profile=ExecutionProfile.MAX)

        register_test_provider(cap1, "OverwriteProvider")
        register_test_provider(cap2, "OverwriteProvider")

        cap = get_provider_capability("OverwriteProvider")
        assert cap.supported is False
        assert cap.default_profile == ExecutionProfile.MAX


class TestClearModelOverrides:
    """Test clear_model_overrides function."""

    def test_clears_all_overrides(self):
        """clear_model_overrides clears all overrides from the registry."""
        register_model_override(
            ModelCapability(model_id="model-1", supports_reasoning=True)
        )
        register_model_override(
            ModelCapability(model_id="model-2", supports_reasoning=False)
        )

        assert len(_MODEL_OVERRIDES) == 2

        clear_model_overrides()

        assert len(_MODEL_OVERRIDES) == 0

    def test_clear_does_not_affect_provider_registry(self):
        """Clearing model overrides should not affect provider registry."""
        # Built-in providers should still be registered after clearing model overrides
        for provider in (PROVIDER_OPENAI, PROVIDER_ANTHROPIC, PROVIDER_MISTRAL):
            cap = get_provider_capability(provider)
            assert isinstance(cap, ProviderCapability)

        # Also test a registered test provider
        def register_test_provider(cap, provider_name):
            _REGISTRY[provider_name] = cap

        test_cap = ProviderCapability(supported=True, reasoning_kwarg="test")
        register_test_provider(test_cap, "TestProvider")
        assert get_provider_capability("TestProvider").supported is True

        clear_model_overrides()

        # Provider registry untouched
        assert get_provider_capability("TestProvider").supported is True


# ========================================================================
# 43-46. Edge cases
# ========================================================================


@pytest.mark.parametrize("empty_value", [
    ("", ""),       # empty provider + empty model_id
    ("", "model"),  # empty provider
    ("OpenAI", ""),  # empty model_id
])
def test_for_model_empty_strings(empty_value):
    """ModelCapability.for_model with empty provider or model_id string."""
    provider, model_id = empty_value
    cap = ModelCapability.for_model(provider, model_id)
    # Should return the base sentinel — no overrides for empty strings
    assert cap is not None
    assert isinstance(cap, ModelCapability)
    assert cap.supports_reasoning is None
    assert cap.disable_temperature is False


def test_model_capability_empty_provider():
    """for_model with empty provider returns empty sentinel regardless of model."""
    cap = ModelCapability.for_model("", "o1")
    assert cap.regex_pattern == ""
    assert cap.model_id == ""


def test_model_capability_empty_model_id():
    """for_model with empty model_id returns empty sentinel."""
    cap = ModelCapability.for_model(PROVIDER_OPENAI, "")
    assert cap.regex_pattern == ""
    assert cap.model_id == ""


def test_fast_profile_boundary():
    """Profile values at boundary (FAST level) — lowest reasoning effort."""
    rc = RuntimeConfigBuilder.build(PROVIDER_OPENAI, "gpt-4o", ExecutionProfile.FAST)
    assert rc.reasoning_value is not None
    assert rc.execution_profile == ExecutionProfile.FAST
    # FAST is the minimum profile — should have the smallest/intensity value
    assert rc.reasoning_value == "low"

    rc_anthropic = RuntimeConfigBuilder.build(
        PROVIDER_ANTHROPIC, "claude-sonnet-4", ExecutionProfile.FAST
    )
    assert rc_anthropic.reasoning_value == 1024


def test_max_profile_boundary():
    """Profile values at boundary (MAX level) — highest reasoning effort."""
    rc = RuntimeConfigBuilder.build(PROVIDER_OPENAI, "gpt-4o", ExecutionProfile.MAX)
    assert rc.reasoning_value is not None
    assert rc.execution_profile == ExecutionProfile.MAX
    # MAX should be the highest intensity value
    assert rc.reasoning_value == "high"

    rc_anthropic = RuntimeConfigBuilder.build(
        PROVIDER_ANTHROPIC, "claude-sonnet-4", ExecutionProfile.MAX
    )
    assert rc_anthropic.reasoning_value == 125000


def test_runtime_config_frozen():
    """RuntimeConfig is a frozen dataclass — immutable."""
    rc = RuntimeConfig(
        provider=PROVIDER_OPENAI,
        model_id="gpt-4o",
        execution_profile=ExecutionProfile.FAST,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        rc.provider = "new-provider"  # type: ignore[assignment]

    with pytest.raises(dataclasses.FrozenInstanceError):
        rc.model_id = "new-model"  # type: ignore[assignment]


def test_provider_capability_frozen():
    """ProviderCapability is a frozen dataclass."""
    cap = ProviderCapability(supported=True, reasoning_kwarg="test")
    with pytest.raises(dataclasses.FrozenInstanceError):
        cap.reasoning_kwarg = "new"  # type: ignore[misc]


def test_model_capability_frozen():
    """ModelCapability is a frozen dataclass."""
    cap = ModelCapability(supports_reasoning=True)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cap.supports_vision = True  # type: ignore[misc]


def test_build_runtime_kwargs_empty_config():
    """build_runtime_kwargs with a minimal RuntimeConfig produces empty dict."""
    rc = RuntimeConfig(
        provider="Unknown",
        model_id="unknown",
        execution_profile=ExecutionProfile.FAST,
    )
    kwargs = build_runtime_kwargs(rc)
    assert kwargs == {}

    kwargs_with_temp = build_runtime_kwargs(rc, temperature=0.5)
    assert kwargs_with_temp == {"temperature": 0.5}


def test_runtime_config_profile_values_inheritance():
    """RuntimeConfig should carry the effective profile_values."""
    # Without model override — should use provider defaults
    rc = RuntimeConfigBuilder.build(
        PROVIDER_OPENAI, "gpt-4o", ExecutionProfile.BALANCED
    )
    assert ExecutionProfile.FAST in rc.profile_values
    assert ExecutionProfile.MAX in rc.profile_values
    assert rc.profile_values[ExecutionProfile.FAST] == "low"
    assert rc.profile_values[ExecutionProfile.MAX] == "high"


@pytest.mark.parametrize("profile", list(ExecutionProfile))
def test_all_profiles_produce_reasoning_value_when_supported(profile):
    """Every supported profile should produce a reasoning value for reasoning-capable providers."""
    rc = RuntimeConfigBuilder.build(PROVIDER_OPENAI, "gpt-4o", profile)
    assert rc.reasoning_kwarg is not None
    assert rc.reasoning_value is not None


@pytest.mark.parametrize("profile", list(ExecutionProfile))
def test_all_profiles_produce_no_reasoning_when_not_supported(profile):
    """Every profile should have no reasoning value for non-reasoning providers."""
    rc = RuntimeConfigBuilder.build(PROVIDER_MISTRAL, "mistral-large", profile)
    assert rc.reasoning_kwarg is None
    assert rc.reasoning_value is None
    assert rc.supports_reasoning is False


# ========================================================================
# 99-101. gpt-5 temperature \u0026 reasoning handling
# ========================================================================


class TestGpt5TemperatureHandling:
    """gpt-5.1/5.2/5.3 reject temperature != 1.0 — force_temperature=1.0."""

    @pytest.mark.parametrize("profile", list(ExecutionProfile))
    def test_gpt51_force_temperature_one(self, profile):
        """gpt-5.1 should force temperature to 1.0 at every profile."""
        _restore_builtins()
        rc = RuntimeConfigBuilder.build(PROVIDER_OPENAI, "gpt-5.1-chat-latest", profile)
        assert rc.force_temperature == 1.0
        kwargs = build_runtime_kwargs(rc, temperature=0.7)
        assert kwargs["temperature"] == 1.0

    @pytest.mark.parametrize("model_id", [
        "gpt-5.2-chat-latest",
        "gpt-5.3-chat-latest",
    ])
    @pytest.mark.parametrize("profile", list(ExecutionProfile))
    def test_gpt52_gpt53_force_temperature_one(self, model_id, profile):
        """gpt-5.2 and gpt-5.3 should also force temperature to 1.0."""
        _restore_builtins()
        rc = RuntimeConfigBuilder.build(PROVIDER_OPENAI, model_id, profile)
        assert rc.force_temperature == 1.0
        kwargs = build_runtime_kwargs(rc, temperature=0.0)
        assert kwargs["temperature"] == 1.0

    def test_gpt5_temperature_forcing_preserves_reasoning(self):
        """gpt-5.1/5.2/5.3 should keep reasoning enabled (inherited)."""
        _restore_builtins()
        rc = RuntimeConfigBuilder.build(PROVIDER_OPENAI, "gpt-5.1-chat-latest", ExecutionProfile.FAST)
        assert rc.supports_reasoning is True
        assert rc.reasoning_kwarg == "reasoning_effort"


class TestGpt5ReasoningDisabled:
    """gpt-5.4+ reject reasoning_effort with function tools — reasoning disabled."""

    @pytest.mark.parametrize("model_id", [
        "gpt-5.4-chat-latest",
        "gpt-5.5-chat-latest",
        "gpt-5.6-reasoning",
        "gpt-5.9-pro",
    ])
    @pytest.mark.parametrize("profile", list(ExecutionProfile))
    def test_gpt54_plus_no_reasoning(self, model_id, profile):
        """gpt-5.4+ should have reasoning disabled regardless of profile."""
        _restore_builtins()
        rc = RuntimeConfigBuilder.build(PROVIDER_OPENAI, model_id, profile)
        assert rc.supports_reasoning is False
        assert rc.reasoning_kwarg is None
        assert rc.reasoning_value is None
        kwargs = build_runtime_kwargs(rc)
        assert "reasoning_effort" not in kwargs

    def test_gpt54_inherits_temperature(self):
        """gpt-5.4 should NOT force temperature — it passes normal temperature through."""
        _restore_builtins()
        rc = RuntimeConfigBuilder.build(PROVIDER_OPENAI, "gpt-5.4-chat-latest", ExecutionProfile.FAST)
        # No force_temperature, no disable_temperature
        assert rc.force_temperature is None
        assert rc.disable_temperature is False
        kwargs = build_runtime_kwargs(rc, temperature=0.7)
        assert kwargs["temperature"] == 0.7


class TestGpt5RegexScope:
    """Verify the regex patterns match intended models and avoid false positives."""

    def test_gpt5_minor_regex_matches_multi_digit(self):
        """The gpt-5. reasoning pattern should match gpt-5.10 etc."""
        _restore_builtins()
        rc = RuntimeConfigBuilder.build(PROVIDER_OPENAI, "gpt-5.10-chat-latest", ExecutionProfile.FAST)
        # Should match gpt-5. reasoning-disabled pattern
        assert rc.supports_reasoning is False

    def test_gpt5_minor_pattern_does_not_match_gpt4(self):
        """gpt-4 models should NOT match the gpt-5 pattern."""
        _restore_builtins()
        rc = RuntimeConfigBuilder.build(PROVIDER_OPENAI, "gpt-4o", ExecutionProfile.DEEP)
        assert rc.supports_reasoning is True
        assert rc.reasoning_kwarg == "reasoning_effort"

    def test_gpt51_does_not_disable_reasoning(self):
        """gpt-5.1 should NOT disable reasoning — only force temperature."""
        _restore_builtins()
        rc = RuntimeConfigBuilder.build(PROVIDER_OPENAI, "gpt-5.1-chat-latest", ExecutionProfile.DEEP)
        assert rc.supports_reasoning is True
        assert rc.force_temperature == 1.0
        assert rc.reasoning_kwarg == "reasoning_effort"

    def test_no_double_matching_gpt54(self):
        """gpt-5.4 must NOT get force_temperature from gpt-5.[1-3] rule."""
        _restore_builtins()
        rc = RuntimeConfigBuilder.build(PROVIDER_OPENAI, "gpt-5.4-chat-latest", ExecutionProfile.DEEP)
        assert rc.force_temperature is None  # Must NOT be forced
        assert rc.supports_reasoning is False
        kwargs = build_runtime_kwargs(rc, temperature=0.7)
        assert kwargs.get("temperature") == 0.7  # Normal temp allowed
        assert "reasoning_effort" not in kwargs  # No reasoning

    def test_no_double_matching_all_gpt5_versions(self):
        """Verify correct behavior across the full gpt-5 family."""
        _restore_builtins()
        test_cases = [
            ("gpt-5.1-chat-latest", True, 1.0, True),      # force_temp, has_reasoning
            ("gpt-5.2-chat-latest", True, 1.0, True),
            ("gpt-5.3-chat-latest", True, 1.0, True),
            ("gpt-5.4-chat-latest", False, None, False),    # no force, no reasoning
            ("gpt-5.5-reasoning", False, None, False),
            ("gpt-5.9-pro", False, None, False),
            ("gpt-5.10-mini", False, None, False),          # also no reasoning
        ]
        for model_id, has_force, force_val, should_reason in test_cases:
            rc = RuntimeConfigBuilder.build(PROVIDER_OPENAI, model_id, ExecutionProfile.FAST)
            if has_force:
                assert rc.force_temperature == force_val, f"{model_id} should force temp"
            else:
                assert rc.force_temperature is None, f"{model_id} should NOT force temp"
            assert rc.supports_reasoning == should_reason, f"{model_id} reasoning mismatch"

    def test_o1_still_works_normal(self):
        """Verify o1 models are unaffected by gpt-5 changes."""
        _restore_builtins()
        rc = RuntimeConfigBuilder.build(PROVIDER_OPENAI, "o1", ExecutionProfile.BALANCED)
        assert rc.force_temperature is None  # o1 disables temp differently
        assert rc.disable_temperature is True  # o1 uses disable_temperature
        assert rc.supports_reasoning is True

    def test_gpt4o_still_works_normal(self):
        """Verify gpt-4o is unaffected by gpt-5 changes."""
        _restore_builtins()
        rc = RuntimeConfigBuilder.build(PROVIDER_OPENAI, "gpt-4o", ExecutionProfile.DEEP)
        assert rc.force_temperature is None
        assert rc.supports_reasoning is True
        assert rc.reasoning_kwarg == "reasoning_effort"

    def test_anthropic_claude_unaffected(self):
        """Verify Anthropic models are unaffected."""
        _restore_builtins()
        rc = RuntimeConfigBuilder.build(PROVIDER_ANTHROPIC, "claude-sonnet-4", ExecutionProfile.MAX)
        assert rc.force_temperature is None
        assert rc.reasoning_kwarg == "thinking_budget"
        assert rc.reasoning_value == 125000
