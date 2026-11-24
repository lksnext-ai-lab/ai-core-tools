"""Neighbouring chunks of a document, against a real PGVector collection.

Chunks store ``resource_id``/``media_id`` as integers while the route receives the
id as a query-string value; the filter must match the stored type.
"""

from unittest.mock import patch

import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding
from models.embedding_service import EmbeddingService
from models.silo import Silo
from services.silo_service import COLLECTION_PREFIX, SiloService, _get_vector_store


@pytest.fixture
def fake_embeddings():
    with patch(
        "tools.vector_stores.pgvector_store.get_embeddings_model",
        return_value=DeterministicFakeEmbedding(size=16),
    ):
        yield


@pytest.fixture
def silo(db, fake_app, fake_embeddings):
    service = EmbeddingService(
        name="Neighbours Test Embeddings", provider="OpenAI",
        api_key="sk-test-fake",  # pragma: allowlist secret
        app_id=fake_app.app_id,
    )
    db.add(service)
    db.flush()
    silo = Silo(
        name="Neighbours", silo_type="REPO", app_id=fake_app.app_id, vector_db_type="PGVECTOR",
        embedding_service_id=service.service_id,
    )
    db.add(silo)
    db.flush()
    store = _get_vector_store(silo)
    collection = COLLECTION_PREFIX + str(silo.silo_id)
    store.index_documents(collection, [
        Document(page_content="resource 61 chunk 1", metadata={"resource_id": 61, "page": 1}),
        Document(page_content="resource 61 chunk 2", metadata={"resource_id": 61, "page": 2}),
        Document(page_content="other resource", metadata={"resource_id": 62, "page": 1}),
        Document(page_content="media chunk", metadata={"media_id": 9, "content_type": "media_chunk", "chunk_index": 0}),
    ])
    yield silo
    store.delete_collection(collection)


@pytest.mark.parametrize("source_id", ["61", 61])
def test_resource_chunks_are_found_by_id(db, silo, source_id):
    chunks = SiloService.get_neighboring_chunks(silo.silo_id, "resource", source_id, db)

    assert [c["page_content"] for c in chunks] == ["resource 61 chunk 1", "resource 61 chunk 2"]


def test_media_chunks_are_found_by_id(db, silo):
    chunks = SiloService.get_neighboring_chunks(silo.silo_id, "media", "9", db)

    assert [c["page_content"] for c in chunks] == ["media chunk"]


def test_non_integer_source_id_is_rejected(db, silo):
    with pytest.raises(ValueError, match="source_id must be an integer"):
        SiloService.get_neighboring_chunks(silo.silo_id, "resource", "abc", db)
