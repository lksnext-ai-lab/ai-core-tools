"""Integration tests: retired embedding services and test-connection (step_012).

AC-8 (index / search blocked with the re-index message; delete document, silo, app succeed),
AC-11 (test connection still works for retired AI, embedding and sandbox services).
Real test DB; vector stores, LLM/embedding/sandbox providers are patched.
"""

import pytest

from tests.integration._eos_enforcement_helpers import (  # noqa: F401  (fixtures)
    LLM_ANSWER,
    ai_service,
    api_key_headers,
    embedding_builders,
    embedding_service,
    fake_sandbox_registry,
    fake_vector_store,
    future,
    guard_warnings,
    lifecycle_caplog,
    llm_builders,
    make_agent,
    make_repository,
    make_silo,
    past,
    sandbox_service,
)
from tests.integration.routers.internal._eos_helpers import ai_payload, embedding_payload, sandbox_payload

pytestmark = pytest.mark.integration

REINDEX_HINT = "Silos using it must be re-indexed with another embedding service."


def _public(app, silo, suffix=""):
    return f"/public/v1/app/{app.app_id}/silos/{silo.silo_id}{suffix}"


def _retired_silo(db, app, name="emb-retired", notice=None):
    emb = embedding_service(db, app, name=name, eos=past(2), notice=notice)
    return emb, make_silo(db, app, embedding_service_id=emb.service_id)


def _embedding_message(emb, notice=""):
    return f"Service {emb.name} was retired on {emb.end_of_service_at:%Y-%m-%d}. {REINDEX_HINT}{notice}"


class TestIndexingAndSearchAreBlocked:
    """AC-8 (blocked half)."""

    def test_public_index_file_returns_409_with_reindex_message(
        self, client, db, fake_app, fake_user, embedding_builders, fake_vector_store, lifecycle_caplog
    ):
        emb, silo = _retired_silo(db, fake_app, notice="Use emb-2.")
        resp = client.post(
            _public(fake_app, silo, "/docs/index-file"),
            files={"file": ("note.txt", b"hello world, this is some text", "text/plain")},
            headers=api_key_headers(db, fake_app, fake_user),
        )

        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"] == _embedding_message(emb, " Use emb-2.")
        assert resp.json()["error_code"] == "SERVICE_RETIRED"
        assert REINDEX_HINT in resp.json()["detail"]
        fake_vector_store.index_documents.assert_not_called()
        assert not embedding_builders.called
        warnings = guard_warnings(lifecycle_caplog)
        assert len(warnings) == 1
        assert "kind=embedding" in warnings[0].getMessage()
        assert f"service_id={emb.service_id}" in warnings[0].getMessage()
        assert f"app_id={fake_app.app_id}" in warnings[0].getMessage()

    def test_public_search_returns_409_with_reindex_message(
        self, client, db, fake_app, fake_user, embedding_builders, fake_vector_store
    ):
        emb, silo = _retired_silo(db, fake_app)

        resp = client.post(_public(fake_app, silo, "/search"), json={"query": "anything"},
                           headers=api_key_headers(db, fake_app, fake_user))

        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"] == _embedding_message(emb)
        fake_vector_store.search_similar_documents.assert_not_called()
        assert not embedding_builders.called

    def test_public_find_docs_returns_409(self, client, db, fake_app, fake_user, embedding_builders, fake_vector_store):
        emb, silo = _retired_silo(db, fake_app)

        resp = client.post(_public(fake_app, silo, "/docs/find"), json={"query": "anything"},
                           headers=api_key_headers(db, fake_app, fake_user))

        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"] == _embedding_message(emb)
        fake_vector_store.search_similar_documents.assert_not_called()

    def test_internal_search_returns_409(self, client, db, fake_app, owner_headers, embedding_builders, fake_vector_store):
        emb, silo = _retired_silo(db, fake_app)

        resp = client.post(f"/internal/apps/{fake_app.app_id}/silos/{silo.silo_id}/search",
                           json={"query": "anything"}, headers=owner_headers)

        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"] == _embedding_message(emb)
        fake_vector_store.search_similar_documents.assert_not_called()

    def test_same_silo_works_when_the_date_moves_to_the_future(
        self, client, db, fake_app, fake_user, embedding_builders, fake_vector_store
    ):
        """AC-12 for the embedding kind: no other change is needed."""
        emb, silo = _retired_silo(db, fake_app)
        headers = api_key_headers(db, fake_app, fake_user)
        assert client.post(_public(fake_app, silo, "/search"), json={"query": "q"}, headers=headers).status_code == 409

        emb.end_of_service_at = future(90)
        db.flush()

        resp = client.post(_public(fake_app, silo, "/search"), json={"query": "q"}, headers=headers)
        assert resp.status_code == 200, resp.text
        fake_vector_store.search_similar_documents.assert_called_once()


