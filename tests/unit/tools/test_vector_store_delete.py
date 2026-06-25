"""Unit tests for vector store delete_documents with metadata filters."""

from unittest.mock import MagicMock, call, patch

import pytest


class TestQdrantStoreDeleteByFilter:
    """QdrantStore.delete_documents with a metadata-filter dict."""

    def _make_store(self):
        with patch("qdrant_client.QdrantClient"), patch("langchain_qdrant.QdrantVectorStore"):
            from tools.vector_stores.qdrant_store import QdrantStore

            store = QdrantStore.__new__(QdrantStore)
            store.url = "http://localhost:6333"
            store.api_key = None
            store.prefer_grpc = False
            store._QdrantVectorStore = MagicMock()

            mock_client = MagicMock()
            store.client = mock_client

            return store, mock_client

    def test_delete_uses_filter_selector_not_scroll(self):
        """delete_documents calls client.delete with a FilterSelector, not scroll."""
        store, mock_client = self._make_store()

        pgvector_filter = {"resource_id": {"$eq": 42}}
        store.delete_documents("silo_1", ids=pgvector_filter)

        mock_client.scroll.assert_not_called()
        mock_client.delete.assert_called_once()
        call_kwargs = mock_client.delete.call_args
        assert call_kwargs.kwargs.get("collection_name") == "silo_1" or call_kwargs.args[0] == "silo_1"

        from qdrant_client.models import FilterSelector

        points_selector = (
            call_kwargs.kwargs.get("points_selector")
            or (call_kwargs.args[1] if len(call_kwargs.args) > 1 else None)
        )
        assert isinstance(points_selector, FilterSelector), (
            f"Expected FilterSelector, got {type(points_selector)}"
        )

    def test_delete_by_id_list_does_not_use_filter_selector(self):
        """Direct list deletion bypasses the filter path (regression guard)."""
        store, mock_client = self._make_store()

        mock_vector_store = MagicMock()

        with patch.object(store, "_get_vector_store", return_value=mock_vector_store):
            store.delete_documents("silo_1", ids=["id-1", "id-2"])

        mock_client.delete.assert_not_called()
        mock_vector_store.delete.assert_called_once_with(ids=["id-1", "id-2"])

    def test_delete_skips_on_none_filter(self):
        """None filter must not trigger any client call."""
        store, mock_client = self._make_store()

        store.delete_documents("silo_1", ids=None)

        mock_client.delete.assert_not_called()
        mock_client.scroll.assert_not_called()

    def test_delete_excluding_adds_must_not_on_fresh_batch(self):
        """delete_documents_excluding deletes the resource's chunks except the fresh batch."""
        store, mock_client = self._make_store()

        store.delete_documents_excluding(
            "silo_1",
            filter_metadata={"resource_id": {"$eq": 7}},
            exclude={"index_batch": "abc123"},
        )

        mock_client.delete.assert_called_once()
        from qdrant_client.models import FilterSelector

        selector = mock_client.delete.call_args.kwargs["points_selector"]
        assert isinstance(selector, FilterSelector)
        must_not = selector.filter.must_not
        assert any(
            getattr(c, "key", None) == "index_batch"
            and getattr(getattr(c, "match", None), "value", None) == "abc123"
            for c in must_not
        )


