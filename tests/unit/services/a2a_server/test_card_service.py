"""Unit coverage for `services.a2a_server.card_service` (step_011, FR-5/6/7/8/9, AC-1/2/8/9/10).

No DB: every test builds an `A2AAgentSnapshot` directly and feeds it to the
pure builder functions. `TestRealShapedAgentLeakTest` additionally runs a
real `build_snapshot()` first (review round 2, MEDIUM-2), so the leak proof
covers the full ORM->snapshot->card pipeline, not just the card builder in
isolation.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from services.a2a_server.card_service import build_extended_card, build_public_card, card_to_json, catalog_entry
from services.a2a_server.snapshot import A2AAgentSnapshot, build_snapshot

BASE_URL = "https://mattin.example.test"


def _snapshot(**overrides) -> A2AAgentSnapshot:
    defaults = dict(
        app_id=1,
        app_slug="acme",
        app_frozen=False,
        app_max_file_size_mb=None,
        app_name="Acme",
        app_agent_cors_origins=None,
        agent_id=9,
        agent_name="Support Bot",
        agent_description="Helps with support questions.",
        agent_frozen=False,
        a2a_enabled=True,
        visibility="public",
        name_override=None,
        description_override=None,
        skill_tags=(),
        examples=(),
        skills=(),
        has_output_parser=False,
        can_produce_files=False,
        accepts_files=True,
        ai_provider="OpenAI",
        model_id="gpt-3.5-turbo",
        has_memory=False,
    )
    defaults.update(overrides)
    return A2AAgentSnapshot(**defaults)


class TestBuildPublicCard:
    def test_ac1_card_fields_and_exact_rpc_url(self):
        snap = _snapshot()
        card = build_public_card(snap, BASE_URL)

        assert card.name == "Support Bot"
        assert card.description == "Helps with support questions."
        assert len(card.supported_interfaces) == 1
        iface = card.supported_interfaces[0]
        assert iface.url == "https://mattin.example.test/a2a/v1/apps/acme/agents/9"
        assert iface.protocol_binding == "JSONRPC"
        assert iface.protocol_version == "1.0"
        assert card.capabilities.streaming is True
        assert card.capabilities.push_notifications is False
        assert card.capabilities.extended_agent_card is True
        assert "apiKey" in card.security_schemes
        assert card.security_schemes["apiKey"].api_key_security_scheme.location == "header"
        assert card.security_schemes["apiKey"].api_key_security_scheme.name == "X-API-KEY"

    def test_name_and_description_overrides_win(self):
        snap = _snapshot(name_override="Override Name", description_override="Override description")
        card = build_public_card(snap, BASE_URL)
        assert card.name == "Override Name"
        assert card.description == "Override description"

    def test_ac10_base_url_drives_provider_and_rpc_url(self):
        snap = _snapshot()
        card = build_public_card(snap, "https://other.example.test")
        assert card.provider.url == "https://other.example.test"
        assert card.supported_interfaces[0].url.startswith("https://other.example.test/")

    def test_ac2_leak_test_no_secrets_prompt_or_internal_names(self):
        snap = _snapshot(
            agent_description="Public description",
            skills=((1, "Billing", "Handles billing"),),
            examples=("example one", "example two"),
        )
        card = build_public_card(snap, BASE_URL)
        serialized = json.dumps(card_to_json(card))

        for leaked in ("SECRET-PROMPT", "silo", "example one", "example two", "mcp"):
            assert leaked not in serialized

    def test_ac8_skills_mapping_two_skills(self):
        snap = _snapshot(
            skills=((1, "Billing", "Handles billing"), (2, "Refunds", "Handles refunds")),
            skill_tags=("finance",),
        )
        card = build_public_card(snap, BASE_URL)
        assert [s.id for s in card.skills] == ["skill-1", "skill-2"]
        assert [s.name for s in card.skills] == ["Billing", "Refunds"]
        assert all(list(s.tags) == ["finance"] for s in card.skills)
        assert all(list(s.examples) == [] for s in card.skills)

    def test_ac8_no_skills_falls_back_to_synthetic_chat_skill(self):
        snap = _snapshot(skills=())
        card = build_public_card(snap, BASE_URL)
        assert len(card.skills) == 1
        assert card.skills[0].id == "chat"
        assert card.skills[0].name == snap.card_name
        assert card.skills[0].description == snap.card_description

    def test_skill_description_falls_back_to_skill_description(self):
        # association description is the empty string -> falls back to the skill's own
        # description; both are already resolved onto the snapshot tuple by the time
        # the card builder sees them (snapshot.build_snapshot), so this just asserts
        # the builder passes the tuple's description through verbatim.
        snap = _snapshot(skills=((1, "Billing", "Fallback description"),))
        card = build_public_card(snap, BASE_URL)
        assert card.skills[0].description == "Fallback description"

    def test_ac9_vision_model_adds_image_modes(self):
        snap = _snapshot(ai_provider="OpenAI", model_id="gpt-4o", accepts_files=True)
        card = build_public_card(snap, BASE_URL)
        assert "image/jpeg" in card.default_input_modes
        assert "image/png" in card.default_input_modes

    def test_ac9_non_vision_model_adds_no_image_modes_even_with_supports_video(self):
        # supports_video is deliberately not part of the snapshot/heuristic input;
        # this asserts a plain non-vision model id yields no image/* modes.
        snap = _snapshot(ai_provider="OpenAI", model_id="gpt-3.5-turbo", accepts_files=True)
        card = build_public_card(snap, BASE_URL)
        assert not any(mode.startswith("image/") for mode in card.default_input_modes)

    def test_ac9_output_parser_adds_application_json_output_mode(self):
        snap = _snapshot(has_output_parser=True)
        card = build_public_card(snap, BASE_URL)
        assert "application/json" in card.default_output_modes

    def test_document_modes_added_only_when_accepts_files(self):
        snap = _snapshot(accepts_files=False)
        card = build_public_card(snap, BASE_URL)
        assert "application/pdf" not in card.default_input_modes
        assert "application/msword" not in card.default_input_modes

        snap_accepts = _snapshot(accepts_files=True)
        card_accepts = build_public_card(snap_accepts, BASE_URL)
        assert "application/pdf" in card_accepts.default_input_modes
        assert "application/msword" in card_accepts.default_input_modes

    def test_file_producing_agent_adds_octet_stream_output_mode(self):
        snap = _snapshot(can_produce_files=True)
        card = build_public_card(snap, BASE_URL)
        assert "application/octet-stream" in card.default_output_modes

    def test_base_input_output_modes_always_present(self):
        snap = _snapshot(accepts_files=False, has_output_parser=False, can_produce_files=False)
        card = build_public_card(snap, BASE_URL)
        assert "text/plain" in card.default_input_modes
        assert "application/json" in card.default_input_modes
        assert card.default_output_modes == ["text/plain"]


class TestBuildExtendedCard:
    def test_extended_card_for_agent_contains_its_own_examples_only(self):
        snap9 = _snapshot(agent_id=9, examples=("agent nine example",))
        card9 = build_extended_card(snap9, BASE_URL)
        assert list(card9.skills[0].examples) == ["agent nine example"]

        snap5 = _snapshot(agent_id=5, examples=("agent five example",))
        card5 = build_extended_card(snap5, BASE_URL)
        assert list(card5.skills[0].examples) == ["agent five example"]
        assert "agent nine example" not in json.dumps(card_to_json(card5))

    def test_extended_card_description_mentions_capabilities(self):
        snap = _snapshot(accepts_files=True, has_output_parser=True, has_memory=True)
        card = build_extended_card(snap, BASE_URL)
        assert "Accepts files: yes" in card.description
        assert "Structured output: yes" in card.description
        assert "Memory: yes" in card.description

    def test_extended_card_never_exposes_system_prompt_or_silo(self):
        snap = _snapshot(skills=((1, "Billing", "Handles billing"),), examples=("one example",))
        card = build_extended_card(snap, BASE_URL)
        serialized = json.dumps(card_to_json(card))
        for leaked in ("SECRET-PROMPT", "silo", "mcp"):
            assert leaked not in serialized


class TestCatalogEntry:
    def test_catalog_entry_has_absolute_urls(self):
        snap = _snapshot()
        entry = catalog_entry(snap, BASE_URL)
        assert entry["agent_id"] == 9
        assert entry["name"] == "Support Bot"
        assert entry["card_url"] == f"{BASE_URL}/a2a/v1/apps/acme/agents/9/.well-known/agent-card.json"
        assert entry["rpc_url"] == f"{BASE_URL}/a2a/v1/apps/acme/agents/9"


def _real_shaped_agent(**overrides) -> SimpleNamespace:
    """An `Agent`-shaped object carrying every secret/internal-id field a real
    row would have (`system_prompt`, `silo`, `mcp_associations`, the AIService's
    provider/model id) -- the AC-2 leak test (review round 2, MEDIUM-2) proves
    none of it survives `build_snapshot` -> `build_public_card`/
    `build_extended_card` -> `card_to_json`, not just that the card builder
    itself ignores fields it was never given.
    """
    skill = SimpleNamespace(name="Billing", description="Handles billing")
    skill_assoc = SimpleNamespace(skill_id=1, skill=skill, description="")
    defaults = dict(
        agent_id=9,
        app_id=1,
        app=SimpleNamespace(slug="acme", is_frozen=False, max_file_size_mb=0, name="Acme", agent_cors_origins=None),
        name="Support Bot",
        description="Public facing description",
        system_prompt="SECRET-PROMPT",
        silo=SimpleNamespace(name="SILO-NAME-X"),
        silo_id=42,
        mcp_associations=[SimpleNamespace(mcp=SimpleNamespace(name="MCP-NAME-X"))],
        is_frozen=False,
        a2a_enabled=True,
        a2a_card_visibility="public",
        a2a_name_override=None,
        a2a_description_override=None,
        a2a_skill_tags=["finance"],
        a2a_examples=["example one", "example two"],
        skill_associations=[skill_assoc],
        server_tools=[],
        enable_code_interpreter=False,
        output_parser_id=None,
        ai_service=SimpleNamespace(provider="PROVIDER-X", description="MODEL-ID-X"),
        has_memory=False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestRealShapedAgentLeakTest:
    """AC-2, through the full `build_snapshot` -> card pipeline (review round 2, MEDIUM-2)."""

    _LEAKED_MARKERS = ("SECRET-PROMPT", "SILO-NAME-X", "MCP-NAME-X", "MODEL-ID-X", "PROVIDER-X")

    def test_public_card_never_leaks_prompt_silo_mcp_model_or_provider(self):
        agent = _real_shaped_agent()
        snap = build_snapshot(agent)
        card = build_public_card(snap, BASE_URL)
        serialized = json.dumps(card_to_json(card))

        for marker in self._LEAKED_MARKERS:
            assert marker not in serialized
        assert "example one" not in serialized
        assert "example two" not in serialized

    def test_extended_card_adds_only_examples_and_a_capability_summary(self):
        agent = _real_shaped_agent()
        snap = build_snapshot(agent)
        card = build_extended_card(snap, BASE_URL)
        serialized = json.dumps(card_to_json(card))

        for marker in self._LEAKED_MARKERS:
            assert marker not in serialized
        assert "example one" in serialized
        assert "example two" in serialized
