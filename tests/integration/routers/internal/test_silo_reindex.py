"""Integration tests for AC-15: POST /internal/apps/{app_id}/silos/{silo_id}/resources/{resource_id}/reindex.

Verifies idempotency — multiple calls must not accumulate duplicate chunks — using the
index-then-swap flow: the fresh batch is written first, then the resource's stale chunks
(those not stamped with the new index_batch) are removed via delete_documents_excluding, so
the collection never passes through an empty state.

Vector DB and file-system operations are mocked. Session isolation: reindex_resource opens its own
SessionLocal(); the reindex_session_patch fixture redirects it to share the test DB connection.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, call
from sqlalchemy.orm import Session
from langchain_core.documents import Document

from models.silo import Silo
from models.repository import Repository
from models.resource import Resource
from models.embedding_service import EmbeddingService


@pytest.fixture()
def reindex_session_patch(db):
    """Redirect SessionLocal inside reindex_resource to the test connection.

    Replaces close() with a no-op so the shared test connection is not prematurely closed.
    """
    connection = db.get_bind()

    def _session_factory():
        inner = Session(bind=connection, autocommit=False, autoflush=True)
        inner.close = lambda: None
        return inner

    with patch("services.silo_service.SessionLocal", side_effect=_session_factory):
        yield


@pytest.fixture()
def reindex_silo(db, fake_app):
    """REPO-type Silo with an attached EmbeddingService, scoped to fake_app."""
    embedding_svc = EmbeddingService(
        name="Test Embedding Service",
        provider="OpenAI",
        api_key="sk-test-fake",  # pragma: allowlist secret
        app_id=fake_app.app_id,
    )
    db.add(embedding_svc)
    db.flush()

    silo = Silo(
        name="Reindex Test Silo",
        description="Silo for reindex integration tests",
        silo_type="REPO",
        status="active",
        app_id=fake_app.app_id,
        vector_db_type="PGVECTOR",
        embedding_service_id=embedding_svc.service_id,
    )
    db.add(silo)
    db.flush()
    return silo


@pytest.fixture()
def reindex_repository(db, fake_app, reindex_silo):
    """Repository linked to reindex_silo."""
    repo = Repository(
        name="Reindex Test Repo",
        type="default",
        status="active",
        app_id=fake_app.app_id,
        silo_id=reindex_silo.silo_id,
        create_date=datetime.now(),
    )
    db.add(repo)
    db.flush()
    return repo


@pytest.fixture()
def reindex_resource(db, reindex_repository):
    """Resource inside reindex_repository."""
    resource = Resource(
        name="doc.txt",
        uri="doc.txt",
        type=".txt",
        status="active",
        repository_id=reindex_repository.repository_id,
        create_date=datetime.now(),
    )
    db.add(resource)
    db.flush()
    return resource


def _reindex_url(app_id: int, silo_id: int, resource_id: int) -> str:
    return (
        f"/internal/apps/{app_id}/silos/{silo_id}"
        f"/resources/{resource_id}/reindex"
    )


def _fake_extract(path, file_extension, base_metadata):
    """Stand-in for extract_documents_from_file: stamps each chunk with base_metadata
    (which includes the index_batch set by index_resource), as the real splitter does."""
    return [
        Document(page_content=f"chunk-{i}", metadata={**base_metadata})
        for i in range(3)
    ]


def _make_fake_vector_store(indexed_docs: list) -> MagicMock:
    """Stateful vector store mock matching the index-then-swap flow: index appends;
    delete_documents_excluding removes the resource's chunks not in the kept batch."""
    store = MagicMock()

    def fake_index(collection_name, documents, embedding_service=None):
        indexed_docs.extend(documents)

    def fake_delete_excluding(collection_name, filter_metadata, exclude, embedding_service=None):
        field = next(iter(filter_metadata))
        value = filter_metadata[field].get("$eq")
        survivors = []
        for d in indexed_docs:
            matches_resource = str(d.metadata.get(field)) == str(value)
            keep_batch = all(d.metadata.get(k) == v for k, v in exclude.items())
            if matches_resource and not keep_batch:
                continue  # stale chunk → drop
            survivors.append(d)
        indexed_docs[:] = survivors

    store.index_documents.side_effect = fake_index
    store.delete_documents_excluding.side_effect = fake_delete_excluding
    return store