class TestCleanupPathsKeepWorking:
    """AC-8 (cleanup half): deleting a document, the silo and the app are never blocked."""

    def test_public_delete_documents_succeeds(
        self, client, db, fake_app, fake_user, embedding_builders, fake_vector_store, lifecycle_caplog
    ):
        _, silo = _retired_silo(db, fake_app)

        resp = client.request("DELETE", _public(fake_app, silo, "/docs/delete"), json={"ids": ["doc-1"]},
                              headers=api_key_headers(db, fake_app, fake_user))

        assert resp.status_code == 200, resp.text
        fake_vector_store.delete_documents.assert_called_once()
        assert not embedding_builders.called
        assert guard_warnings(lifecycle_caplog) == []

    def test_internal_delete_documents_succeeds(
        self, client, db, fake_app, owner_headers, embedding_builders, fake_vector_store
    ):
        _, silo = _retired_silo(db, fake_app)

        resp = client.request("DELETE", f"/internal/apps/{fake_app.app_id}/silos/{silo.silo_id}/documents",
                              json={"document_ids": ["doc-1"]}, headers=owner_headers)

        assert resp.status_code == 200, resp.text
        fake_vector_store.delete_documents.assert_called_once()

    def test_public_delete_silo_succeeds(
        self, client, db, fake_app, fake_user, embedding_builders, fake_vector_store, lifecycle_caplog
    ):
        from models.silo import Silo

        _, silo = _retired_silo(db, fake_app)
        silo_id = silo.silo_id

        resp = client.delete(_public(fake_app, silo), headers=api_key_headers(db, fake_app, fake_user))

        assert resp.status_code == 204, resp.text
        assert db.query(Silo).filter(Silo.silo_id == silo_id).count() == 0
        assert guard_warnings(lifecycle_caplog) == []

    def test_internal_delete_silo_succeeds(self, client, db, fake_app, owner_headers, embedding_builders, fake_vector_store):
        from models.silo import Silo

        _, silo = _retired_silo(db, fake_app)
        silo_id = silo.silo_id

        resp = client.delete(f"/internal/apps/{fake_app.app_id}/silos/{silo_id}", headers=owner_headers)

        assert resp.status_code == 200, resp.text
        assert db.query(Silo).filter(Silo.silo_id == silo_id).count() == 0

    def test_delete_silo_service_level_and_vector_collection_removed(
        self, db, fake_app, embedding_builders, fake_vector_store, lifecycle_caplog
    ):
        from models.silo import Silo
        from services.silo_service import SiloService

        _, silo = _retired_silo(db, fake_app)
        silo_id = silo.silo_id

        SiloService.delete_silo(silo_id, db)

        fake_vector_store.delete_collection.assert_called_once()
        assert db.query(Silo).filter(Silo.silo_id == silo_id).count() == 0
        assert not embedding_builders.called
        assert guard_warnings(lifecycle_caplog) == []

    def test_delete_app_with_retired_services_succeeds(
        self, db, fake_app, fake_ai_service, embedding_builders, llm_builders, fake_vector_store, lifecycle_caplog
    ):
        from models.app import App
        from models.silo import Silo
        from services.app_service import AppService

        app_id = fake_app.app_id
        emb, silo = _retired_silo(db, fake_app)
        make_repository(db, fake_app, silo)
        retired_llm = ai_service(db, fake_app, name="llm-retired-app-delete", eos=past(1))
        make_agent(db, fake_app, retired_llm)
        sandbox_service(db, fake_app, name="sb-retired-app-delete", eos=past(1))

        assert AppService(db).delete_app(app_id) is True

        assert db.query(App).filter(App.app_id == app_id).count() == 0
        assert db.query(Silo).filter(Silo.silo_id == silo.silo_id).count() == 0
        assert guard_warnings(lifecycle_caplog) == []
        assert not embedding_builders.called
        assert not llm_builders.called


