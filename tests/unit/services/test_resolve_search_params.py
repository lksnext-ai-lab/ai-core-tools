"""Unit tests for ``services.silo_service.resolve_search_params``.

No database is touched; all silo/agent objects are SimpleNamespace stubs.

Acceptance criteria exercised:
- AC-12: legacy agent (rag_k=30, rag_search_type='similarity', rag_fixed_filters=None)
  yields exactly k=30/similarity and empty pinned filter — zero regression.
- AC-13: AND-merge of caller flat filter + agent rag_fixed_filters produces the
  expected backend dict; the agent's fixed filter wins on conflict (scoping floor).
- caller > agent precedence for k, search_type, score_threshold.
- agent > system defaults when caller omits.
- agent.silo is None → returns tuning dict + empty {}.
- fetch_k / lambda_mult pass-through from caller only.
"""

from __future__ import annotations

import types
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_metadata_def(fields: list[dict]) -> Any:
    """Build a SimpleNamespace with a .fields list, like silo.metadata_definition."""
    return types.SimpleNamespace(fields=list(fields))


def _make_silo(
    silo_id: int = 1,
    vector_db_type: str = "PGVECTOR",
    metadata_fields: list[dict] | None = None,
) -> Any:
    silo = types.SimpleNamespace(
        silo_id=silo_id,
        vector_db_type=vector_db_type,
        metadata_definition=_make_metadata_def(metadata_fields) if metadata_fields else None,
    )
    return silo


def _make_agent(
    rag_k: int = 30,
    rag_search_type: str = "similarity",
    rag_score_threshold: float | None = None,
    rag_fixed_filters: list | None = None,
    rag_max_retrieval_calls: int | None = None,
    silo: Any = None,
) -> Any:
    return types.SimpleNamespace(
        rag_k=rag_k,
        rag_search_type=rag_search_type,
        rag_score_threshold=rag_score_threshold,
        rag_fixed_filters=rag_fixed_filters,
        rag_max_retrieval_calls=rag_max_retrieval_calls,
        silo=silo,
    )


# ---------------------------------------------------------------------------
# Import under test
# ---------------------------------------------------------------------------

from services.silo_service import resolve_search_params  # noqa: E402


# ---------------------------------------------------------------------------
# AC-12 — legacy agent: zero regression
# ---------------------------------------------------------------------------

class TestLegacyAgent:
    def test_legacy_agent_yields_k30_similarity_empty_filter(self):
        """A legacy agent (server_default values, no filters, caller omits everything)
        must return k=30, search_type='similarity', and an empty pinned filter."""
        silo = _make_silo(metadata_fields=None)
        agent = _make_agent(rag_k=30, rag_search_type="similarity", silo=silo)

        sp, pf = resolve_search_params(agent, None)

        assert sp["k"] == 30
        assert sp["search_type"] == "similarity"
        assert "score_threshold" not in sp
        assert pf == {}

    def test_legacy_agent_empty_caller_same_as_none(self):
        """Empty caller dict behaves identically to None."""
        silo = _make_silo()
        agent = _make_agent(rag_k=30, rag_search_type="similarity", silo=silo)

        sp_none, pf_none = resolve_search_params(agent, None)
        sp_empty, pf_empty = resolve_search_params(agent, {})

        assert sp_none == sp_empty
        assert pf_none == pf_empty == {}


# ---------------------------------------------------------------------------
# Caller > agent precedence
# ---------------------------------------------------------------------------

class TestCallerPrecedence:
    def test_caller_k_overrides_agent_k(self):
        silo = _make_silo()
        agent = _make_agent(rag_k=30, silo=silo)

        sp, _ = resolve_search_params(agent, {"k": 5})

        assert sp["k"] == 5

    def test_caller_search_type_overrides_agent_search_type(self):
        silo = _make_silo()
        agent = _make_agent(rag_search_type="similarity", silo=silo)

        sp, _ = resolve_search_params(agent, {"search_type": "mmr"})

        assert sp["search_type"] == "mmr"

    def test_caller_score_threshold_overrides_agent(self):
        silo = _make_silo()
        agent = _make_agent(rag_score_threshold=0.7, silo=silo)

        sp, _ = resolve_search_params(agent, {"score_threshold": 0.4})

        assert sp["score_threshold"] == pytest.approx(0.4)

    def test_caller_score_threshold_none_clears_agent_value(self):
        """Explicit None in caller for score_threshold clears the agent's value and
        leaves no residual key (never forwarded as score_threshold=None to as_retriever)."""
        silo = _make_silo()
        agent = _make_agent(rag_score_threshold=0.7, silo=silo)

        sp, _ = resolve_search_params(agent, {"score_threshold": None})

        assert "score_threshold" not in sp


# ---------------------------------------------------------------------------
# Agent > system defaults when caller omits
# ---------------------------------------------------------------------------

class TestAgentFallback:
    def test_agent_k_used_when_caller_omits_k(self):
        silo = _make_silo()
        agent = _make_agent(rag_k=15, silo=silo)

        sp, _ = resolve_search_params(agent, {})

        assert sp["k"] == 15

    def test_agent_search_type_used_when_caller_omits(self):
        silo = _make_silo()
        agent = _make_agent(rag_search_type="mmr", silo=silo)

        sp, _ = resolve_search_params(agent, {})

        assert sp["search_type"] == "mmr"

    def test_agent_score_threshold_included_when_set_and_caller_omits(self):
        silo = _make_silo()
        agent = _make_agent(rag_score_threshold=0.8, silo=silo)

        sp, _ = resolve_search_params(agent, {})

        assert sp.get("score_threshold") == pytest.approx(0.8)

    def test_score_threshold_absent_when_neither_caller_nor_agent_sets_it(self):
        silo = _make_silo()
        agent = _make_agent(rag_score_threshold=None, silo=silo)

        sp, _ = resolve_search_params(agent, {})

        assert "score_threshold" not in sp


