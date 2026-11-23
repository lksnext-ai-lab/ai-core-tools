"""Per-silo indexing settings (chunking + PDF loader) through the internal API and export/import."""

import pytest
from models.embedding_service import EmbeddingService
from models.repository import Repository
from models.silo import Silo
from schemas.import_schemas import ConflictMode
from services.silo_export_service import SiloExportService
from services.silo_import_service import SiloImportService

STRUCTURED_OPTIONS = {"section_prefix": False, "remove_headers_footers": True}


@pytest.fixture
def embedding_service(db, fake_app):
    service = EmbeddingService(
        name="Indexing Test Embeddings",
        provider="OpenAI",
        api_key="sk-test-fake",  # pragma: allowlist secret
        app_id=fake_app.app_id,
    )
    db.add(service)
    db.flush()
    return service


def _silos_url(app_id, silo_id=None):
    return f"/internal/apps/{app_id}/silos/" + (str(silo_id) if silo_id is not None else "")


class TestSiloIndexingSettings:
    def test_new_silo_template_has_defaults_and_catalog(self, client, fake_app, owner_headers):
        detail = client.get(_silos_url(fake_app.app_id, 0), headers=owner_headers).json()

        assert (detail["chunk_size"], detail["chunk_overlap"], detail["pdf_loader"]) == (2000, 400, "pymupdf")
        options = detail["indexing_options"]
        assert [loader["key"] for loader in options["pdf_loaders"]] == ["pymupdf", "pymupdf4llm"]
        assert (options["min_chunk_size"], options["max_chunk_size"]) == (200, 8000)

    def test_create_and_update_silo_with_indexing_settings(self, client, db, fake_app, owner_headers, embedding_service):
        created = client.post(_silos_url(fake_app.app_id), headers=owner_headers, json={
            "name": "Manuals", "embedding_service_id": embedding_service.service_id,
            "chunk_size": 3000, "chunk_overlap": 500,
            "pdf_loader": "pymupdf4llm", "pdf_loader_options": {"section_prefix": False},
        })
        assert created.status_code == 201, created.text
        silo_id = created.json()["silo_id"]
        assert created.json()["pdf_loader_options"] == STRUCTURED_OPTIONS

        # Omitted indexing fields keep their value on update.
        updated = client.put(_silos_url(fake_app.app_id, silo_id), headers=owner_headers, json={"name": "Manuals v2"})
        assert updated.status_code == 200, updated.text
        silo = db.get(Silo, silo_id)
        db.refresh(silo)
        assert (silo.name, silo.chunk_size, silo.chunk_overlap, silo.pdf_loader) == ("Manuals v2", 3000, 500, "pymupdf4llm")

        # Switching loader without options resets them to that loader's defaults.
        client.put(_silos_url(fake_app.app_id, silo_id), headers=owner_headers, json={"name": "Manuals v2", "pdf_loader": "pymupdf"})
        db.refresh(silo)
        assert (silo.pdf_loader, silo.pdf_loader_options) == ("pymupdf", {})

    def test_silo_without_indexing_fields_gets_defaults(self, client, db, fake_app, owner_headers):
        created = client.post(_silos_url(fake_app.app_id), headers=owner_headers, json={"name": "Plain"})
        silo = db.get(Silo, created.json()["silo_id"])

        assert (silo.chunk_size, silo.chunk_overlap, silo.pdf_loader) == (2000, 400, "pymupdf")

    @pytest.mark.parametrize("payload", [
        {"chunk_size": 100},
        {"chunk_size": 1000, "chunk_overlap": 900},
        {"pdf_loader": "does-not-exist"},
        {"pdf_loader": "pymupdf4llm", "pdf_loader_options": {"unknown": True}},
    ])
    def test_invalid_settings_are_rejected(self, client, fake_app, owner_headers, payload):
        response = client.post(_silos_url(fake_app.app_id), headers=owner_headers, json={"name": "Bad", **payload})

        assert response.status_code in (400, 422), response.text


class TestRepositoryIndexingSettings:
    def test_repository_settings_are_stored_on_its_silo(self, client, db, fake_app, owner_headers, embedding_service):
        base = f"/internal/apps/{fake_app.app_id}/repositories/"
        created = client.post(base, headers=owner_headers, json={
            "name": "Contracts", "embedding_service_id": embedding_service.service_id,
            "chunk_size": 1500, "pdf_loader": "pymupdf4llm",
        })
        assert created.status_code in (200, 201), created.text
        repository_id = created.json()["repository_id"]
        repo = db.get(Repository, repository_id)
        assert (repo.silo.chunk_size, repo.silo.chunk_overlap, repo.silo.pdf_loader) == (1500, 400, "pymupdf4llm")

        updated = client.put(f"{base}{repository_id}", headers=owner_headers, json={"name": "Contracts", "chunk_overlap": 100})
        assert updated.status_code == 200, updated.text
        db.refresh(repo.silo)
        assert (repo.silo.chunk_size, repo.silo.chunk_overlap) == (1500, 100)

        detail = client.get(f"{base}{repository_id}", headers=owner_headers).json()
        assert (detail["chunk_size"], detail["chunk_overlap"], detail["pdf_loader"]) == (1500, 100, "pymupdf4llm")
        assert detail["indexing_options"]["default_pdf_loader"] == "pymupdf"


class TestSiloExportImportIndexingSettings:
    def test_settings_survive_export_and_import(self, db, fake_app, embedding_service):
        silo = Silo(
            name="Exported", silo_type="CUSTOM", app_id=fake_app.app_id, vector_db_type="PGVECTOR",
            embedding_service_id=embedding_service.service_id, chunk_size=2500, chunk_overlap=250,
            pdf_loader="pymupdf4llm", pdf_loader_options=STRUCTURED_OPTIONS,
        )
        db.add(silo)
        db.flush()

        exported = SiloExportService(db).export_silo(silo.silo_id, fake_app.app_id)
        summary = SiloImportService(db).import_silo(
            exported, fake_app.app_id, ConflictMode.RENAME, new_name="Imported",
            selected_embedding_service_id=embedding_service.service_id,
        )

        imported = db.get(Silo, summary.component_id)
        assert (imported.chunk_size, imported.chunk_overlap, imported.pdf_loader) == (2500, 250, "pymupdf4llm")
        assert imported.pdf_loader_options == STRUCTURED_OPTIONS

    def test_unknown_loader_in_an_export_falls_back_to_defaults_with_a_warning(self, db, fake_app, embedding_service):
        silo = Silo(name="Old", silo_type="CUSTOM", app_id=fake_app.app_id, vector_db_type="PGVECTOR",
                    embedding_service_id=embedding_service.service_id)
        db.add(silo)
        db.flush()
        exported = SiloExportService(db).export_silo(silo.silo_id, fake_app.app_id)
        exported.silo.pdf_loader = "loader-from-another-instance"

        summary = SiloImportService(db).import_silo(
            exported, fake_app.app_id, ConflictMode.RENAME, new_name="Imported old",
            selected_embedding_service_id=embedding_service.service_id,
        )

        imported = db.get(Silo, summary.component_id)
        assert imported.pdf_loader == "pymupdf"
        assert any("Indexing settings not applied" in warning for warning in summary.warnings)