class TestConnectionTestsStillWork:
    """AC-11: a retired service can still be tested (admin diagnosing / fixing it)."""

    def test_ai_service_test_by_id_succeeds(self, client, db, fake_app, owner_headers, llm_builders, lifecycle_caplog):
        svc = ai_service(db, fake_app, name="ai-retired-test", eos=past(1))

        resp = client.post(f"/internal/apps/{fake_app.app_id}/ai-services/{svc.service_id}/test",
                           headers=owner_headers)

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "success", resp.text
        assert resp.json()["response"] == LLM_ANSWER
        assert llm_builders.openai.call_count == 1
        assert guard_warnings(lifecycle_caplog) == []

    def test_ai_service_test_connection_with_config_succeeds(
        self, client, db, fake_app, owner_headers, llm_builders, lifecycle_caplog
    ):
        svc = ai_service(db, fake_app, name="ai-retired-test-cfg", eos=past(1))

        resp = client.post(
            f"/internal/apps/{fake_app.app_id}/ai-services/test-connection?service_id={svc.service_id}",
            json=ai_payload(name=svc.name, end_of_service_at=svc.end_of_service_at.isoformat()),
            headers=owner_headers,
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "success", resp.text
        assert guard_warnings(lifecycle_caplog) == []

    def test_embedding_service_test_connection_succeeds(
        self, client, db, fake_app, owner_headers, embedding_builders, lifecycle_caplog
    ):
        svc = embedding_service(db, fake_app, name="emb-retired-test", eos=past(1))

        resp = client.post(
            f"/internal/apps/{fake_app.app_id}/embedding-services/test-connection?service_id={svc.service_id}",
            json=embedding_payload(name=svc.name, end_of_service_at=svc.end_of_service_at.isoformat()),
            headers=owner_headers,
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "success", resp.text
        assert embedding_builders.openai.call_count == 1
        assert guard_warnings(lifecycle_caplog) == []

    def test_sandbox_service_test_by_id_succeeds(
        self, client, db, fake_app, owner_headers, fake_sandbox_registry, lifecycle_caplog
    ):
        svc = sandbox_service(db, fake_app, name="sb-retired-test", eos=past(1))

        resp = client.post(f"/internal/apps/{fake_app.app_id}/sandbox-services/{svc.service_id}/test",
                           headers=owner_headers)

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "success", resp.text
        assert len(fake_sandbox_registry.instances) == 1
        assert guard_warnings(lifecycle_caplog) == []

    def test_sandbox_service_test_connection_with_config_succeeds(
        self, client, db, fake_app, owner_headers, fake_sandbox_registry, lifecycle_caplog
    ):
        svc = sandbox_service(db, fake_app, name="sb-retired-test-cfg", eos=past(1))

        resp = client.post(
            f"/internal/apps/{fake_app.app_id}/sandbox-services/test-connection?service_id={svc.service_id}",
            json=sandbox_payload(name=svc.name, end_of_service_at=svc.end_of_service_at.isoformat()),
            headers=owner_headers,
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "success", resp.text
        assert len(fake_sandbox_registry.instances) == 1
        assert guard_warnings(lifecycle_caplog) == []
