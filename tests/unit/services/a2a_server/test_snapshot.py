"""Unit coverage for `services.a2a_server.snapshot.build_snapshot` (step_011, review round 2).

No DB: builds `Agent`-shaped `SimpleNamespace` objects mimicking exactly what
`repositories.a2a_agent_repository`'s eager-loaded query returns.
"""

from __future__ import annotations

from types import SimpleNamespace

from services.a2a_server.snapshot import build_snapshot


def _skill_assoc(*, skill_id=1, name="Billing", description="", assoc_description=""):
    skill = SimpleNamespace(name=name, description=description)
    return SimpleNamespace(skill_id=skill_id, skill=skill, description=assoc_description)


def _agent(**overrides):
    defaults = dict(
        agent_id=9,
        app_id=1,
        app=SimpleNamespace(slug="acme", is_frozen=False, max_file_size_mb=0, name="Acme"),
        name="Support Bot",
        description="Public description",
        is_frozen=False,
        a2a_enabled=True,
        a2a_card_visibility="public",
        a2a_name_override=None,
        a2a_description_override=None,
        a2a_skill_tags=[],
        a2a_examples=[],
        skill_associations=[],
        server_tools=[],
        enable_code_interpreter=False,
        output_parser_id=None,
        ai_service=None,
        has_memory=False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestFailClosedVisibility:
    def test_public_stays_public(self):
        snap = build_snapshot(_agent(a2a_card_visibility="public"))
        assert snap.visibility == "public"

    def test_api_key_stays_api_key(self):
        snap = build_snapshot(_agent(a2a_card_visibility="api_key"))
        assert snap.visibility == "api_key"

    def test_unexpected_value_fails_closed_to_api_key(self):
        # LOW-3: anything that isn't the exact string "public" must resolve to
        # the stricter "api_key", never silently default to "public".
        snap = build_snapshot(_agent(a2a_card_visibility="something-unexpected"))
        assert snap.visibility == "api_key"

    def test_none_fails_closed_to_api_key(self):
        snap = build_snapshot(_agent(a2a_card_visibility=None))
        assert snap.visibility == "api_key"

    def test_empty_string_fails_closed_to_api_key(self):
        snap = build_snapshot(_agent(a2a_card_visibility=""))
        assert snap.visibility == "api_key"


class TestTextSanitizationAndCaps:
    def test_control_characters_are_stripped_from_name_and_description(self):
        agent = _agent(name="Sup\x00port\x07 Bot", description="Public\x0cdescription")
        snap = build_snapshot(agent)
        assert "\x00" not in snap.agent_name
        assert "\x07" not in snap.agent_name
        assert "\x0c" not in snap.agent_description
        assert snap.agent_name == "Support Bot"

    def test_name_is_capped_at_255_characters(self):
        agent = _agent(name="x" * 500)
        snap = build_snapshot(agent)
        assert len(snap.agent_name) == 255

    def test_description_is_capped_at_1000_characters(self):
        agent = _agent(description="y" * 2000)
        snap = build_snapshot(agent)
        assert len(snap.agent_description) == 1000

    def test_description_allows_newlines_and_tabs(self):
        agent = _agent(description="line one\nline two\tindented")
        snap = build_snapshot(agent)
        assert snap.agent_description == "line one\nline two\tindented"

    def test_name_does_not_allow_newlines(self):
        agent = _agent(name="line one\nline two")
        snap = build_snapshot(agent)
        assert "\n" not in snap.agent_name

    def test_skill_name_and_description_are_sanitized_and_capped(self):
        assoc = _skill_assoc(
            name="Billing\x00Skill" + "z" * 300,
            assoc_description="assoc\x07desc" + "w" * 1200,
        )
        agent = _agent(skill_associations=[assoc])
        snap = build_snapshot(agent)
        skill_id, name, description = snap.skills[0]
        assert "\x00" not in name
        assert len(name) <= 255
        assert "\x07" not in description
        assert len(description) <= 1000

    def test_skill_description_falls_back_and_is_still_sanitized(self):
        assoc = _skill_assoc(description="skill own desc\x00here", assoc_description="")
        agent = _agent(skill_associations=[assoc])
        snap = build_snapshot(agent)
        _, _, description = snap.skills[0]
        assert "\x00" not in description
        assert description == "skill own deschere"

    def test_none_name_and_description_become_empty_strings(self):
        agent = _agent(name=None, description=None)
        snap = build_snapshot(agent)
        assert snap.agent_name == ""
        assert snap.agent_description == ""


class TestSnapshotRequiredAttributesForInputService:
    """`input_service.py`'s `_AgentSnapshotLike` Protocol only needs these three."""

    def test_exposes_agent_id_app_max_file_size_mb_has_memory(self):
        agent = _agent(
            agent_id=42,
            app=SimpleNamespace(slug="acme", is_frozen=False, max_file_size_mb=25, name="Acme"),
            has_memory=True,
        )
        snap = build_snapshot(agent)
        assert snap.agent_id == 42
        assert snap.app_max_file_size_mb == 25
        assert snap.has_memory is True
