"""Unit tests for RAG field validators in agent schemas (step_008).

Validates:
- rag_k: out-of-range raises ValidationError; valid values pass.
- rag_search_type: invalid value raises; valid values pass.
- rag_score_threshold: out-of-range raises; valid values pass.
- rag_max_retrieval_calls: out-of-range raises; valid values pass.
- rag_fixed_filters: malformed element raises; valid list passes.
- None values always pass (all fields are Optional).

Applied to all three write schemas:
  CreateUpdateAgentSchema (internal)
  CreateAgentRequestSchema (public create)
  UpdateAgentRequestSchema (public update)
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUIRED_CREATE_UPDATE = {
    "name": "test",
}

_REQUIRED_CREATE_PUBLIC = {
    "name": "test",
}

_REQUIRED_UPDATE_PUBLIC: dict = {}  # all fields Optional


def _cu(**kwargs):
    """Build CreateUpdateAgentSchema (internal)."""
    from schemas.agent_schemas import CreateUpdateAgentSchema
    return CreateUpdateAgentSchema(**{**_REQUIRED_CREATE_UPDATE, **kwargs})


def _create(**kwargs):
    """Build CreateAgentRequestSchema (public)."""
    from schemas.agent_schemas import CreateAgentRequestSchema
    return CreateAgentRequestSchema(**{**_REQUIRED_CREATE_PUBLIC, **kwargs})


def _update(**kwargs):
    """Build UpdateAgentRequestSchema (public)."""
    from schemas.agent_schemas import UpdateAgentRequestSchema
    return UpdateAgentRequestSchema(**kwargs)


# ---------------------------------------------------------------------------
# rag_k
# ---------------------------------------------------------------------------

class TestRagK:
    @pytest.mark.parametrize("schema_fn", [_cu, _create, _update])
    def test_valid_rag_k_passes(self, schema_fn):
        schema_fn(rag_k=10)
        schema_fn(rag_k=1)
        schema_fn(rag_k=100)

    @pytest.mark.parametrize("schema_fn", [_cu, _create, _update])
    def test_none_rag_k_passes(self, schema_fn):
        schema_fn(rag_k=None)

    @pytest.mark.parametrize("schema_fn", [_cu, _create, _update])
    def test_rag_k_below_min_raises(self, schema_fn):
        with pytest.raises(ValidationError, match="rag_k"):
            schema_fn(rag_k=0)

    @pytest.mark.parametrize("schema_fn", [_cu, _create, _update])
    def test_rag_k_above_max_raises(self, schema_fn):
        with pytest.raises(ValidationError, match="rag_k"):
            schema_fn(rag_k=101)


# ---------------------------------------------------------------------------
# rag_search_type
# ---------------------------------------------------------------------------

class TestRagSearchType:
    @pytest.mark.parametrize("schema_fn", [_cu, _create, _update])
    @pytest.mark.parametrize("valid_type", ["similarity", "mmr", "similarity_score_threshold"])
    def test_valid_search_type_passes(self, schema_fn, valid_type):
        schema_fn(rag_search_type=valid_type)

    @pytest.mark.parametrize("schema_fn", [_cu, _create, _update])
    def test_none_search_type_passes(self, schema_fn):
        schema_fn(rag_search_type=None)

    @pytest.mark.parametrize("schema_fn", [_cu, _create, _update])
    def test_invalid_search_type_raises(self, schema_fn):
        with pytest.raises(ValidationError, match="rag_search_type"):
            schema_fn(rag_search_type="cosine")

    @pytest.mark.parametrize("schema_fn", [_cu, _create, _update])
    def test_empty_string_raises(self, schema_fn):
        with pytest.raises(ValidationError, match="rag_search_type"):
            schema_fn(rag_search_type="")


# ---------------------------------------------------------------------------
# rag_score_threshold
# ---------------------------------------------------------------------------

class TestRagScoreThreshold:
    @pytest.mark.parametrize("schema_fn", [_cu, _create, _update])
    def test_valid_threshold_passes(self, schema_fn):
        schema_fn(rag_score_threshold=0.0)
        schema_fn(rag_score_threshold=0.5)
        schema_fn(rag_score_threshold=1.0)

    @pytest.mark.parametrize("schema_fn", [_cu, _create, _update])
    def test_none_passes(self, schema_fn):
        schema_fn(rag_score_threshold=None)

    @pytest.mark.parametrize("schema_fn", [_cu, _create, _update])
    def test_below_zero_raises(self, schema_fn):
        with pytest.raises(ValidationError, match="rag_score_threshold"):
            schema_fn(rag_score_threshold=-0.01)

    @pytest.mark.parametrize("schema_fn", [_cu, _create, _update])
    def test_above_one_raises(self, schema_fn):
        with pytest.raises(ValidationError, match="rag_score_threshold"):
            schema_fn(rag_score_threshold=1.01)


# ---------------------------------------------------------------------------
# rag_max_retrieval_calls
# ---------------------------------------------------------------------------

class TestRagMaxRetrievalCalls:
    @pytest.mark.parametrize("schema_fn", [_cu, _create, _update])
    def test_valid_max_retrieval_calls_passes(self, schema_fn):
        schema_fn(rag_max_retrieval_calls=1)
        schema_fn(rag_max_retrieval_calls=10)
        schema_fn(rag_max_retrieval_calls=20)

    @pytest.mark.parametrize("schema_fn", [_cu, _create, _update])
    def test_none_passes(self, schema_fn):
        schema_fn(rag_max_retrieval_calls=None)

    @pytest.mark.parametrize("schema_fn", [_cu, _create, _update])
    def test_zero_raises(self, schema_fn):
        with pytest.raises(ValidationError, match="rag_max_retrieval_calls"):
            schema_fn(rag_max_retrieval_calls=0)

    @pytest.mark.parametrize("schema_fn", [_cu, _create, _update])
    def test_above_max_raises(self, schema_fn):
        with pytest.raises(ValidationError, match="rag_max_retrieval_calls"):
            schema_fn(rag_max_retrieval_calls=21)


# ---------------------------------------------------------------------------
# rag_fixed_filters
# ---------------------------------------------------------------------------

class TestRagFixedFilters:
    @pytest.mark.parametrize("schema_fn", [_cu, _create, _update])
    def test_none_passes(self, schema_fn):
        schema_fn(rag_fixed_filters=None)

    @pytest.mark.parametrize("schema_fn", [_cu, _create, _update])
    def test_empty_list_passes(self, schema_fn):
        obj = schema_fn(rag_fixed_filters=[])
        assert obj.rag_fixed_filters == []

    @pytest.mark.parametrize("schema_fn", [_cu, _create, _update])
    def test_valid_filter_passes(self, schema_fn):
        valid = [{"field": "status", "op": "$eq", "value": "active"}]
        obj = schema_fn(rag_fixed_filters=valid)
        assert obj.rag_fixed_filters is not None
        assert len(obj.rag_fixed_filters) == 1
        assert obj.rag_fixed_filters[0]["field"] == "status"

    @pytest.mark.parametrize("schema_fn", [_cu, _create, _update])
    def test_valid_in_operator_passes(self, schema_fn):
        valid = [{"field": "year", "op": "$in", "value": [2022, 2023]}]
        obj = schema_fn(rag_fixed_filters=valid)
        assert obj.rag_fixed_filters is not None

    @pytest.mark.parametrize("schema_fn", [_cu, _create, _update])
    def test_empty_field_raises(self, schema_fn):
        bad = [{"field": "", "op": "$eq", "value": "x"}]
        with pytest.raises(ValidationError):
            schema_fn(rag_fixed_filters=bad)

    @pytest.mark.parametrize("schema_fn", [_cu, _create, _update])
    def test_unknown_op_raises(self, schema_fn):
        bad = [{"field": "status", "op": "$regex", "value": ".*"}]
        with pytest.raises(ValidationError):
            schema_fn(rag_fixed_filters=bad)

    @pytest.mark.parametrize("schema_fn", [_cu, _create, _update])
    def test_missing_field_key_raises(self, schema_fn):
        bad = [{"op": "$eq", "value": "x"}]  # no 'field'
        with pytest.raises((ValidationError, TypeError)):
            schema_fn(rag_fixed_filters=bad)

    @pytest.mark.parametrize("schema_fn", [_cu, _create, _update])
    def test_multiple_valid_filters_pass(self, schema_fn):
        filters = [
            {"field": "region", "op": "$eq", "value": "north"},
            {"field": "year", "op": "$gte", "value": 2020},
        ]
        obj = schema_fn(rag_fixed_filters=filters)
        assert len(obj.rag_fixed_filters) == 2


# ---------------------------------------------------------------------------
# RuntimeSearchParamsSchema — DoS guard for caller-supplied search params
# ---------------------------------------------------------------------------

class TestRuntimeSearchParams:
    def _schema(self):
        from schemas.agent_schemas import RuntimeSearchParamsSchema
        return RuntimeSearchParamsSchema

    def test_valid_params_pass(self):
        self._schema()(k=20, search_type="mmr", score_threshold=0.5, fetch_k=50, lambda_mult=0.3)

    def test_empty_passes(self):
        self._schema()()

    def test_filter_passthrough_accepted(self):
        obj = self._schema()(filter={"region": "north"})
        assert obj.filter == {"region": "north"}

    @pytest.mark.parametrize("k", [0, 101, 100000])
    def test_out_of_range_k_raises(self, k):
        with pytest.raises(ValidationError):
            self._schema()(k=k)

    @pytest.mark.parametrize("fetch_k", [0, 101])
    def test_out_of_range_fetch_k_raises(self, fetch_k):
        with pytest.raises(ValidationError):
            self._schema()(fetch_k=fetch_k)

    def test_invalid_search_type_raises(self):
        with pytest.raises(ValidationError):
            self._schema()(search_type="bogus")

    @pytest.mark.parametrize("value", [-0.1, 1.1])
    def test_out_of_range_score_threshold_raises(self, value):
        with pytest.raises(ValidationError):
            self._schema()(score_threshold=value)