class TestPGVectorStoreDeleteByFilter:
    """PGVectorStore.delete_documents with a metadata-filter dict (native SQL DELETE)."""

    def _make_store(self):
        from tools.vector_stores.pgvector_store import PGVectorStore

        store = PGVectorStore.__new__(PGVectorStore)
        store.db = MagicMock()
        store.async_engine = None

        # engine.begin() context manager yielding a connection that records execute().
        self.mock_conn = MagicMock()
        mock_engine = MagicMock()
        mock_engine.begin.return_value.__enter__.return_value = self.mock_conn
        mock_engine.begin.return_value.__exit__.return_value = False
        store.engine = mock_engine
        return store

    def test_delete_by_filter_issues_single_native_delete(self):
        """A metadata-filter dict runs one DELETE, never an embedding/similarity_search loop."""
        store = self._make_store()

        with patch.object(store, "_get_vector_store") as mock_get_vs:
            store.delete_documents("silo_1", ids={"resource_id": {"$eq": 7}})

        mock_get_vs.assert_not_called()  # no embedding model is built for deletes
        self.mock_conn.execute.assert_called_once()
        sql_arg, params = self.mock_conn.execute.call_args.args
        assert "DELETE FROM langchain_pg_embedding" in str(sql_arg)
        assert params["name"] == "silo_1"
        assert 7 in params.values() or "7" in params.values()

    def test_delete_skips_on_empty_filter(self):
        """An empty/None filter must not issue any SQL."""
        store = self._make_store()
        store.delete_documents("silo_1", ids={})
        store.delete_documents("silo_1", ids=None)
        self.mock_conn.execute.assert_not_called()

    def test_delete_by_id_list_uses_langchain_store(self):
        """Direct list deletion still goes through the LangChain wrapper, not SQL."""
        store = self._make_store()
        mock_vs = MagicMock()

        with patch.object(store, "_get_vector_store", return_value=mock_vs):
            store.delete_documents("silo_1", ids=["id-1", "id-2"])

        mock_vs.delete.assert_called_once_with(ids=["id-1", "id-2"])
        self.mock_conn.execute.assert_not_called()

    def test_delete_excluding_keeps_fresh_batch(self):
        """delete_documents_excluding builds an IS DISTINCT FROM guard for the kept batch."""
        store = self._make_store()

        store.delete_documents_excluding(
            "silo_1",
            filter_metadata={"resource_id": {"$eq": 7}},
            exclude={"index_batch": "abc123"},
        )

        self.mock_conn.execute.assert_called_once()
        sql_arg, params = self.mock_conn.execute.call_args.args
        sql = str(sql_arg)
        assert "DELETE FROM langchain_pg_embedding" in sql
        assert "IS DISTINCT FROM" in sql
        assert params["exf0"] == "index_batch"
        assert params["exv0"] == "abc123"

    def test_delete_excluding_requires_filter(self):
        """An empty candidate filter is rejected (would delete the whole collection)."""
        store = self._make_store()
        with pytest.raises(ValueError, match="filter_metadata is required"):
            store.delete_documents_excluding("silo_1", filter_metadata={}, exclude={"index_batch": "x"})


class TestPGVectorStoreStrForJsonb:
    """PGVectorStore._str_for_jsonb produces lowercase 'true'/'false' for booleans.

    PostgreSQL's ``->>`` returns JSON booleans as lowercase literals; ``str(True)``
    yields ``'True'`` which would never match.
    """

    def setup_method(self):
        from tools.vector_stores.pgvector_store import PGVectorStore

        self.fn = PGVectorStore._str_for_jsonb

    def test_true_produces_lowercase(self):
        assert self.fn(True) == "true"

    def test_false_produces_lowercase(self):
        assert self.fn(False) == "false"

    def test_integer_unchanged(self):
        assert self.fn(42) == "42"

    def test_string_unchanged(self):
        assert self.fn("hello") == "hello"

    def test_none_produces_none_string(self):
        # None should produce "None" — callers guard against None upstream
        assert self.fn(None) == "None"

    def test_operator_condition_eq_bool_false_produces_lowercase(self):
        """End-to-end: _operator_condition for $eq False must bind 'false' not 'False'."""
        from tools.vector_stores.pgvector_store import PGVectorStore

        params: dict = {}
        frags = PGVectorStore._operator_condition(0, "active", "$eq", False, params)
        assert len(frags) == 1
        assert params["v0"] == "false"

    def test_operator_condition_ne_bool_true_produces_lowercase(self):
        """$ne True must bind 'true'."""
        from tools.vector_stores.pgvector_store import PGVectorStore

        params: dict = {}
        PGVectorStore._operator_condition(0, "active", "$ne", True, params)
        assert params["v0"] == "true"

    def test_operator_condition_in_list_with_bool_produces_lowercase(self):
        """$in list containing booleans must bind lowercase strings."""
        from tools.vector_stores.pgvector_store import PGVectorStore

        params: dict = {}
        PGVectorStore._operator_condition(0, "active", "$in", [True, False], params)
        assert params["in0_0"] == "true"
        assert params["in0_1"] == "false"
