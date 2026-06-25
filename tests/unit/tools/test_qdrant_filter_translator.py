"""Unit tests for QdrantStore._translate_pgvector_filter_to_qdrant.

Covers the $in → MatchAny translation and regression guards for pre-existing
operators. All tests are pure-Python — no Qdrant server, no I/O.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest


TRANSLATOR_LOGGER = "tools.vector_stores.qdrant_store"


def _make_store():
    with patch("qdrant_client.QdrantClient"), patch("langchain_qdrant.QdrantVectorStore"):
        from tools.vector_stores.qdrant_store import QdrantStore

        store = QdrantStore.__new__(QdrantStore)
        store.url = "http://localhost:6333"
        store.api_key = None
        store.prefer_grpc = False
        store._QdrantVectorStore = MagicMock()
        store.client = MagicMock()
        return store


class TestTranslatePGVectorFilterToQdrant:

    def setup_method(self):
        self.store = _make_store()

    def test_in_produces_must_with_match_any(self):
        """$in translates to a must clause with match.any."""
        result = self.store._translate_pgvector_filter_to_qdrant(
            {"campo": {"$in": ["a", "b"]}}
        )
        assert "must" in result
        assert len(result["must"]) == 1
        condition = result["must"][0]
        assert condition["key"] == "metadata.campo"
        assert condition["match"] == {"any": ["a", "b"]}

    def test_in_empty_list_discards_condition_with_warning(self, caplog):
        """Empty $in list must be discarded and a WARNING logged."""
        with caplog.at_level(logging.WARNING, logger=TRANSLATOR_LOGGER):
            result = self.store._translate_pgvector_filter_to_qdrant(
                {"campo": {"$in": []}}
            )
        # No conditions should be emitted
        assert result.get("must", []) == []
        assert result.get("must_not", []) == []
        assert any("campo" in r.message for r in caplog.records)

    def test_in_combined_with_eq(self):
        """$in and $eq in the same filter are both translated."""
        result = self.store._translate_pgvector_filter_to_qdrant(
            {
                "category": {"$in": ["tech", "science"]},
                "active": {"$eq": True},
            }
        )
        assert "must" in result
        must = result["must"]

        # Locate each condition by key
        by_key = {c["key"]: c for c in must}
        assert "metadata.category" in by_key
        assert "metadata.active" in by_key

        assert by_key["metadata.category"]["match"] == {"any": ["tech", "science"]}
        assert by_key["metadata.active"]["match"] == {"value": True}

    def test_in_condition_goes_into_must_and_not_must_not(self):
        """$in is placed in must (not must_not)."""
        result = self.store._translate_pgvector_filter_to_qdrant(
            {"tag": {"$in": ["x"]}}
        )
        assert len(result.get("must", [])) == 1
        assert result.get("must_not", []) == []

    def test_in_non_list_value_discards_condition_with_warning(self, caplog):
        """$in with a non-list value must be discarded and a WARNING logged."""
        with caplog.at_level(logging.WARNING, logger=TRANSLATOR_LOGGER):
            result = self.store._translate_pgvector_filter_to_qdrant(
                {"campo": {"$in": "not_a_list"}}
            )
        assert result.get("must", []) == []
        assert result.get("must_not", []) == []
        assert any("campo" in r.message for r in caplog.records)

    def test_eq_still_produces_match_value(self):
        result = self.store._translate_pgvector_filter_to_qdrant(
            {"status": {"$eq": "published"}}
        )
        assert result["must"][0] == {
            "key": "metadata.status",
            "match": {"value": "published"},
        }

    def test_ne_produces_must_not_match_value(self):
        result = self.store._translate_pgvector_filter_to_qdrant(
            {"status": {"$ne": "draft"}}
        )
        assert result.get("must", []) == []
        assert result["must_not"][0] == {
            "key": "metadata.status",
            "match": {"value": "draft"},
        }

    def test_range_operator_gte_unaffected(self):
        result = self.store._translate_pgvector_filter_to_qdrant(
            {"year": {"$gte": 2020}}
        )
        assert result["must"][0] == {
            "key": "metadata.year",
            "range": {"gte": 2020},
        }

    def test_plain_equality_shorthand_unaffected(self):
        """{"field": value} shorthand without operator dict still works."""
        result = self.store._translate_pgvector_filter_to_qdrant({"type": "article"})
        assert result["must"][0] == {
            "key": "metadata.type",
            "match": {"value": "article"},
        }

    def test_unknown_operator_skipped_with_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger=TRANSLATOR_LOGGER):
            result = self.store._translate_pgvector_filter_to_qdrant(
                {"field": {"$regex": ".*"}}
            )
        assert result.get("must", []) == []
        assert any("$regex" in r.message for r in caplog.records)


class TestBuildQdrantFilterWithIn:

    def setup_method(self):
        self.store = _make_store()

    def test_in_filter_produces_filter_object_with_match_any(self):
        from qdrant_client.models import FieldCondition, Filter, MatchAny

        qdrant_filter = self.store._build_qdrant_filter(
            {"category": {"$in": ["news", "blog"]}}
        )

        assert isinstance(qdrant_filter, Filter)
        assert len(qdrant_filter.must) == 1

        condition = qdrant_filter.must[0]
        assert isinstance(condition, FieldCondition)
        assert condition.key == "metadata.category"
        assert isinstance(condition.match, MatchAny)
        assert set(condition.match.any) == {"news", "blog"}

    def test_empty_in_filter_returns_none(self, caplog):
        """An empty $in list must result in None and a WARNING."""
        with caplog.at_level(logging.WARNING, logger=TRANSLATOR_LOGGER):
            qdrant_filter = self.store._build_qdrant_filter(
                {"category": {"$in": []}}
            )
        assert qdrant_filter is None
        assert any("category" in r.message for r in caplog.records)


class TestSearchSimilarDocumentsFilterTranslation:
    """search_similar_documents translates filter dicts to models.Filter before calling the store."""

    def setup_method(self):
        self.store = _make_store()

    def _make_vector_store_mock(self):
        vs_mock = MagicMock()
        self.store._get_vector_store = MagicMock(return_value=vs_mock)
        return vs_mock

    def test_similarity_search_passes_filter_object_for_in(self):
        """similarity search branch: filter= receives a models.Filter, not a dict."""
        from qdrant_client.models import Filter

        vs_mock = self._make_vector_store_mock()
        vs_mock.similarity_search_with_score.return_value = []

        self.store.search_similar_documents(
            collection_name="test_col",
            query="hello",
            filter_metadata={"tag": {"$in": ["a", "b"]}},
            k=3,
            search_type="similarity",
        )

        call_kwargs = vs_mock.similarity_search_with_score.call_args
        passed_filter = call_kwargs.kwargs.get("filter") or call_kwargs.args[2] if call_kwargs.args and len(call_kwargs.args) > 2 else call_kwargs.kwargs.get("filter")
        assert isinstance(passed_filter, Filter), (
            f"Expected models.Filter, got {type(passed_filter)}"
        )

    def test_similarity_score_threshold_passes_filter_object(self):
        """similarity_score_threshold branch also receives a models.Filter."""
        from qdrant_client.models import Filter

        vs_mock = self._make_vector_store_mock()
        vs_mock.similarity_search_with_relevance_scores.return_value = []

        self.store.search_similar_documents(
            collection_name="test_col",
            query="hello",
            filter_metadata={"tag": {"$in": ["a", "b"]}},
            k=3,
            search_type="similarity_score_threshold",
            score_threshold=0.7,
        )

        call_kwargs = vs_mock.similarity_search_with_relevance_scores.call_args
        passed_filter = call_kwargs.kwargs.get("filter")
        assert isinstance(passed_filter, Filter), (
            f"Expected models.Filter, got {type(passed_filter)}"
        )

    def test_mmr_search_passes_filter_object(self):
        """MMR branch also receives a models.Filter."""
        from qdrant_client.models import Filter

        vs_mock = self._make_vector_store_mock()
        vs_mock.max_marginal_relevance_search.return_value = []

        self.store.search_similar_documents(
            collection_name="test_col",
            query="hello",
            filter_metadata={"tag": {"$in": ["a", "b"]}},
            k=3,
            search_type="mmr",
        )

        call_kwargs = vs_mock.max_marginal_relevance_search.call_args
        passed_filter = call_kwargs.kwargs.get("filter")
        assert isinstance(passed_filter, Filter), (
            f"Expected models.Filter, got {type(passed_filter)}"
        )

    def test_none_filter_passes_through_as_none(self):
        """When filter_metadata is None, None is forwarded (no crash)."""
        vs_mock = self._make_vector_store_mock()
        vs_mock.similarity_search_with_score.return_value = []

        self.store.search_similar_documents(
            collection_name="test_col",
            query="hello",
            filter_metadata=None,
            k=3,
        )

        call_kwargs = vs_mock.similarity_search_with_score.call_args
        passed_filter = call_kwargs.kwargs.get("filter")
        assert passed_filter is None


class TestGetRetrieverFilterTranslation:
    """get_retriever must translate a dict filter in search_params before as_retriever."""

    def setup_method(self):
        self.store = _make_store()

    def _make_vector_store_mock(self):
        vs_mock = MagicMock()
        self.store._get_vector_store = MagicMock(return_value=vs_mock)
        return vs_mock

    def test_retriever_translates_filter_dict_in_search_params(self):
        """as_retriever must receive search_kwargs with a models.Filter, not a raw dict."""
        from qdrant_client.models import Filter

        vs_mock = self._make_vector_store_mock()
        vs_mock.as_retriever.return_value = MagicMock()

        self.store.get_retriever(
            collection_name="test_col",
            search_params={"k": 4, "filter": {"tag": {"$in": ["x", "y"]}}},
        )

        call_kwargs = vs_mock.as_retriever.call_args
        search_kwargs = call_kwargs.kwargs.get("search_kwargs") or {}
        passed_filter = search_kwargs.get("filter")
        assert isinstance(passed_filter, Filter), (
            f"Expected models.Filter in search_kwargs['filter'], got {type(passed_filter)}"
        )

    def test_retriever_no_filter_in_search_params_passes_unchanged(self):
        """search_params without a filter key are forwarded as-is."""
        vs_mock = self._make_vector_store_mock()
        vs_mock.as_retriever.return_value = MagicMock()

        self.store.get_retriever(
            collection_name="test_col",
            search_params={"k": 5},
        )

        call_kwargs = vs_mock.as_retriever.call_args
        search_kwargs = call_kwargs.kwargs.get("search_kwargs") or {}
        assert search_kwargs.get("k") == 5
        assert "filter" not in search_kwargs

    def test_retriever_none_search_params_uses_default_as_retriever(self):
        """When search_params is None, as_retriever is called without search_kwargs."""
        vs_mock = self._make_vector_store_mock()
        vs_mock.as_retriever.return_value = MagicMock()

        self.store.get_retriever(collection_name="test_col", search_params=None)

        call_kwargs = vs_mock.as_retriever.call_args
        assert "search_kwargs" not in call_kwargs.kwargs
