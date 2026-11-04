"""Unit tests for A2A field validators on the internal agent schema (step_009, FR-3).

Covers:
- trimming and empty-string -> None normalization for name/description overrides;
- length caps: name <=255, description <=1000;
- tags: trim, drop empties, dedupe case-insensitively (keep first), <=20 items, <=50 chars;
- examples: trim, drop empties, <=20 items, <=500 chars;
- card_visibility: literal set only, invalid value -> 422;
- defaults when the caller omits the fields entirely.

Only ``CreateUpdateAgentSchema`` (internal) carries these fields; the public API
schemas (``PublicAgentSchema``, ``PublicAgentDetailSchema``, ``CreateAgentRequestSchema``,
``UpdateAgentRequestSchema``) intentionally do not.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.agent_schemas import CreateUpdateAgentSchema


def _cu(**kwargs):
    return CreateUpdateAgentSchema(name="test", **kwargs)


class TestDefaults:
    def test_defaults_when_omitted(self):
        agent = _cu()
        assert agent.a2a_enabled is False
        assert agent.a2a_card_visibility == "public"
        assert agent.a2a_name_override is None
        assert agent.a2a_description_override is None
        assert agent.a2a_skill_tags == []
        assert agent.a2a_examples == []


class TestNameOverride:
    def test_trims_whitespace(self):
        assert _cu(a2a_name_override="  Bot  ").a2a_name_override == "Bot"

    def test_empty_string_becomes_none(self):
        assert _cu(a2a_name_override="   ").a2a_name_override is None

    def test_at_cap_is_valid(self):
        value = "x" * 255
        assert _cu(a2a_name_override=value).a2a_name_override == value

    def test_over_cap_raises(self):
        with pytest.raises(ValidationError):
            _cu(a2a_name_override="x" * 256)


class TestDescriptionOverride:
    def test_trims_whitespace(self):
        assert _cu(a2a_description_override="  hi  ").a2a_description_override == "hi"

    def test_empty_string_becomes_none(self):
        assert _cu(a2a_description_override="").a2a_description_override is None

    def test_at_cap_is_valid(self):
        value = "x" * 1000
        assert _cu(a2a_description_override=value).a2a_description_override == value

    def test_over_cap_raises(self):
        with pytest.raises(ValidationError):
            _cu(a2a_description_override="x" * 1001)


class TestSkillTags:
    def test_trims_and_drops_empties(self):
        agent = _cu(a2a_skill_tags=["  billing ", "", "   ", "support"])
        assert agent.a2a_skill_tags == ["billing", "support"]

    def test_dedupes_case_insensitively_keeping_first(self):
        agent = _cu(a2a_skill_tags=["Billing", "billing", "BILLING"])
        assert agent.a2a_skill_tags == ["Billing"]

    def test_21_tags_raises_422(self):
        with pytest.raises(ValidationError):
            _cu(a2a_skill_tags=[f"tag{i}" for i in range(21)])

    def test_20_tags_is_valid(self):
        tags = [f"tag{i}" for i in range(20)]
        assert _cu(a2a_skill_tags=tags).a2a_skill_tags == tags

    def test_tag_over_50_chars_raises(self):
        with pytest.raises(ValidationError):
            _cu(a2a_skill_tags=["x" * 51])

    def test_tag_at_50_chars_is_valid(self):
        tag = "x" * 50
        assert _cu(a2a_skill_tags=[tag]).a2a_skill_tags == [tag]

    def test_none_defaults_to_empty_list(self):
        assert _cu(a2a_skill_tags=None).a2a_skill_tags == []


class TestExamples:
    def test_trims_and_drops_empties(self):
        agent = _cu(a2a_examples=["  Hello  ", "", "   "])
        assert agent.a2a_examples == ["Hello"]

    def test_21_examples_raises_422(self):
        with pytest.raises(ValidationError):
            _cu(a2a_examples=[f"example {i}" for i in range(21)])

    def test_20_examples_is_valid(self):
        examples = [f"example {i}" for i in range(20)]
        assert _cu(a2a_examples=examples).a2a_examples == examples

    def test_example_over_500_chars_raises(self):
        with pytest.raises(ValidationError):
            _cu(a2a_examples=["x" * 501])

    def test_example_at_500_chars_is_valid(self):
        example = "x" * 500
        assert _cu(a2a_examples=[example]).a2a_examples == [example]


class TestCardVisibility:
    def test_public_is_valid(self):
        assert _cu(a2a_card_visibility="public").a2a_card_visibility == "public"

    def test_api_key_is_valid(self):
        assert _cu(a2a_card_visibility="api_key").a2a_card_visibility == "api_key"

    def test_invalid_value_raises_422(self):
        with pytest.raises(ValidationError):
            _cu(a2a_card_visibility="private")

    def test_explicit_null_raises_422(self):
        """FR-3 has no 'unset' meaning for visibility; null must not silently become 'public'."""
        with pytest.raises(ValidationError):
            _cu(a2a_card_visibility=None)

    def test_omitted_uses_default_public(self):
        assert _cu().a2a_card_visibility == "public"


class TestEnabledFlag:
    def test_enabled_true_roundtrips(self):
        assert _cu(a2a_enabled=True).a2a_enabled is True

    def test_explicit_null_raises_422(self):
        with pytest.raises(ValidationError):
            _cu(a2a_enabled=None)


class TestModelFieldsSet:
    """``model_fields_set`` is how the router distinguishes 'omitted' from 'sent'."""

    def test_omitted_a2a_fields_are_not_in_fields_set(self):
        agent = _cu()
        assert "a2a_enabled" not in agent.model_fields_set
        assert "a2a_card_visibility" not in agent.model_fields_set
        assert "a2a_name_override" not in agent.model_fields_set

    def test_explicitly_sent_a2a_fields_are_in_fields_set(self):
        agent = _cu(a2a_enabled=True, a2a_card_visibility="public")
        assert "a2a_enabled" in agent.model_fields_set
        assert "a2a_card_visibility" in agent.model_fields_set


class TestCleanText:
    """Shared NUL/control-character hygiene (exported for step_010 reuse)."""

    def test_rejects_nul_in_name_override(self):
        with pytest.raises(ValidationError):
            _cu(a2a_name_override="bad\x00name")

    def test_rejects_nul_in_skill_tag(self):
        with pytest.raises(ValidationError):
            _cu(a2a_skill_tags=["bad\x00tag"])

    def test_rejects_nul_in_example(self):
        with pytest.raises(ValidationError):
            _cu(a2a_examples=["bad\x00example"])

    def test_rejects_control_char_in_description(self):
        with pytest.raises(ValidationError):
            _cu(a2a_description_override="bad\x01description")

    def test_rejects_newline_in_name_override(self):
        """Name override is single-line; \\n is not allowed there."""
        with pytest.raises(ValidationError):
            _cu(a2a_name_override="line1\nline2")

    def test_rejects_newline_in_skill_tag(self):
        with pytest.raises(ValidationError):
            _cu(a2a_skill_tags=["line1\nline2"])

    def test_allows_newline_in_description_override(self):
        agent = _cu(a2a_description_override="line1\nline2")
        assert agent.a2a_description_override == "line1\nline2"

    def test_allows_newline_in_examples(self):
        agent = _cu(a2a_examples=["line1\nline2"])
        assert agent.a2a_examples == ["line1\nline2"]

    def test_clean_a2a_text_is_importable(self):
        from schemas.agent_schemas import clean_a2a_text
        assert clean_a2a_text("hello") == "hello"
        with pytest.raises(ValueError):
            clean_a2a_text("bad\x00value")

    def test_clean_a2a_text_allow_newline_flag(self):
        from schemas.agent_schemas import clean_a2a_text
        with pytest.raises(ValueError):
            clean_a2a_text("a\nb", allow_newline=False)
        assert clean_a2a_text("a\nb", allow_newline=True) == "a\nb"


class TestRawListCap:
    """Field(max_length=100) bounds the raw list before the dedupe/trim pass runs."""

    def test_101_raw_skill_tags_raises_422_before_dedupe(self):
        # All identical, so post-dedupe would be 1 item; the raw-list cap must still
        # reject it, proving the cheap guard runs before any per-item processing.
        with pytest.raises(ValidationError):
            _cu(a2a_skill_tags=["same"] * 101)

    def test_100_raw_skill_tags_is_within_the_raw_cap(self):
        # Distinct values so the post-dedupe count (20 max) is the second gate hit.
        with pytest.raises(ValidationError) as exc_info:
            _cu(a2a_skill_tags=[f"tag{i}" for i in range(100)])
        assert "at most 20 items" in str(exc_info.value)

    def test_101_raw_examples_raises_422_before_dedupe(self):
        with pytest.raises(ValidationError):
            _cu(a2a_examples=["same"] * 101)