class TestReindexIdempotency:
    """POST /internal/apps/{app_id}/silos/{silo_id}/resources/{resource_id}/reindex"""

    def test_reindex_twice_does_not_duplicate_chunks(
        self,
        client,
        db,
        fake_app,
        owner_headers,
        reindex_silo,
        reindex_resource,
        reindex_session_patch,
    ):
        """AC-15: reindexing multiple times must not accumulate duplicate chunks."""
        db.flush()

        resource_id = reindex_resource.resource_id
        silo_id = reindex_silo.silo_id
        app_id = fake_app.app_id

        indexed_docs: list[Document] = []
        fake_store = _make_fake_vector_store(indexed_docs)

        with (
            patch("services.silo_service._get_vector_store", return_value=fake_store),
            patch(
                "services.silo_service.SiloService.extract_documents_from_file",
                side_effect=_fake_extract,
            ),
        ):
            resp1 = client.post(
                _reindex_url(app_id, silo_id, resource_id),
                headers=owner_headers,
            )
            assert resp1.status_code == 200, f"First reindex failed: {resp1.text}"
            count_after_first = len(indexed_docs)
            assert count_after_first == 3, (
                f"Expected 3 chunks after first index, got {count_after_first}"
            )

            resp2 = client.post(
                _reindex_url(app_id, silo_id, resource_id),
                headers=owner_headers,
            )
            assert resp2.status_code == 200, f"Second reindex failed: {resp2.text}"
            count_after_second = len(indexed_docs)
            assert count_after_second == count_after_first, (
                f"Chunk count grew on second reindex: {count_after_first} → {count_after_second}"
            )

            resp3 = client.post(
                _reindex_url(app_id, silo_id, resource_id),
                headers=owner_headers,
            )
            assert resp3.status_code == 200, f"Third reindex failed: {resp3.text}"
            count_after_third = len(indexed_docs)
            assert count_after_third == count_after_first, (
                f"Chunk count grew on third reindex: {count_after_first} → {count_after_third}"
            )

    def test_reindex_indexes_before_swap_delete(
        self,
        client,
        db,
        fake_app,
        owner_headers,
        reindex_silo,
        reindex_resource,
        reindex_session_patch,
    ):
        """Index-then-swap: the fresh batch is written before stale chunks are deleted."""
        db.flush()

        resource_id = reindex_resource.resource_id
        call_order: list[str] = []
        fake_store = MagicMock()
        fake_store.index_documents.side_effect = lambda *a, **kw: call_order.append("index")
        fake_store.delete_documents_excluding.side_effect = lambda *a, **kw: call_order.append("delete")

        with (
            patch("services.silo_service._get_vector_store", return_value=fake_store),
            patch(
                "services.silo_service.SiloService.extract_documents_from_file",
                side_effect=_fake_extract,
            ),
        ):
            resp = client.post(
                _reindex_url(fake_app.app_id, reindex_silo.silo_id, resource_id),
                headers=owner_headers,
            )
        assert resp.status_code == 200
        assert call_order == ["index", "delete"], (
            f"Expected ['index', 'delete'], got {call_order}"
        )

    def test_reindex_does_not_delete_if_index_fails(
        self,
        client,
        db,
        fake_app,
        owner_headers,
        reindex_silo,
        reindex_resource,
        reindex_session_patch,
    ):
        """If indexing raises, the swap delete never runs — previous chunks survive (no data loss)."""
        db.flush()

        resource_id = reindex_resource.resource_id
        fake_store = MagicMock()
        fake_store.index_documents.side_effect = RuntimeError("vector store unavailable")
        delete_called = []
        fake_store.delete_documents_excluding.side_effect = lambda *a, **kw: delete_called.append(True)

        with (
            patch("services.silo_service._get_vector_store", return_value=fake_store),
            patch(
                "services.silo_service.SiloService.extract_documents_from_file",
                side_effect=_fake_extract,
            ),
        ):
            resp = client.post(
                _reindex_url(fake_app.app_id, reindex_silo.silo_id, resource_id),
                headers=owner_headers,
            )

        assert resp.status_code == 500, (
            f"Expected 500 when indexing fails, got {resp.status_code}"
        )
        assert not delete_called, "swap delete must not run when indexing fails"

    def test_reindex_uses_correct_filter(
        self,
        client,
        db,
        fake_app,
        owner_headers,
        reindex_silo,
        reindex_resource,
        reindex_session_patch,
    ):
        """The swap delete targets the resource_id and preserves the fresh index_batch."""
        db.flush()

        resource_id = reindex_resource.resource_id
        delete_calls: list = []
        fake_store = MagicMock()
        fake_store.delete_documents_excluding.side_effect = (
            lambda coll, filter_metadata, exclude, embedding_service=None: delete_calls.append(
                (filter_metadata, exclude)
            )
        )

        with (
            patch("services.silo_service._get_vector_store", return_value=fake_store),
            patch(
                "services.silo_service.SiloService.extract_documents_from_file",
                side_effect=_fake_extract,
            ),
        ):
            resp = client.post(
                _reindex_url(fake_app.app_id, reindex_silo.silo_id, resource_id),
                headers=owner_headers,
            )

        assert resp.status_code == 200
        assert len(delete_calls) == 1, (
            f"Expected delete_documents_excluding called once, got {len(delete_calls)} calls"
        )
        filter_metadata, exclude = delete_calls[0]
        assert filter_metadata.get("resource_id", {}).get("$eq") == resource_id, (
            f"Filter resource_id mismatch: {filter_metadata}"
        )
        assert "index_batch" in exclude, f"Expected index_batch in exclude, got {exclude}"


