"""Indexing failures reach the user: upload response, document status, service status.

Scenario from a real incident: the embedding service's API key was revoked, uploads kept
answering "success" and the silo silently stayed at 0 documents.

Vector store and text extraction are mocked; index_resource and ServiceHealthService open
their own SessionLocal(), redirected here to the test connection.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import httpx
import openai
import pytest
from langchain_core.documents import Document
from sqlalchemy.orm import Session

from models.embedding_service import EmbeddingService
from models.repository import Repository
from models.resource import Resource
from models.silo import Silo


@pytest.fixture
def shared_sessions(db):
    connection = db.get_bind()

    def _session_factory():
        inner = Session(bind=connection, autocommit=False, autoflush=True)
        inner.close = lambda: None
        return inner

    with patch("services.silo_service.SessionLocal", side_effect=_session_factory), \
            patch("services.service_health_service.SessionLocal", side_effect=_session_factory):
        yield


@pytest.fixture
def repo_base(tmp_path):
    # Never write test uploads into the developer's real REPO_BASE_FOLDER.
    with patch("services.resource_service.REPO_BASE_FOLDER", str(tmp_path)):
        yield tmp_path


@pytest.fixture
def embedding_service(db, fake_app):
    svc = EmbeddingService(name="small", provider="OpenAI", description="text-embedding-3-small",
                           api_key="sk-test-fake", app_id=fake_app.app_id)  # pragma: allowlist secret
    db.add(svc)
    db.flush()
    return svc


@pytest.fixture
def repository(db, fake_app, embedding_service):
    silo = Silo(name="kk silo", silo_type="REPO", status="active", app_id=fake_app.app_id,
                vector_db_type="PGVECTOR", embedding_service_id=embedding_service.service_id)
    db.add(silo)
    db.flush()
    repo = Repository(name="kk", type="default", status="active", app_id=fake_app.app_id,
                      silo_id=silo.silo_id, create_date=datetime.now())
    db.add(repo)
    db.flush()
    return repo


def _revoked_key_error():
    request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    return openai.AuthenticationError(
        "Incorrect API key provided: sk-proj-***LRsA", response=httpx.Response(401, request=request), body=None
    )


def _extract(path, file_extension, base_metadata):
    return [Document(page_content="chunk", metadata={**base_metadata})]


def _upload(client, headers, app_id, repo_id, store):
    with patch("services.silo_service._get_vector_store", return_value=store), \
            patch("services.silo_service.SiloService.extract_documents_from_file", side_effect=_extract):
        return client.post(
            f"/internal/apps/{app_id}/repositories/{repo_id}/resources",
            headers=headers,
            files=[("files", ("cv.txt", b"hello", "text/plain"))],
        )


@pytest.mark.usefixtures("shared_sessions", "repo_base")
class TestRevokedEmbeddingKey:
    def test_upload_reports_the_failure_and_everything_shows_it(self, client, db, fake_app, owner_headers,
                                                                repository, embedding_service):
        store = MagicMock()
        store.index_documents.side_effect = _revoked_key_error()

        resp = _upload(client, owner_headers, fake_app.app_id, repository.repository_id, store)

        # The file is kept (it can be reindexed) but the response says it is not searchable.
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["created_resources"]) == 1
        assert "could not be indexed" in body["message"]
        [failure] = body["indexing_failures"]
        assert failure["filename"] == "cv.txt"
        assert "Embedding service 'small' rejected its credentials" in failure["error"]
        assert "LRsA" not in failure["error"]

        detail = client.get(f"/internal/apps/{fake_app.app_id}/repositories/{repository.repository_id}",
                            headers=owner_headers).json()
        [resource] = detail["resources"]
        assert resource["status"] == "error"
        assert resource["error_message"] == failure["error"]
        assert detail["service_warnings"] == [failure["error"]]

        services = client.get(f"/internal/apps/{fake_app.app_id}/embedding-services/",
                              headers=owner_headers).json()
        [listed] = [s for s in services if s["service_id"] == embedding_service.service_id]
        assert listed["last_error"] == failure["error"]
        assert listed["last_error_at"] is not None

    def test_successful_upload_marks_indexed_and_clears_the_service_error(self, client, db, fake_app, owner_headers,
                                                                          repository, embedding_service):
        embedding_service.last_error = "old failure"
        embedding_service.last_error_at = datetime.now()
        db.flush()

        resp = _upload(client, owner_headers, fake_app.app_id, repository.repository_id, MagicMock())

        assert resp.status_code == 200, resp.text
        assert resp.json()["indexing_failures"] == []
        resource = db.query(Resource).filter(Resource.repository_id == repository.repository_id).one()
        db.refresh(resource)
        assert resource.status == "indexed"
        db.refresh(embedding_service)
        assert embedding_service.last_error is None


class TestServiceErrorClearedOnReconfigure:
    def test_new_api_key_clears_the_recorded_error(self, db, embedding_service):
        embedding_service.last_error = "rejected key"
        embedding_service.last_error_at = datetime.now()
        db.flush()

        embedding_service.api_key = "sk-test-new"  # pragma: allowlist secret
        db.flush()

        assert embedding_service.last_error is None
        assert embedding_service.last_error_at is None

    def test_unrelated_edit_keeps_the_error(self, db, embedding_service):
        embedding_service.last_error = "rejected key"
        db.flush()

        embedding_service.name = "renamed"
        db.flush()

        assert embedding_service.last_error == "rejected key"


@pytest.fixture
def indexed_resource(db, repository):
    resource = Resource(name="cv", uri="cv.txt", type=".txt", status="indexed",
                        repository_id=repository.repository_id, create_date=datetime.now())
    db.add(resource)
    db.flush()
    return resource


def _reindex(client, headers, app_id, silo_id, resource_id, store, extract=_extract):
    with patch("services.silo_service._get_vector_store", return_value=store), \
            patch("services.silo_service.SiloService.extract_documents_from_file", side_effect=extract):
        return client.post(f"/internal/apps/{app_id}/silos/{silo_id}/resources/{resource_id}/reindex",
                           headers=headers)


@pytest.mark.usefixtures("shared_sessions")
class TestReindexFailures:
    def test_no_text_keeps_the_previous_chunks(self, client, db, fake_app, owner_headers, repository,
                                               indexed_resource):
        store = MagicMock()

        resp = _reindex(client, owner_headers, fake_app.app_id, repository.silo_id,
                        indexed_resource.resource_id, store, extract=lambda *a: [])

        assert resp.status_code == 422
        assert "No text could be extracted" in resp.json()["detail"]
        store.delete_documents_excluding.assert_not_called()
        db.refresh(indexed_resource)
        assert indexed_resource.status == "error"

    def test_failure_returns_the_current_reason_without_raw_text(self, client, db, fake_app, owner_headers,
                                                                 repository, indexed_resource):
        indexed_resource.error_message = "stale reason from an earlier run"
        db.flush()
        store = MagicMock()
        store.index_documents.side_effect = RuntimeError("[SQL: INSERT INTO langchain_pg_embedding] host=db.internal")

        resp = _reindex(client, owner_headers, fake_app.app_id, repository.silo_id,
                        indexed_resource.resource_id, store)

        assert resp.status_code == 500
        detail = resp.json()["detail"]
        assert detail.startswith("Indexing failed (RuntimeError)")
        for leaked in ("stale", "SQL", "db.internal"):
            assert leaked not in detail
        store.delete_documents_excluding.assert_not_called()
