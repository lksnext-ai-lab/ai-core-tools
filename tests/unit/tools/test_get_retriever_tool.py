"""Unit tests for ``tools.agentTools.get_retriever_tool``.

All external dependencies (SiloService, MetadataValuesCacheService, SessionLocal)
are mocked — no LLM, database, or vector store is touched.

Patch strategy:
  - ``tools.agentTools.SiloService`` — top-level import in agentTools.
  - ``services.metadata_values_cache_service.MetadataValuesCacheService`` —
    imported lazily by both collect_distinct_values (construction) and
    _build_fallback_notice (runtime); patching the canonical source covers both.
  - ``tools.agentTools.SessionLocal`` — patched so construction never touches
    the real database.

Coverage:
- AC-3  : silo without metadata_definition → tool only accepts 'query'.
- AC-5  : LLM kwargs with undeclared field are discarded with WARNING.
- AC-8  : 0 results with LLM filter → fallback with pinned only + notice.
- AC-21 : content always starts with "N results …" eco.
- AC-22 : max_retrieval_calls ceiling.
- NFR-1 : pinned filter passes undeclared fields without whitelist rejection.
- NFR-1 : pinned filter works when silo has no metadata_definition.
- Extra : vector store exception returns generic constant message.
- Extra : None kwargs are silently ignored.
- Extra : counter is per-instance.
- Extra : silo with metadata_definition → args_schema has extra fields.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.documents import Document
from langchain_core.tools import StructuredTool

from tools.agentTools import _SEARCH_ERROR_MSG

# ---------------------------------------------------------------------------
# Patch targets
# ---------------------------------------------------------------------------

_SILO_SERVICE_PATCH = "tools.agentTools.SiloService"
_CACHE_SERVICE_PATCH = "services.metadata_values_cache_service.MetadataValuesCacheService"
_SESSION_LOCAL_PATCH = "tools.agentTools.SessionLocal"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_metadata_def(fields: list[dict]) -> MagicMock:
    md = MagicMock()
    md.fields = fields
    return md


def _make_silo(
    silo_id: int = 1,
    name: str = "Test Silo",
    description: str = "desc",
    silo_type: str = "REPO",
    vector_db_type: str = "PGVECTOR",
    metadata_def_fields: list[dict] | None = None,
) -> MagicMock:
    silo = MagicMock()
    silo.silo_id = silo_id
    silo.name = name
    silo.description = description
    silo.silo_type = silo_type
    silo.vector_db_type = vector_db_type
    if metadata_def_fields is None:
        silo.metadata_definition = None
    else:
        silo.metadata_definition = _make_metadata_def(metadata_def_fields)
    return silo


def _make_doc(content: str = "chunk text", metadata: dict | None = None) -> Document:
    return Document(page_content=content, metadata=metadata or {})


def _mock_retriever(docs: List[Document]) -> MagicMock:
    retriever = MagicMock()
    retriever.ainvoke = AsyncMock(return_value=docs)
    return retriever


def _mock_silo_service(docs: List[Document]) -> MagicMock:
    svc = MagicMock()
    svc.get_silo_retriever = MagicMock(return_value=_mock_retriever(docs))
    return svc


def _mock_cache(values: list[str] | None = None) -> MagicMock:
    cache = MagicMock()
    cache.get_distinct_values = MagicMock(return_value=values or [])
    return cache


def _mock_session_local():
    """Return a callable that yields a fresh no-op context manager on each call."""
    @contextmanager
    def _no_op():
        yield MagicMock()

    return MagicMock(side_effect=lambda: _no_op())


def _patches(svc=None, cache=None):
    """Return a list of patch context managers for the three external deps."""
    return [
        patch(_SILO_SERVICE_PATCH, svc or _mock_silo_service([])),
        patch(_CACHE_SERVICE_PATCH, cache or _mock_cache()),
        patch(_SESSION_LOCAL_PATCH, _mock_session_local()),
    ]


# ---------------------------------------------------------------------------
# AC-3 — silo without metadata_definition → only 'query' field
# ---------------------------------------------------------------------------


class TestNoMetadataDefinition:
    def test_returns_structured_tool(self):
        from tools.agentTools import get_retriever_tool

        silo = _make_silo(metadata_def_fields=None)
        with patch(_SILO_SERVICE_PATCH, _mock_silo_service([])), \
             patch(_CACHE_SERVICE_PATCH, _mock_cache()), \
             patch(_SESSION_LOCAL_PATCH, _mock_session_local()):
            tool = get_retriever_tool(silo=silo)
        assert isinstance(tool, StructuredTool)

    def test_args_schema_has_only_query(self):
        from tools.agentTools import get_retriever_tool

        silo = _make_silo(metadata_def_fields=None)
        with patch(_SILO_SERVICE_PATCH, _mock_silo_service([])), \
             patch(_CACHE_SERVICE_PATCH, _mock_cache()), \
             patch(_SESSION_LOCAL_PATCH, _mock_session_local()):
            tool = get_retriever_tool(silo=silo)
        assert list(tool.args_schema.model_fields.keys()) == ["query"]

    def test_name_follows_ad8_pattern(self):
        from tools.agentTools import get_retriever_tool

        silo = _make_silo(silo_id=42, name="My Silo", metadata_def_fields=None)
        with patch(_SILO_SERVICE_PATCH, _mock_silo_service([])), \
             patch(_CACHE_SERVICE_PATCH, _mock_cache()), \
             patch(_SESSION_LOCAL_PATCH, _mock_session_local()):
            tool = get_retriever_tool(silo=silo)
        assert tool.name == "search_my_silo_42"

    @pytest.mark.asyncio
    async def test_returns_content_and_artifact_tuple(self):
        from tools.agentTools import get_retriever_tool

        silo = _make_silo(metadata_def_fields=None)
        docs = [_make_doc("hello")]
        with patch(_SILO_SERVICE_PATCH, _mock_silo_service(docs)), \
             patch(_CACHE_SERVICE_PATCH, _mock_cache()), \
             patch(_SESSION_LOCAL_PATCH, _mock_session_local()):
            tool = get_retriever_tool(silo=silo)
            content, artifact = await tool.coroutine(query="test query")
        assert isinstance(content, str)
        assert isinstance(artifact, list)

    @pytest.mark.asyncio
    async def test_eco_no_filter(self):
        from tools.agentTools import get_retriever_tool

        silo = _make_silo(metadata_def_fields=None)
        docs = [_make_doc("doc1"), _make_doc("doc2")]
        with patch(_SILO_SERVICE_PATCH, _mock_silo_service(docs)), \
             patch(_CACHE_SERVICE_PATCH, _mock_cache()), \
             patch(_SESSION_LOCAL_PATCH, _mock_session_local()):
            tool = get_retriever_tool(silo=silo)
            content, artifact = await tool.coroutine(query="test")
        assert "2 results (no metadata filter)" in content
        assert len(artifact) == 2


# ---------------------------------------------------------------------------
# Silo with metadata_definition — args_schema has extra fields
# ---------------------------------------------------------------------------


class TestWithMetadataDefinition:
    def test_args_schema_includes_metadata_field(self):
        from tools.agentTools import get_retriever_tool

        silo = _make_silo(
            metadata_def_fields=[{"name": "anio", "description": "Year", "type": "int"}]
        )
        with patch(_SILO_SERVICE_PATCH, _mock_silo_service([])), \
             patch(_CACHE_SERVICE_PATCH, _mock_cache()), \
             patch(_SESSION_LOCAL_PATCH, _mock_session_local()):
            tool = get_retriever_tool(silo=silo)
        fields = tool.args_schema.model_fields
        assert "query" in fields
        assert "anio" in fields

    def test_description_not_empty(self):
        from tools.agentTools import get_retriever_tool

        silo = _make_silo(
            metadata_def_fields=[{"name": "anio", "description": "Year", "type": "int"}]
        )
        with patch(_SILO_SERVICE_PATCH, _mock_silo_service([])), \
             patch(_CACHE_SERVICE_PATCH, _mock_cache()), \
             patch(_SESSION_LOCAL_PATCH, _mock_session_local()):
            tool = get_retriever_tool(silo=silo)
        assert tool.description and len(tool.description) > 10


# ---------------------------------------------------------------------------
# AC-5 — undeclared field in LLM kwargs → discarded with WARNING
# ---------------------------------------------------------------------------


class TestUndeclaredFieldDiscarded:
    @pytest.mark.asyncio
    async def test_undeclared_field_ignored_and_search_proceeds(self):
        from tools import agentTools
        from tools.agentTools import get_retriever_tool

        silo = _make_silo(
            metadata_def_fields=[{"name": "anio", "description": "Year", "type": "int"}]
        )
        docs = [_make_doc("result")]
        warning_calls: list[str] = []

        original_warning = agentTools.logger.warning

        def capture_warning(msg, *args, **kwargs):
            warning_calls.append(msg % args if args else str(msg))
            return original_warning(msg, *args, **kwargs)

        with patch(_SILO_SERVICE_PATCH, _mock_silo_service(docs)), \
             patch(_CACHE_SERVICE_PATCH, _mock_cache()), \
             patch(_SESSION_LOCAL_PATCH, _mock_session_local()), \
             patch.object(agentTools.logger, "warning", side_effect=capture_warning):
            tool = get_retriever_tool(silo=silo)
            content, artifact = await tool.coroutine(
                query="test", anio=2023, undeclared_field="bad_value"
            )

        assert "1 results" in content
        assert len(artifact) == 1
        assert any("undeclared_field" in msg for msg in warning_calls), (
            f"Expected WARNING for undeclared_field, got: {warning_calls}"
        )

    @pytest.mark.asyncio
    async def test_none_kwargs_are_silently_ignored(self):
        from tools.agentTools import get_retriever_tool

        silo = _make_silo(
            metadata_def_fields=[{"name": "anio", "description": "Year", "type": "int"}]
        )
        docs = [_make_doc("result")]
        with patch(_SILO_SERVICE_PATCH, _mock_silo_service(docs)), \
             patch(_CACHE_SERVICE_PATCH, _mock_cache()), \
             patch(_SESSION_LOCAL_PATCH, _mock_session_local()):
            tool = get_retriever_tool(silo=silo)
            content, artifact = await tool.coroutine(query="test", anio=None)
        assert "1 results (no metadata filter)" in content


# ---------------------------------------------------------------------------
# NFR-1 — pinned filter: undeclared fields pass through without whitelist rejection
# ---------------------------------------------------------------------------


class TestPinnedFilterPassthrough:
    @pytest.mark.asyncio
    async def test_undeclared_pinned_field_passes_to_store(self):
        """Caller-supplied filter with undeclared field must NOT be dropped."""
        from tools.agentTools import get_retriever_tool

        silo = _make_silo(
            metadata_def_fields=[{"name": "anio", "description": "Year", "type": "int"}]
        )
        docs = [_make_doc("result")]
        mock_svc = _mock_silo_service(docs)

        with patch(_SILO_SERVICE_PATCH, mock_svc), \
             patch(_CACHE_SERVICE_PATCH, _mock_cache()), \
             patch(_SESSION_LOCAL_PATCH, _mock_session_local()):
            tool = get_retriever_tool(
                silo=silo,
                search_params={"filter": {"undeclared_field": "value", "anio": 2023}},
            )
            content, artifact = await tool.coroutine(query="test")

        assert "1 results" in content
        assert mock_svc.get_silo_retriever.call_count >= 1
        call_args = mock_svc.get_silo_retriever.call_args
        passed_params = call_args[0][1]
        assert passed_params is not None
        assert "filter" in passed_params
        assert "undeclared_field" in passed_params["filter"], (
            "Undeclared pinned field must survive the filter pipeline"
        )
        assert "anio" in passed_params["filter"]

    @pytest.mark.asyncio
    async def test_pinned_filter_works_with_no_metadata_definition(self):
        """Pinned filter on a silo with no metadata_definition must pass through."""
        from tools.agentTools import get_retriever_tool

        silo = _make_silo(metadata_def_fields=None)
        docs = [_make_doc("result")]
        mock_svc = _mock_silo_service(docs)

        with patch(_SILO_SERVICE_PATCH, mock_svc), \
             patch(_CACHE_SERVICE_PATCH, _mock_cache()), \
             patch(_SESSION_LOCAL_PATCH, _mock_session_local()):
            tool = get_retriever_tool(
                silo=silo,
                search_params={"filter": {"some_field": "some_value"}},
            )
            content, artifact = await tool.coroutine(query="test")

        assert "1 results" in content
        assert mock_svc.get_silo_retriever.call_count >= 1


# ---------------------------------------------------------------------------
# AC-21 — eco of filter applied and result count
# ---------------------------------------------------------------------------


class TestEcoFilterAndResultCount:
    @pytest.mark.asyncio
    async def test_eco_with_llm_filter(self):
        from tools.agentTools import get_retriever_tool

        silo = _make_silo(
            metadata_def_fields=[{"name": "anio", "description": "Year", "type": "int"}]
        )
        docs = [_make_doc(f"doc{i}") for i in range(5)]
        with patch(_SILO_SERVICE_PATCH, _mock_silo_service(docs)), \
             patch(_CACHE_SERVICE_PATCH, _mock_cache()), \
             patch(_SESSION_LOCAL_PATCH, _mock_session_local()):
            tool = get_retriever_tool(silo=silo)
            content, artifact = await tool.coroutine(query="test", anio=2023)

        assert "5 results" in content
        assert "anio" in content

    @pytest.mark.asyncio
    async def test_eco_without_any_filter(self):
        from tools.agentTools import get_retriever_tool

        silo = _make_silo(metadata_def_fields=None)
        docs = [_make_doc("only doc")]
        with patch(_SILO_SERVICE_PATCH, _mock_silo_service(docs)), \
             patch(_CACHE_SERVICE_PATCH, _mock_cache()), \
             patch(_SESSION_LOCAL_PATCH, _mock_session_local()):
            tool = get_retriever_tool(silo=silo)
            content, _ = await tool.coroutine(query="anything")
        assert "1 results (no metadata filter)" in content


# ---------------------------------------------------------------------------
# AC-8 — 0 results with LLM filter → fallback without LLM filter + notice
# ---------------------------------------------------------------------------


class TestFallbackBehavior:
    @pytest.mark.asyncio
    async def test_fallback_triggered_on_zero_llm_results(self):
        from tools.agentTools import get_retriever_tool

        silo = _make_silo(
            metadata_def_fields=[{"name": "anio", "description": "Year", "type": "int"}]
        )
        fallback_docs = [_make_doc("fallback result")]
        call_count = [0]

        async def fake_ainvoke(query):
            call_count[0] += 1
            return [] if call_count[0] == 1 else fallback_docs

        mock_ret = MagicMock()
        mock_ret.ainvoke = fake_ainvoke
        mock_svc = MagicMock()
        mock_svc.get_silo_retriever = MagicMock(return_value=mock_ret)
        cache = _mock_cache(["2020", "2021", "2022"])

        with patch(_SILO_SERVICE_PATCH, mock_svc), \
             patch(_CACHE_SERVICE_PATCH, cache), \
             patch(_SESSION_LOCAL_PATCH, _mock_session_local()):
            tool = get_retriever_tool(silo=silo)
            content, artifact = await tool.coroutine(query="docs", anio=9999)

        assert "[notice]" in content
        assert "retried without it" in content
        assert "2020" in content or "2021" in content or "2022" in content
        assert len(artifact) == 1

    @pytest.mark.asyncio
    async def test_fallback_shows_pinned_filter_eco(self):
        from tools.agentTools import get_retriever_tool

        silo = _make_silo(
            metadata_def_fields=[
                {"name": "organismo", "description": "Org", "type": "str"},
                {"name": "anio", "description": "Year", "type": "int"},
            ]
        )
        fallback_docs = [_make_doc("doc")]
        call_count = [0]

        async def fake_ainvoke(query):
            call_count[0] += 1
            return [] if call_count[0] == 1 else fallback_docs

        mock_ret = MagicMock()
        mock_ret.ainvoke = fake_ainvoke
        mock_svc = MagicMock()
        mock_svc.get_silo_retriever = MagicMock(return_value=mock_ret)
        cache = _mock_cache(["GobA", "GobB"])

        with patch(_SILO_SERVICE_PATCH, mock_svc), \
             patch(_CACHE_SERVICE_PATCH, cache), \
             patch(_SESSION_LOCAL_PATCH, _mock_session_local()):
            tool = get_retriever_tool(
                silo=silo,
                search_params={"filter": {"organismo": "GobA"}},
            )
            content, _ = await tool.coroutine(query="docs", anio=9999)

        assert "[notice]" in content
        assert "organismo" in content

    @pytest.mark.asyncio
    async def test_no_fallback_when_zero_results_without_llm_filter(self):
        from tools.agentTools import get_retriever_tool

        silo = _make_silo(metadata_def_fields=None)
        mock_svc = MagicMock()
        mock_svc.get_silo_retriever = MagicMock(return_value=_mock_retriever([]))

        with patch(_SILO_SERVICE_PATCH, mock_svc), \
             patch(_CACHE_SERVICE_PATCH, _mock_cache()), \
             patch(_SESSION_LOCAL_PATCH, _mock_session_local()):
            tool = get_retriever_tool(silo=silo)
            content, artifact = await tool.coroutine(query="nothing")

        assert mock_svc.get_silo_retriever.call_count == 1
        assert "[notice]" not in content
        assert "0 results (no metadata filter)" in content


# ---------------------------------------------------------------------------
# AC-22 — max_retrieval_calls ceiling
# ---------------------------------------------------------------------------


class TestRetrievalCeiling:
    @pytest.mark.asyncio
    async def test_calls_within_ceiling_execute_normally(self):
        from tools.agentTools import get_retriever_tool

        silo = _make_silo(metadata_def_fields=None)
        docs = [_make_doc("doc")]
        N = 3
        with patch(_SILO_SERVICE_PATCH, _mock_silo_service(docs)), \
             patch(_CACHE_SERVICE_PATCH, _mock_cache()), \
             patch(_SESSION_LOCAL_PATCH, _mock_session_local()):
            tool = get_retriever_tool(silo=silo, max_retrieval_calls=N)
            for _ in range(N):
                content, artifact = await tool.coroutine(query="q")
                assert "1 results" in content
                assert len(artifact) == 1

    @pytest.mark.asyncio
    async def test_n_plus_1_call_returns_limit_message_without_hitting_store(self):
        from tools.agentTools import get_retriever_tool

        silo = _make_silo(metadata_def_fields=None)
        docs = [_make_doc("doc")]
        N = 2
        mock_svc = _mock_silo_service(docs)
        with patch(_SILO_SERVICE_PATCH, mock_svc), \
             patch(_CACHE_SERVICE_PATCH, _mock_cache()), \
             patch(_SESSION_LOCAL_PATCH, _mock_session_local()):
            tool = get_retriever_tool(silo=silo, max_retrieval_calls=N)
            for _ in range(N):
                await tool.coroutine(query="q")
            calls_before = mock_svc.get_silo_retriever.call_count
            content, artifact = await tool.coroutine(query="q")

        assert mock_svc.get_silo_retriever.call_count == calls_before
        assert "Search limit reached" in content
        assert artifact == []

    @pytest.mark.asyncio
    async def test_none_max_retrieval_calls_means_no_ceiling(self):
        from tools.agentTools import get_retriever_tool

        silo = _make_silo(metadata_def_fields=None)
        docs = [_make_doc("doc")]
        MANY = 20
        with patch(_SILO_SERVICE_PATCH, _mock_silo_service(docs)), \
             patch(_CACHE_SERVICE_PATCH, _mock_cache()), \
             patch(_SESSION_LOCAL_PATCH, _mock_session_local()):
            tool = get_retriever_tool(silo=silo, max_retrieval_calls=None)
            for _ in range(MANY):
                content, _ = await tool.coroutine(query="q")
                assert "Search limit reached" not in content

    @pytest.mark.asyncio
    async def test_counters_are_per_tool_instance(self):
        from tools.agentTools import get_retriever_tool

        silo = _make_silo(metadata_def_fields=None)
        docs = [_make_doc("doc")]
        with patch(_SILO_SERVICE_PATCH, _mock_silo_service(docs)), \
             patch(_CACHE_SERVICE_PATCH, _mock_cache()), \
             patch(_SESSION_LOCAL_PATCH, _mock_session_local()):
            tool_a = get_retriever_tool(silo=silo, max_retrieval_calls=1)
            tool_b = get_retriever_tool(silo=silo, max_retrieval_calls=1)
            await tool_a.coroutine(query="q")
            content_b, _ = await tool_b.coroutine(query="q")
        assert "Search limit reached" not in content_b


# ---------------------------------------------------------------------------
# Exception capture — vector store error → generic constant, no propagation
# ---------------------------------------------------------------------------


class TestExceptionCapture:
    @pytest.mark.asyncio
    async def test_vector_store_exception_returns_generic_message(self):
        from tools.agentTools import get_retriever_tool

        silo = _make_silo(metadata_def_fields=None)
        mock_ret = MagicMock()
        mock_ret.ainvoke = AsyncMock(
            side_effect=RuntimeError("postgresql://user:secret@host/db connection refused")
        )
        mock_svc = MagicMock()
        mock_svc.get_silo_retriever = MagicMock(return_value=mock_ret)

        with patch(_SILO_SERVICE_PATCH, mock_svc), \
             patch(_CACHE_SERVICE_PATCH, _mock_cache()), \
             patch(_SESSION_LOCAL_PATCH, _mock_session_local()):
            tool = get_retriever_tool(silo=silo)
            content, artifact = await tool.coroutine(query="test")

        assert content == _SEARCH_ERROR_MSG
        assert "postgresql" not in content
        assert artifact == []

    @pytest.mark.asyncio
    async def test_fallback_exception_also_returns_generic_message(self):
        from tools.agentTools import get_retriever_tool

        silo = _make_silo(
            metadata_def_fields=[{"name": "anio", "description": "Year", "type": "int"}]
        )
        call_count = [0]

        async def exploding_ainvoke(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return []
            raise RuntimeError("store down during fallback")

        mock_ret = MagicMock()
        mock_ret.ainvoke = exploding_ainvoke
        mock_svc = MagicMock()
        mock_svc.get_silo_retriever = MagicMock(return_value=mock_ret)

        with patch(_SILO_SERVICE_PATCH, mock_svc), \
             patch(_CACHE_SERVICE_PATCH, _mock_cache()), \
             patch(_SESSION_LOCAL_PATCH, _mock_session_local()):
            tool = get_retriever_tool(silo=silo)
            content, artifact = await tool.coroutine(query="test", anio=9999)

        assert content == _SEARCH_ERROR_MSG
        assert artifact == []


# ---------------------------------------------------------------------------
# Null/zero silo_id guard
# ---------------------------------------------------------------------------


class TestNullSiloId:
    def test_returns_none_for_zero_silo_id(self):
        from tools.agentTools import get_retriever_tool

        silo = _make_silo(silo_id=0, metadata_def_fields=None)
        with patch(_SILO_SERVICE_PATCH, MagicMock()), \
             patch(_CACHE_SERVICE_PATCH, _mock_cache()), \
             patch(_SESSION_LOCAL_PATCH, _mock_session_local()):
            result = get_retriever_tool(silo=silo)
        assert result is None


class TestCollectionIsolation:
    """AC-7: no tool argument can redirect the query to another silo's collection."""

    @pytest.mark.asyncio
    async def test_collection_not_overridable_via_filter(self):
        from tools.agentTools import get_retriever_tool

        silo = _make_silo(
            silo_id=42,
            metadata_def_fields=[
                {"name": "silo_id", "description": "ignored", "type": "int"},
                {"name": "collection", "description": "ignored", "type": "str"},
            ],
        )
        mock_svc = _mock_silo_service([_make_doc("x")])

        with patch(_SILO_SERVICE_PATCH, mock_svc), \
             patch(_CACHE_SERVICE_PATCH, _mock_cache()), \
             patch(_SESSION_LOCAL_PATCH, _mock_session_local()):
            tool = get_retriever_tool(silo=silo)
            await tool.coroutine(query="test", silo_id=9999, collection="silo_9999")

        assert mock_svc.get_silo_retriever.call_count >= 1
        for call in mock_svc.get_silo_retriever.call_args_list:
            assert call[0][0] == 42, (
                f"get_silo_retriever called with silo_id={call[0][0]!r}, expected 42"
            )
