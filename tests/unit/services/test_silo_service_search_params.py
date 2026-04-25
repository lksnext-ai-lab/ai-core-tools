"""Unit tests for SiloService.find_docs_in_collection with new search params."""
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

from services.silo_service import SiloService


def _make_silo():
    silo = MagicMock()
    silo.embedding_service_id = 1
    return silo


def _make_docs(*lengths: int) -> list:
    return [Document(page_content="x" * length, metadata={}) for length in lengths]


# ---------------------------------------------------------------------------
# search_type forwarding
# ---------------------------------------------------------------------------

def test_find_docs_passes_mmr_search_type():
    silo = _make_silo()
    vs = MagicMock()
    vs.search_similar_documents.return_value = []
    db = MagicMock()

    with patch("services.silo_service.SiloRepository.get_by_id", return_value=silo), \
         patch("services.silo_service.SiloService.check_silo_collection_exists", return_value=True), \
         patch("services.silo_service.SiloRepository.get_embedding_service_by_id", return_value="emb"), \
         patch("services.silo_service._get_vector_store", return_value=vs):
        SiloService.find_docs_in_collection(
            silo_id=1, query="test", search_type="mmr", fetch_k=20, lambda_mult=0.7, db=db
        )

    vs.search_similar_documents.assert_called_once()
    call_kwargs = vs.search_similar_documents.call_args[1]
    assert call_kwargs["search_type"] == "mmr"
    assert call_kwargs["fetch_k"] == 20
    assert call_kwargs["lambda_mult"] == 0.7


def test_find_docs_passes_score_threshold():
    silo = _make_silo()
    vs = MagicMock()
    vs.search_similar_documents.return_value = []
    db = MagicMock()

    with patch("services.silo_service.SiloRepository.get_by_id", return_value=silo), \
         patch("services.silo_service.SiloService.check_silo_collection_exists", return_value=True), \
         patch("services.silo_service.SiloRepository.get_embedding_service_by_id", return_value="emb"), \
         patch("services.silo_service._get_vector_store", return_value=vs):
        SiloService.find_docs_in_collection(
            silo_id=1,
            query="test",
            search_type="similarity_score_threshold",
            score_threshold=0.75,
            db=db,
        )

    call_kwargs = vs.search_similar_documents.call_args[1]
    assert call_kwargs["search_type"] == "similarity_score_threshold"
    assert call_kwargs["score_threshold"] == 0.75


# ---------------------------------------------------------------------------
# content-length post-retrieval filter
# ---------------------------------------------------------------------------

def test_find_docs_filters_by_min_content_length():
    silo = _make_silo()
    vs = MagicMock()
    vs.search_similar_documents.return_value = _make_docs(50, 200, 300)
    db = MagicMock()

    with patch("services.silo_service.SiloRepository.get_by_id", return_value=silo), \
         patch("services.silo_service.SiloService.check_silo_collection_exists", return_value=True), \
         patch("services.silo_service.SiloRepository.get_embedding_service_by_id", return_value="emb"), \
         patch("services.silo_service._get_vector_store", return_value=vs):
        results = SiloService.find_docs_in_collection(
            silo_id=1, query="test", min_content_length=100, db=db
        )

    assert len(results) == 2
    assert all(len(d.page_content) >= 100 for d in results)


def test_find_docs_filters_by_max_content_length():
    silo = _make_silo()
    vs = MagicMock()
    vs.search_similar_documents.return_value = _make_docs(50, 200, 500)
    db = MagicMock()

    with patch("services.silo_service.SiloRepository.get_by_id", return_value=silo), \
         patch("services.silo_service.SiloService.check_silo_collection_exists", return_value=True), \
         patch("services.silo_service.SiloRepository.get_embedding_service_by_id", return_value="emb"), \
         patch("services.silo_service._get_vector_store", return_value=vs):
        results = SiloService.find_docs_in_collection(
            silo_id=1, query="test", max_content_length=250, db=db
        )

    assert len(results) == 2
    assert all(len(d.page_content) <= 250 for d in results)


def test_find_docs_filters_by_min_and_max_content_length():
    silo = _make_silo()
    vs = MagicMock()
    vs.search_similar_documents.return_value = _make_docs(10, 100, 300, 600)
    db = MagicMock()

    with patch("services.silo_service.SiloRepository.get_by_id", return_value=silo), \
         patch("services.silo_service.SiloService.check_silo_collection_exists", return_value=True), \
         patch("services.silo_service.SiloRepository.get_embedding_service_by_id", return_value="emb"), \
         patch("services.silo_service._get_vector_store", return_value=vs):
        results = SiloService.find_docs_in_collection(
            silo_id=1, query="test", min_content_length=50, max_content_length=400, db=db
        )

    # Only 100-char and 300-char docs pass
    assert len(results) == 2
    assert all(50 <= len(d.page_content) <= 400 for d in results)


def test_find_docs_no_content_filter_returns_all():
    silo = _make_silo()
    vs = MagicMock()
    vs.search_similar_documents.return_value = _make_docs(10, 100, 300)
    db = MagicMock()

    with patch("services.silo_service.SiloRepository.get_by_id", return_value=silo), \
         patch("services.silo_service.SiloService.check_silo_collection_exists", return_value=True), \
         patch("services.silo_service.SiloRepository.get_embedding_service_by_id", return_value="emb"), \
         patch("services.silo_service._get_vector_store", return_value=vs):
        results = SiloService.find_docs_in_collection(
            silo_id=1, query="test", db=db
        )

    assert len(results) == 3


def test_find_docs_returns_empty_when_silo_not_found():
    db = MagicMock()
    with patch("services.silo_service.SiloRepository.get_by_id", return_value=None):
        results = SiloService.find_docs_in_collection(silo_id=99, query="x", db=db)
    assert results == []


def test_find_docs_returns_empty_when_collection_missing():
    silo = _make_silo()
    db = MagicMock()
    with patch("services.silo_service.SiloRepository.get_by_id", return_value=silo), \
         patch("services.silo_service.SiloService.check_silo_collection_exists", return_value=False):
        results = SiloService.find_docs_in_collection(silo_id=1, query="x", db=db)
    assert results == []