class TestReindexAuthorization:

    def test_reindex_requires_authentication(
        self, client, fake_app, reindex_silo, reindex_resource, db
    ):
        """Unauthenticated request (no Authorization header) returns 401."""
        db.flush()
        resp = client.post(
            _reindex_url(fake_app.app_id, reindex_silo.silo_id, reindex_resource.resource_id)
        )
        assert resp.status_code == 401

    def test_reindex_returns_404_for_unknown_resource(
        self, client, fake_app, owner_headers, reindex_silo, db
    ):
        """Non-existent resource_id returns 404."""
        db.flush()
        resp = client.post(
            _reindex_url(fake_app.app_id, reindex_silo.silo_id, 999999),
            headers=owner_headers,
        )
        assert resp.status_code == 404

    def test_reindex_returns_400_for_resource_in_different_silo(
        self,
        client,
        db,
        fake_app,
        owner_headers,
        reindex_silo,
        reindex_resource,
    ):
        """Resource belonging to a different silo returns 400."""
        db.flush()

        other_silo = Silo(
            name="Other Silo",
            silo_type="REPO",
            status="active",
            app_id=fake_app.app_id,
            vector_db_type="PGVECTOR",
        )
        db.add(other_silo)
        db.flush()

        resp = client.post(
            _reindex_url(fake_app.app_id, other_silo.silo_id, reindex_resource.resource_id),
            headers=owner_headers,
        )
        assert resp.status_code == 400

    def test_reindex_returns_422_when_silo_has_no_embedding_service(
        self,
        client,
        db,
        fake_app,
        owner_headers,
        reindex_session_patch,
    ):
        """When the silo has no embedding service, the endpoint returns 422 (not a silent 200)."""
        db.flush()

        silo_no_emb = Silo(
            name="Silo Without Embedding",
            silo_type="REPO",
            status="active",
            app_id=fake_app.app_id,
            vector_db_type="PGVECTOR",
        )
        db.add(silo_no_emb)
        db.flush()

        repo = Repository(
            name="Repo for no-emb silo",
            type="default",
            status="active",
            app_id=fake_app.app_id,
            silo_id=silo_no_emb.silo_id,
            create_date=datetime.now(),
        )
        db.add(repo)
        db.flush()

        resource = Resource(
            name="doc.txt",
            uri="doc.txt",
            type=".txt",
            status="active",
            repository_id=repo.repository_id,
            create_date=datetime.now(),
        )
        db.add(resource)
        db.flush()

        resp = client.post(
            _reindex_url(fake_app.app_id, silo_no_emb.silo_id, resource.resource_id),
            headers=owner_headers,
        )
        assert resp.status_code == 422, (
            f"Expected 422 for silo without embedding service, got {resp.status_code}: {resp.text}"
        )
