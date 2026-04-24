from unittest.mock import MagicMock, patch

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
    )