class TestThresholdFallback:
    def test_threshold_search_without_value_downgrades_to_similarity(self):
        """A threshold search with no threshold would silently no-op; the resolver
        normalizes it to plain similarity instead."""
        silo = _make_silo()
        agent = _make_agent(
            rag_search_type="similarity_score_threshold",
            rag_score_threshold=None,
            silo=silo,
        )

        sp, _ = resolve_search_params(agent, {})

        assert sp["search_type"] == "similarity"
        assert "score_threshold" not in sp

    def test_threshold_search_kept_when_value_present(self):
        silo = _make_silo()
        agent = _make_agent(
            rag_search_type="similarity_score_threshold",
            rag_score_threshold=0.6,
            silo=silo,
        )

        sp, _ = resolve_search_params(agent, {})

        assert sp["search_type"] == "similarity_score_threshold"
        assert sp["score_threshold"] == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# fetch_k / lambda_mult — caller pass-through only
# ---------------------------------------------------------------------------

class TestPassthroughParams:
    def test_fetch_k_included_when_caller_supplies_it(self):
        silo = _make_silo()
        agent = _make_agent(silo=silo)

        sp, _ = resolve_search_params(agent, {"fetch_k": 100})

        assert sp["fetch_k"] == 100

    def test_fetch_k_absent_when_caller_omits_it(self):
        silo = _make_silo()
        agent = _make_agent(silo=silo)

        sp, _ = resolve_search_params(agent, {})

        assert "fetch_k" not in sp

    def test_lambda_mult_included_when_caller_supplies_it(self):
        silo = _make_silo()
        agent = _make_agent(silo=silo)

        sp, _ = resolve_search_params(agent, {"lambda_mult": 0.5})

        assert sp["lambda_mult"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# agent.silo is None
# ---------------------------------------------------------------------------

class TestNoSilo:
    def test_returns_tuning_dict_and_empty_filter_when_silo_is_none(self):
        agent = _make_agent(rag_k=10, rag_search_type="similarity", silo=None)

        sp, pf = resolve_search_params(agent, None)

        assert sp["k"] == 10
        assert sp["search_type"] == "similarity"
        assert pf == {}


# ---------------------------------------------------------------------------
# AC-13 — AND-merge of caller flat filter + agent rag_fixed_filters
# ---------------------------------------------------------------------------

class TestFilterMerge:
    def test_caller_flat_filter_converted_to_backend_dict(self):
        """A caller flat {field: value} dict is converted to {field: {$eq: value}}."""
        silo = _make_silo(
            metadata_fields=[{"name": "year", "description": "Year", "type": "int"}]
        )
        agent = _make_agent(rag_fixed_filters=None, silo=silo)

        _, pf = resolve_search_params(agent, {"filter": {"year": 2024}})

        assert "year" in pf
        assert pf["year"] == {"$eq": 2024}

    def test_agent_fixed_filters_converted_to_backend_dict(self):
        """Agent rag_fixed_filters list is converted to a backend filter dict."""
        silo = _make_silo(
            metadata_fields=[{"name": "region", "description": "Region", "type": "str"}]
        )
        agent = _make_agent(
            rag_fixed_filters=[{"field": "region", "op": "$eq", "value": "north"}],
            silo=silo,
        )

        _, pf = resolve_search_params(agent, None)

        assert "region" in pf
        assert pf["region"] == {"$eq": "north"}

    def test_agent_fixed_filter_wins_on_conflict(self):
        """Security: when caller and agent constrain the same (field, op), the
        agent's fixed filter wins — a caller cannot loosen an admin scoping floor."""
        silo = _make_silo(
            metadata_fields=[{"name": "status", "description": "Status", "type": "str"}]
        )
        agent = _make_agent(
            rag_fixed_filters=[{"field": "status", "op": "$eq", "value": "draft"}],
            silo=silo,
        )

        _, pf = resolve_search_params(agent, {"filter": {"status": "published"}})

        assert pf["status"]["$eq"] == "draft"

    def test_different_fields_merged_from_both_sources(self):
        """Fields from caller and agent that do not conflict both appear in pinned filter."""
        silo = _make_silo(
            metadata_fields=[
                {"name": "region", "description": "Region", "type": "str"},
                {"name": "year", "description": "Year", "type": "int"},
            ]
        )
        agent = _make_agent(
            rag_fixed_filters=[{"field": "region", "op": "$eq", "value": "north"}],
            silo=silo,
        )

        _, pf = resolve_search_params(agent, {"filter": {"year": 2023}})

        assert "region" in pf
        assert "year" in pf
        assert pf["region"]["$eq"] == "north"
        assert pf["year"]["$eq"] == 2023

    def test_both_sources_empty_yields_empty_filter(self):
        silo = _make_silo()
        agent = _make_agent(rag_fixed_filters=None, silo=silo)

        _, pf = resolve_search_params(agent, {})

        assert pf == {}

    def test_system_field_allowed_in_agent_filters(self):
        """'page', 'name', 'url', 'file_type' are always valid filter fields."""
        silo = _make_silo(metadata_fields=None)  # no user-declared fields
        agent = _make_agent(
            rag_fixed_filters=[{"field": "file_type", "op": "$eq", "value": ".pdf"}],
            silo=silo,
        )

        _, pf = resolve_search_params(agent, None)

        assert "file_type" in pf
        assert pf["file_type"]["$eq"] == ".pdf"
