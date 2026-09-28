"""Public API: video/audio indexed straight into a silo, with media services configured on the silo."""

from unittest.mock import patch

import pytest

from models.media import Media


def silos_url(app_id: int, silo_id: int = None, suffix: str = None) -> str:
    base = f"/public/v1/app/{app_id}/silos"
    if silo_id is not None:
        base = f"{base}/{silo_id}"
    if suffix:
        base = f"{base}/{suffix}"
    return base


def api_headers(key: str) -> dict:
    return {"X-API-KEY": key}


@pytest.fixture
def embedding_service(db, fake_app):
    from models.embedding_service import EmbeddingService

    svc = EmbeddingService(name="Test Embeddings", provider="OpenAI", description="text-embedding-3-small",
                           api_key="sk-test", app_id=fake_app.app_id)  # pragma: allowlist secret
    db.add(svc)
    db.flush()
    return svc


def _ai_service(db, app_id, name, supports_video=False):
    from models.ai_service import AIService

    svc = AIService(name=name, provider="OpenAI", api_key="sk-test", app_id=app_id,  # pragma: allowlist secret
                    supports_video=supports_video)
    db.add(svc)
    db.flush()
    return svc


@pytest.fixture
def transcription_service(db, fake_app):
    return _ai_service(db, fake_app.app_id, "Whisper")


@pytest.fixture
def video_service(db, fake_app):
    return _ai_service(db, fake_app.app_id, "Gemini", supports_video=True)


@pytest.fixture
def media_silo(db, fake_app, embedding_service, transcription_service):
    from models.silo import Silo

    silo = Silo(name="Media Silo", app_id=fake_app.app_id, silo_type="CUSTOM", status="active",
                vector_db_type="PGVECTOR", embedding_service_id=embedding_service.service_id,
                transcription_service_id=transcription_service.service_id)
    db.add(silo)
    db.flush()
    return silo


@pytest.fixture(autouse=True)
def media_folder(tmp_path, monkeypatch):
    import tasks.media_tasks as media_tasks

    monkeypatch.setattr(media_tasks, "REPO_BASE_FOLDER", str(tmp_path))
    return tmp_path


@pytest.fixture
def no_processing():
    """The transcription/indexing pipeline is not run: only its scheduling is checked."""
    with patch("tasks.media_tasks.process_media_task_sync") as task:
        yield task


class TestSiloMediaServices:
    def test_create_silo_with_media_services(self, client, fake_app, fake_api_key, embedding_service,
                                             transcription_service, video_service):
        resp = client.post(silos_url(fake_app.app_id), headers=api_headers(fake_api_key.key), json={
            "name": "Videos", "embedding_service_id": embedding_service.service_id,
            "transcription_service_id": transcription_service.service_id,
            "video_ai_service_id": video_service.service_id,
        })
        assert resp.status_code == 201, resp.text
        silo = resp.json()["silo"]
        assert silo["transcription_service_id"] == transcription_service.service_id
        assert silo["video_ai_service_id"] == video_service.service_id

    def test_video_service_must_support_video(self, client, fake_app, fake_api_key, transcription_service):
        resp = client.post(silos_url(fake_app.app_id), headers=api_headers(fake_api_key.key), json={
            "name": "Videos", "video_ai_service_id": transcription_service.service_id,
        })
        assert resp.status_code == 422
        assert "does not support video" in resp.json()["detail"]

    def test_service_of_another_app_is_rejected(self, client, db, fake_app, fake_user, fake_api_key):
        from models.app import App

        other = App(name="Other", slug="other-media-app", owner_id=fake_user.user_id, agent_rate_limit=0,
                    max_file_size_mb=10)
        db.add(other)
        db.flush()
        foreign = _ai_service(db, other.app_id, "Foreign whisper")
        resp = client.post(silos_url(fake_app.app_id), headers=api_headers(fake_api_key.key), json={
            "name": "Videos", "transcription_service_id": foreign.service_id,
        })
        assert resp.status_code == 422

    def test_update_keeps_omitted_services_and_null_clears(self, client, fake_app, fake_api_key, media_silo,
                                                            transcription_service):
        url = silos_url(fake_app.app_id, media_silo.silo_id)
        kept = client.put(url, headers=api_headers(fake_api_key.key), json={"name": "Renamed"})
        assert kept.status_code == 200, kept.text
        assert kept.json()["silo"]["transcription_service_id"] == transcription_service.service_id

        cleared = client.put(url, headers=api_headers(fake_api_key.key),
                             json={"name": "Renamed", "transcription_service_id": None})
        assert cleared.json()["silo"]["transcription_service_id"] is None


