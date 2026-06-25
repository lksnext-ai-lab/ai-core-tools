"""Integration tests for ``get_retriever_tool``.

These tests require:
  - The test database running on port 5433 (``docker compose --profile test up -d db_test``).
  - A PGVector-enabled test silo with seeded documents.

Run via:
    pytest tests/integration/tools/test_retriever_tool_integration.py -v -m integration

The tests are *not* intended to be executed in CI without the test DB.
On Windows without the test DB, they are automatically skipped.

Coverage:
  - AC-9  : AND of caller (pinned) + LLM-inferred filter queries only documents
             matching both constraints.
  - AC-7  : The collection queried is always ``silo_{silo_id}`` regardless of
             any filter value trying to reference a different collection.
"""

from __future__ import annotations

import os
import pytest
from typing import List
from unittest.mock import MagicMock, patch


# Skip the entire module unless the integration test database is reachable.
# The conftest.py sets SQLALCHEMY_DATABASE_URI to the test DB; if it is not
# available the test DB fixtures will fail, so we skip gracefully.
pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_metadata_def(fields: list[dict]) -> MagicMock:
    md = MagicMock()
    md.fields = fields
    return md


def _make_silo_mock(
    silo_id: int,
    name: str = "Integration Test Silo",
    vector_db_type: str = "PGVECTOR",
    metadata_def_fields: list[dict] | None = None,
) -> MagicMock:
    silo = MagicMock()
    silo.silo_id = silo_id
    silo.name = name
    silo.description = "Integration test silo description"
    silo.silo_type = "REPO"
    silo.vector_db_type = vector_db_type
    if metadata_def_fields is None:
        silo.metadata_definition = None
    else:
        silo.metadata_definition = _make_metadata_def(metadata_def_fields)
    return silo


# ---------------------------------------------------------------------------
# AC-9 — AND of caller + LLM filter in PGVector with seeded documents
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAndFilterIntegration:
    """Verify that caller (pinned) and LLM-inferred filters are ANDed together.

    To run these tests you need a silo seeded with documents that have
    metadata fields ``doc_type`` and ``anio``.  Seed the test collection
    ``silo_9001`` with at least:
      - doc A: {doc_type: "informe", anio: 2023}
      - doc B: {doc_type: "acta",    anio: 2023}
      - doc C: {doc_type: "informe", anio: 2022}

    Expectations:
      - Pinned filter ``doc_type=informe`` + LLM filter ``anio=2023``
        → only doc A.
      - Pinned filter ``doc_type=informe`` alone → docs A + C.
    """

    _SILO_ID = 9001

    @pytest.mark.asyncio
    async def test_ac9_and_pinned_plus_llm_narrows_results(self, db):
        """With caller AND LLM filters applied, only matching docs are returned."""
        from tools.agentTools import get_retriever_tool

        silo = _make_silo_mock(
            silo_id=self._SILO_ID,
            metadata_def_fields=[
                {"name": "doc_type", "description": "Document type", "type": "str"},
                {"name": "anio", "description": "Year", "type": "int"},
            ],
        )

        tool = get_retriever_tool(
            silo=silo,
            search_params={"filter": {"doc_type": "informe"}, "k": 10},
        )
        assert tool is not None

        content, artifact = await tool.coroutine(query="annual report", anio=2023)

        # Content must echo the merged filter.
        assert "doc_type" in content or "anio" in content
        # Guard against vacuous pass: at least one document must be returned.
        assert len(artifact) > 0
        # All returned documents must satisfy BOTH constraints.
        for doc in artifact:
            assert doc.metadata.get("doc_type") == "informe", (
                f"Unexpected doc_type in result: {doc.metadata}"
            )
            assert doc.metadata.get("anio") == 2023, (
                f"Unexpected anio in result: {doc.metadata}"
            )


# AC-7 (collection isolation) is covered by a unit test:
# tests/unit/tools/test_get_retriever_tool.py::TestCollectionIsolation
