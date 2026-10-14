"""Unit tests for the A2A import-field helper (step_010, FR-24, AC-39).

``_a2a_import_fields`` is the single place that decides what happens to the
A2A fields on import. Both the ``Agent``/``OCRAgent`` constructor paths and
the ``OVERRIDE`` conflict-mode update path in ``AgentImportService`` call it,
so these tests pin its contract directly rather than only indirectly through
a full DB round trip.
"""

from schemas.export_schemas import ExportAgentSchema
from services.agent_import_service import _a2a_import_fields


def test_a2a_import_fields_forces_disabled_even_when_source_was_enabled():
    """a2a_enabled must always come back False, regardless of the file."""
    agent_schema = ExportAgentSchema(
        name="Agent",
        a2a_enabled=True,
        a2a_card_visibility="api_key",
        a2a_name_override="Public Name",
        a2a_description_override="Public description",
        a2a_skill_tags=["billing", "support"],
        a2a_examples=["How do I pay my invoice?"],
    )

    fields = _a2a_import_fields(agent_schema)

    assert fields == {
        "a2a_enabled": False,
        "a2a_card_visibility": "api_key",
        "a2a_name_override": "Public Name",
        "a2a_description_override": "Public description",
        "a2a_skill_tags": ["billing", "support"],
        "a2a_examples": ["How do I pay my invoice?"],
    }


def test_a2a_import_fields_defaults_from_legacy_schema():
    """A schema built with no A2A keys (legacy export) still yields a
    complete, safe field dict instead of raising or returning None."""
    agent_schema = ExportAgentSchema(name="Legacy Agent")

    fields = _a2a_import_fields(agent_schema)

    assert fields == {
        "a2a_enabled": False,
        "a2a_card_visibility": "public",
        "a2a_name_override": None,
        "a2a_description_override": None,
        "a2a_skill_tags": [],
        "a2a_examples": [],
    }


def test_a2a_import_fields_always_returns_a_fresh_list():
    """Tags/examples are copied into a new list, never the schema's own list
    object, so later in-place mutation on the Agent side can't alias back."""
    agent_schema = ExportAgentSchema(
        name="Agent", a2a_skill_tags=["billing"], a2a_examples=["example"]
    )

    fields = _a2a_import_fields(agent_schema)

    assert fields["a2a_skill_tags"] is not agent_schema.a2a_skill_tags
    assert fields["a2a_examples"] is not agent_schema.a2a_examples