class TestIndexMediaIntoSilo:
    def test_video_is_accepted_and_processed_in_background(self, client, db, fake_app, fake_api_key, media_silo,
                                                           media_folder, no_processing):
        resp = client.post(
            silos_url(fake_app.app_id, media_silo.silo_id, "docs/index-file"),
            headers=api_headers(fake_api_key.key),
            files={"file": ("demo.mp4", b"fake-video-bytes", "video/mp4")},
            data={"metadata": '{"source_system": "cms", "doc_id": "42"}', "forced_language": "es"},
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["num_documents"] == 0 and body["status"] == "pending"

        media = db.get(Media, body["media_id"])
        assert media.silo_id == media_silo.silo_id
        assert media.repository_id is None
        assert media.custom_metadata == {"source_system": "cms", "doc_id": "42"}
        assert media.forced_language == "es"
        assert media.file_path.startswith(str(media_folder / "silo_media" / str(media_silo.silo_id)))
        no_processing.assert_called_once_with(media.media_id)

    def test_silo_without_transcription_service_rejects_media(self, client, db, fake_app, fake_api_key,
                                                              media_silo, no_processing):
        media_silo.transcription_service_id = None
        db.flush()
        resp = client.post(
            silos_url(fake_app.app_id, media_silo.silo_id, "docs/index-file"),
            headers=api_headers(fake_api_key.key),
            files={"file": ("demo.mp3", b"fake-audio", "audio/mpeg")},
        )
        assert resp.status_code == 400
        assert "transcription" in resp.json()["detail"]
        no_processing.assert_not_called()

    def test_youtube(self, client, db, fake_app, fake_api_key, media_silo, no_processing):
        url = silos_url(fake_app.app_id, media_silo.silo_id, "media/youtube")
        payload = {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "metadata": {"topic": "demo"}}
        resp = client.post(url, headers=api_headers(fake_api_key.key), json=payload)
        assert resp.status_code == 202, resp.text
        media = db.get(Media, resp.json()["media_id"])
        assert media.source_type == "youtube" and media.custom_metadata == {"topic": "demo"}

        duplicate = client.post(url, headers=api_headers(fake_api_key.key), json=payload)
        assert duplicate.status_code == 400

    def test_status_list_and_delete(self, client, db, fake_app, fake_api_key, media_silo, no_processing):
        created = client.post(
            silos_url(fake_app.app_id, media_silo.silo_id, "docs/index-file"),
            headers=api_headers(fake_api_key.key),
            files={"file": ("demo.mp4", b"x", "video/mp4")},
        ).json()
        media_id = created["media_id"]
        media = db.get(Media, media_id)
        media.status, media.error_message = "error", "No speech was detected in the audio."
        db.flush()

        status_resp = client.get(silos_url(fake_app.app_id, media_silo.silo_id, f"media/{media_id}"),
                                 headers=api_headers(fake_api_key.key))
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "error"
        assert "No speech" in status_resp.json()["error_message"]

        listed = client.get(silos_url(fake_app.app_id, media_silo.silo_id, "media"),
                            headers=api_headers(fake_api_key.key)).json()["media"]
        assert [m["media_id"] for m in listed] == [media_id]

        with patch("services.silo_service.SiloService.delete_media"):
            deleted = client.delete(silos_url(fake_app.app_id, media_silo.silo_id, f"media/{media_id}"),
                                    headers=api_headers(fake_api_key.key))
        assert deleted.status_code == 200
        assert db.get(Media, media_id) is None

    def test_media_of_another_silo_is_not_found(self, client, db, fake_app, fake_api_key, media_silo,
                                                embedding_service, no_processing):
        from models.silo import Silo

        other = Silo(name="Other", app_id=fake_app.app_id, silo_type="CUSTOM", status="active",
                     embedding_service_id=embedding_service.service_id)
        db.add(other)
        db.flush()
        media = Media(name="m", silo_id=other.silo_id, source_type="upload", status="ready")
        db.add(media)
        db.flush()
        resp = client.get(silos_url(fake_app.app_id, media_silo.silo_id, f"media/{media.media_id}"),
                          headers=api_headers(fake_api_key.key))
        assert resp.status_code == 404

    def test_documents_are_still_indexed_synchronously(self, client, fake_app, fake_api_key, media_silo):
        with patch("services.silo_service.SiloService.index_multiple_content") as index:
            resp = client.post(
                silos_url(fake_app.app_id, media_silo.silo_id, "docs/index-file"),
                headers=api_headers(fake_api_key.key),
                files={"file": ("notes.txt", b"hello world", "text/plain")},
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["media_id"] is None
        index.assert_called_once()


class TestRepositoryStoresMediaServicesOnSilo:
    def test_repository_create_and_update(self, db, fake_app, embedding_service, transcription_service,
                                          video_service, media_folder, monkeypatch):
        import services.repository_service as repository_service
        from schemas.repository_schemas import CreateRepositorySchema, UpdateRepositorySchema
        from services.repository_service import RepositoryService

        monkeypatch.setattr(repository_service, "REPO_BASE_FOLDER", str(media_folder))
        repo = RepositoryService.create_repository_router(fake_app.app_id, CreateRepositorySchema(
            name="Videos repo", embedding_service_id=embedding_service.service_id,
            transcription_service_id=transcription_service.service_id, video_ai_service_id=video_service.service_id,
        ), db)
        assert repo.silo.transcription_service_id == transcription_service.service_id
        assert repo.silo.video_ai_service_id == video_service.service_id
        assert repo.transcription_service_id == transcription_service.service_id  # read through the silo

        RepositoryService.update_repository_router(fake_app.app_id, repo.repository_id, UpdateRepositorySchema(
            name="Videos repo", transcription_service_id=transcription_service.service_id,
        ), db)
        db.refresh(repo.silo)
        assert repo.silo.video_ai_service_id is None
        assert repo.silo.transcription_service_id == transcription_service.service_id

        detail = RepositoryService.get_repository_detail(fake_app.app_id, repo.repository_id, db)
        assert detail.transcription_service_id == transcription_service.service_id
