from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from schemas.silo_schemas import SiloSearchSchema
from services.silo_service import SiloService


def _make_silo() -> MagicMock:
    silo = MagicMock()
    silo.embedding_service_id = 42
    return silo


def test_find_docs_in_collection_uses_explicit_limit_with_metadata_filter():
    silo = _make_silo()
    vector_store = MagicMock()
    vector_store.search_similar_documents.return_value = []
    db = MagicMock()

    with patch("services.silo_service.SiloRepository.get_by_id", return_value=silo), patch(
        "services.silo_service.SiloService.check_silo_collection_exists",
        return_value=True,
    ), patch(
        "services.silo_service.SiloRepository.get_embedding_service_by_id",
        return_value="embedding-service",
    ), patch("services.silo_service._get_vector_store", return_value=vector_store):
        SiloService.find_docs_in_collection(
            silo_id=7,
            query="invoice",
            filter_metadata={"doc_type": {"$eq": "pdf"}},
            limit=12,
            db=db,
        )

    vector_store.search_similar_documents.assert_called_once_with(
        "silo_7",
        "invoice",
        embedding_service="embedding-service",
        filter_metadata={"doc_type": {"$eq": "pdf"}},
        k=12,
        search_type="similarity",
        score_threshold=None,
        fetch_k=None,
        lambda_mult=None,
    )


def test_find_docs_in_collection_defaults_to_service_limit_when_limit_is_missing():
    silo = _make_silo()
    vector_store = MagicMock()
    vector_store.search_similar_documents.return_value = []
    db = MagicMock()

    with patch("services.silo_service.SiloRepository.get_by_id", return_value=silo), patch(
        "services.silo_service.SiloService.check_silo_collection_exists",
        return_value=True,
    ), patch(
        "services.silo_service.SiloRepository.get_embedding_service_by_id",
        return_value="embedding-service",
    ), patch("services.silo_service._get_vector_store", return_value=vector_store):
        SiloService.find_docs_in_collection(
            silo_id=7,
            query="invoice",
            db=db,
        )

    vector_store.search_similar_documents.assert_called_once_with(
        "silo_7",
        "invoice",
        embedding_service="embedding-service",
        filter_metadata={},
        k=100,
        search_type="similarity",
        score_threshold=None,
        fetch_k=None,
        lambda_mult=None,
    )


def test_find_docs_in_collection_clamps_limit_to_max():
    silo = _make_silo()
    vector_store = MagicMock()
    vector_store.search_similar_documents.return_value = []
    db = MagicMock()

    with patch("services.silo_service.SiloRepository.get_by_id", return_value=silo), patch(
        "services.silo_service.SiloService.check_silo_collection_exists",
        return_value=True,
    ), patch(
        "services.silo_service.SiloRepository.get_embedding_service_by_id",
        return_value="embedding-service",
    ), patch("services.silo_service._get_vector_store", return_value=vector_store):
        SiloService.find_docs_in_collection(
            silo_id=7,
            query="invoice",
            limit=5000,
            db=db,
        )

    vector_store.search_similar_documents.assert_called_once_with(
        "silo_7",
        "invoice",
        embedding_service="embedding-service",
        filter_metadata={},
        k=200,
        search_type="similarity",
        score_threshold=None,
        fetch_k=None,
        lambda_mult=None,
    )


def test_find_docs_in_collection_forwards_search_type():
    """search_type param is forwarded to the vector store adapter."""
    silo = _make_silo()
    vector_store = MagicMock()
    vector_store.search_similar_documents.return_value = []
    db = MagicMock()

    with patch("services.silo_service.SiloRepository.get_by_id", return_value=silo), patch(
        "services.silo_service.SiloService.check_silo_collection_exists",
        return_value=True,
    ), patch(
        "services.silo_service.SiloRepository.get_embedding_service_by_id",
        return_value="embedding-service",
    ), patch("services.silo_service._get_vector_store", return_value=vector_store):
        SiloService.find_docs_in_collection(
            silo_id=7,
            query="invoice",
            search_type="mmr",
            db=db,
        )

    vector_store.search_similar_documents.assert_called_once_with(
        "silo_7",
        "invoice",
        embedding_service="embedding-service",
        filter_metadata={},
        k=100,
        search_type="mmr",
        score_threshold=None,
        fetch_k=None,
        lambda_mult=None,
    )


def test_find_docs_in_collection_forwards_score_threshold():
    """score_threshold is forwarded when search_type='similarity_score_threshold'."""
    silo = _make_silo()
    vector_store = MagicMock()
    vector_store.search_similar_documents.return_value = []
    db = MagicMock()

    with patch("services.silo_service.SiloRepository.get_by_id", return_value=silo), patch(
        "services.silo_service.SiloService.check_silo_collection_exists",
        return_value=True,
    ), patch(
        "services.silo_service.SiloRepository.get_embedding_service_by_id",
        return_value="embedding-service",
    ), patch("services.silo_service._get_vector_store", return_value=vector_store):
        SiloService.find_docs_in_collection(
            silo_id=7,
            query="invoice",
            search_type="similarity_score_threshold",
            score_threshold=0.75,
            db=db,
        )

    vector_store.search_similar_documents.assert_called_once_with(
        "silo_7",
        "invoice",
        embedding_service="embedding-service",
        filter_metadata={},
        k=100,
        search_type="similarity_score_threshold",
        score_threshold=0.75,
        fetch_k=None,
        lambda_mult=None,
    )


def test_find_docs_in_collection_forwards_mmr_params():
    """fetch_k and lambda_mult are forwarded when search_type='mmr'."""
    silo = _make_silo()
    vector_store = MagicMock()
    vector_store.search_similar_documents.return_value = []
    db = MagicMock()

    with patch("services.silo_service.SiloRepository.get_by_id", return_value=silo), patch(
        "services.silo_service.SiloService.check_silo_collection_exists",
        return_value=True,
    ), patch(
        "services.silo_service.SiloRepository.get_embedding_service_by_id",
        return_value="embedding-service",
    ), patch("services.silo_service._get_vector_store", return_value=vector_store):
        SiloService.find_docs_in_collection(
            silo_id=7,
            query="invoice",
            search_type="mmr",
            fetch_k=50,
            lambda_mult=0.3,
            db=db,
        )

    vector_store.search_similar_documents.assert_called_once_with(
        "silo_7",
        "invoice",
        embedding_service="embedding-service",
        filter_metadata={},
        k=100,
        search_type="mmr",
        score_threshold=None,
        fetch_k=50,
        lambda_mult=0.3,
    )


def test_silo_search_schema_rejects_invalid_search_type():
    """SiloSearchSchema raises ValidationError for unknown search_type."""
    import pytest

    with pytest.raises(ValidationError) as exc_info:
        SiloSearchSchema(query="test", search_type="fuzzy")

    assert "search_type" in str(exc_info.value)


def test_silo_search_schema_rejects_score_threshold_with_wrong_type():
    """SiloSearchSchema raises ValidationError when score_threshold used without correct search_type."""
    import pytest

    with pytest.raises(ValidationError) as exc_info:
        SiloSearchSchema(query="test", search_type="similarity", score_threshold=0.8)

    assert "score_threshold" in str(exc_info.value)

