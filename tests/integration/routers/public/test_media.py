"""
Integration tests for public API media endpoints.

Uses the shared test infrastructure (TestClient, transactional DB, real API key).
Service-level operations that touch the filesystem, background tasks, or external
services (YouTube, Whisper) are mocked.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def media_url(app_id: int, repo_id: int, suffix: str = "") -> str:
    base = f"/public/v1/app/{app_id}/repositories/{repo_id}/media"
    return f"{base}{suffix}"


def api_headers(key: str) -> dict:
    return {"X-API-KEY": key}


# ---------------------------------------------------------------------------
# Fixtures (test-local, no conftest changes)
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_silo(db, fake_app):
    from models.silo import Silo

    silo = Silo(
        name="Test Silo",
        description="Silo for test repository",
        status="active",
        silo_type="REPO",
        app_id=fake_app.app_id,
        vector_db_type="PGVECTOR",
    )
    db.add(silo)
    db.flush()
    return silo


@pytest.fixture
def fake_repository(db, fake_app, fake_silo):
    from models.repository import Repository

    repo = Repository(
        name="Test Repository",
        type="default",
        status="active",
        app_id=fake_app.app_id,
        silo_id=fake_silo.silo_id,
        create_date=datetime.now(),
    )
    db.add(repo)
    db.flush()
    return repo


@pytest.fixture
def fake_ai_transcription_service(db, fake_app):
    from models.ai_service import AIService

    svc = AIService(
        name="Test Whisper Service",
        provider="OpenAI",
        api_key="sk-test-whisper-key",  # pragma: allowlist secret
        app_id=fake_app.app_id,
    )
    db.add(svc)
    db.flush()
    return svc


@pytest.fixture
def fake_media(db, fake_repository, fake_ai_transcription_service):
    from models.media import Media

    media = Media(
        name="test_video",
        repository_id=fake_repository.repository_id,
        transcription_service_id=fake_ai_transcription_service.service_id,
        source_type="upload",
        status="completed",
        create_date=datetime.now(),
    )
    db.add(media)
    db.flush()
    return media


@pytest.fixture
def fake_youtube_media(db, fake_repository, fake_ai_transcription_service):
    from models.media import Media

    media = Media(
        name="YouTube: test_video",
        repository_id=fake_repository.repository_id,
        transcription_service_id=fake_ai_transcription_service.service_id,
        source_type="youtube",
        source_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        status="completed",
        create_date=datetime.now(),
    )
    db.add(media)
    db.flush()
    return media


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestMediaAuth:
    def test_no_api_key_returns_401(self, client, fake_app, fake_repository):
        resp = client.get(media_url(fake_app.app_id, fake_repository.repository_id))
        assert resp.status_code == 401

    def test_invalid_api_key_returns_401(self, client, fake_app, fake_repository):
        resp = client.get(
            media_url(fake_app.app_id, fake_repository.repository_id),
            headers=api_headers("totally-invalid-key"),
        )
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# List media
# ---------------------------------------------------------------------------


class TestListMedia:
    def test_returns_200_with_media(
        self, client, fake_app, fake_repository, fake_media, fake_api_key, db
    ):
        resp = client.get(
            media_url(fake_app.app_id, fake_repository.repository_id),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "media" in data
        assert len(data["media"]) >= 1

        media_data = data["media"][0]
        assert "media_id" in media_data
        assert "name" in media_data
        assert "source_type" in media_data
        assert "status" in media_data
        assert "repository_id" in media_data
        # Internal fields should NOT be exposed
        assert "file_path" not in media_data
        assert "error_message" not in media_data

    def test_empty_repo_returns_empty_list(
        self, client, fake_app, fake_repository, fake_api_key, db
    ):
        """Repository with no media returns empty list."""
        resp = client.get(
            media_url(fake_app.app_id, fake_repository.repository_id),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        assert resp.json()["media"] == []

    def test_nonexistent_repo_returns_404(
        self, client, fake_app, fake_api_key, db
    ):
        resp = client.get(
            media_url(fake_app.app_id, 999999),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 404

    def test_youtube_media_has_source_url(
        self, client, fake_app, fake_repository, fake_youtube_media, fake_api_key, db
    ):
        resp = client.get(
            media_url(fake_app.app_id, fake_repository.repository_id),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        data = resp.json()
        youtube_items = [m for m in data["media"] if m["source_type"] == "youtube"]
        assert len(youtube_items) >= 1
        assert youtube_items[0]["source_url"] is not None


# ---------------------------------------------------------------------------
# Upload media
# ---------------------------------------------------------------------------


class TestUploadMedia:
    def test_upload_returns_201(
        self, client, fake_app, fake_repository, fake_ai_transcription_service, fake_api_key, db
    ):
        with patch(
            "routers.public.v1.repositories.MediaService.upload_media_files",
            new_callable=AsyncMock,
        ) as mock_upload:
            from models.media import Media

            mock_media = Media(
                media_id=9999,
                name="test_audio",
                repository_id=fake_repository.repository_id,
                transcription_service_id=fake_ai_transcription_service.service_id,
                source_type="upload",
                status="pending",
                create_date=datetime.now(),
            )
            mock_upload.return_value = ([mock_media], [])

            import io

            fake_file = io.BytesIO(b"fake audio content")
            resp = client.post(
                media_url(fake_app.app_id, fake_repository.repository_id),
                files={"files": ("test.mp3", fake_file, "audio/mpeg")},
                data={"transcription_service_id": str(fake_ai_transcription_service.service_id)},
                headers=api_headers(fake_api_key.key),
            )
            assert resp.status_code == 201
            data = resp.json()
            assert "created_media" in data
            assert len(data["created_media"]) == 1
            assert data["created_media"][0]["name"] == "test_audio"

    def test_upload_to_nonexistent_repo_returns_404(
        self, client, fake_app, fake_api_key, db
    ):
        import io

        fake_file = io.BytesIO(b"fake content")
        resp = client.post(
            media_url(fake_app.app_id, 999999),
            files={"files": ("test.mp3", fake_file, "audio/mpeg")},
            data={"transcription_service_id": "1"},
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 404

    def test_upload_with_partial_failures(
        self, client, fake_app, fake_repository, fake_ai_transcription_service, fake_api_key, db
    ):
        with patch(
            "routers.public.v1.repositories.MediaService.upload_media_files",
            new_callable=AsyncMock,
        ) as mock_upload:
            from models.media import Media

            mock_media = Media(
                media_id=9998,
                name="good_file",
                repository_id=fake_repository.repository_id,
                transcription_service_id=fake_ai_transcription_service.service_id,
                source_type="upload",
                status="pending",
                create_date=datetime.now(),
            )
            mock_upload.return_value = (
                [mock_media],
                [{"filename": "bad.txt", "error": "Unsupported file type"}],
            )

            import io

            resp = client.post(
                media_url(fake_app.app_id, fake_repository.repository_id),
                files={"files": ("good.mp3", io.BytesIO(b"data"), "audio/mpeg")},
                data={"transcription_service_id": str(fake_ai_transcription_service.service_id)},
                headers=api_headers(fake_api_key.key),
            )
            assert resp.status_code == 201
            data = resp.json()
            assert len(data["created_media"]) == 1
            assert len(data["failed_files"]) == 1


# ---------------------------------------------------------------------------
# YouTube
# ---------------------------------------------------------------------------


class TestYouTubeMedia:
    def test_add_youtube_returns_201(
        self, client, fake_app, fake_repository, fake_ai_transcription_service, fake_api_key, db
    ):
        with patch(
            "routers.public.v1.repositories.MediaService.create_media_from_youtube",
            new_callable=AsyncMock,
        ) as mock_yt:
            from models.media import Media

            mock_media = Media(
                media_id=8888,
                name="YouTube: test_video",
                repository_id=fake_repository.repository_id,
                transcription_service_id=fake_ai_transcription_service.service_id,
                source_type="youtube",
                source_url="https://www.youtube.com/watch?v=abc123",
                status="pending",
                create_date=datetime.now(),
            )
            mock_yt.return_value = mock_media

            resp = client.post(
                media_url(fake_app.app_id, fake_repository.repository_id, "/youtube"),
                json={
                    "url": "https://www.youtube.com/watch?v=abc123",
                    "transcription_service_id": fake_ai_transcription_service.service_id,
                },
                headers=api_headers(fake_api_key.key),
            )
            assert resp.status_code == 201
            data = resp.json()
            assert "media" in data
            assert data["media"]["source_type"] == "youtube"
            assert data["media"]["source_url"] == "https://www.youtube.com/watch?v=abc123"

    def test_invalid_url_returns_400(
        self, client, fake_app, fake_repository, fake_ai_transcription_service, fake_api_key, db
    ):
        with patch(
            "routers.public.v1.repositories.MediaService.create_media_from_youtube",
            new_callable=AsyncMock,
            side_effect=ValueError("Invalid YouTube URL"),
        ):
            resp = client.post(
                media_url(fake_app.app_id, fake_repository.repository_id, "/youtube"),
                json={
                    "url": "https://not-youtube.com/video",
                    "transcription_service_id": fake_ai_transcription_service.service_id,
                },
                headers=api_headers(fake_api_key.key),
            )
            assert resp.status_code == 400
            assert "Invalid YouTube URL" in resp.json()["detail"]

    def test_duplicate_url_returns_400(
        self, client, fake_app, fake_repository, fake_ai_transcription_service, fake_api_key, db
    ):
        with patch(
            "routers.public.v1.repositories.MediaService.create_media_from_youtube",
            new_callable=AsyncMock,
            side_effect=ValueError("This YouTube URL already exists in this repository"),
        ):
            resp = client.post(
                media_url(fake_app.app_id, fake_repository.repository_id, "/youtube"),
                json={
                    "url": "https://www.youtube.com/watch?v=duplicate",
                    "transcription_service_id": fake_ai_transcription_service.service_id,
                },
                headers=api_headers(fake_api_key.key),
            )
            assert resp.status_code == 400

    def test_youtube_to_nonexistent_repo_returns_404(
        self, client, fake_app, fake_api_key, db
    ):
        resp = client.post(
            media_url(fake_app.app_id, 999999, "/youtube"),
            json={
                "url": "https://www.youtube.com/watch?v=abc123",
                "transcription_service_id": 1,
            },
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 404

    def test_missing_required_fields_returns_422(
        self, client, fake_app, fake_repository, fake_api_key, db
    ):
        resp = client.post(
            media_url(fake_app.app_id, fake_repository.repository_id, "/youtube"),
            json={"url": "https://www.youtube.com/watch?v=abc123"},
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Get media status
# ---------------------------------------------------------------------------


class TestGetMediaStatus:
    def test_returns_200_with_detail(
        self, client, fake_app, fake_repository, fake_media, fake_api_key, db
    ):
        resp = client.get(
            media_url(
                fake_app.app_id,
                fake_repository.repository_id,
                f"/{fake_media.media_id}",
            ),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "media" in data
        media = data["media"]
        assert media["media_id"] == fake_media.media_id
        assert media["name"] == fake_media.name
        assert media["status"] == fake_media.status
        assert "file_path" not in media
        assert "error_message" not in media

    def test_nonexistent_returns_404(
        self, client, fake_app, fake_repository, fake_api_key, db
    ):
        resp = client.get(
            media_url(fake_app.app_id, fake_repository.repository_id, "/999999"),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 404

    def test_idor_cross_repo_returns_404(
        self, client, fake_app, fake_repository, fake_media, fake_api_key, db
    ):
        """Accessing media via wrong repo_id should return 404."""
        from models.repository import Repository
        from models.silo import Silo

        silo2 = Silo(
            name="Other Silo", description="Other", status="active",
            silo_type="REPO", app_id=fake_app.app_id, vector_db_type="PGVECTOR",
        )
        db.add(silo2)
        db.flush()

        other_repo = Repository(
            name="Other Repo", type="default", status="active",
            app_id=fake_app.app_id, silo_id=silo2.silo_id, create_date=datetime.now(),
        )
        db.add(other_repo)
        db.flush()

        resp = client.get(
            media_url(fake_app.app_id, other_repo.repository_id, f"/{fake_media.media_id}"),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Move media
# ---------------------------------------------------------------------------


class TestMoveMedia:
    def test_move_returns_200(
        self, client, fake_app, fake_repository, fake_media, fake_api_key, db
    ):
        with patch(
            "routers.public.v1.repositories.MediaService.move_media_to_folder"
        ) as mock_move:
            mock_move.return_value = {"success": True, "message": "Media moved successfully"}

            resp = client.post(
                media_url(
                    fake_app.app_id,
                    fake_repository.repository_id,
                    f"/{fake_media.media_id}/move",
                ),
                data={"new_folder_id": "5"},
                headers=api_headers(fake_api_key.key),
            )
            assert resp.status_code == 200
            assert "moved" in resp.json()["message"].lower()

    def test_move_nonexistent_returns_404(
        self, client, fake_app, fake_repository, fake_api_key, db
    ):
        resp = client.post(
            media_url(fake_app.app_id, fake_repository.repository_id, "/999999/move"),
            data={"new_folder_id": "1"},
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 404

    def test_move_invalid_folder_returns_400(
        self, client, fake_app, fake_repository, fake_media, fake_api_key, db
    ):
        with patch(
            "routers.public.v1.repositories.MediaService.move_media_to_folder",
            side_effect=ValueError("Folder 999 does not belong to repository"),
        ):
            resp = client.post(
                media_url(
                    fake_app.app_id,
                    fake_repository.repository_id,
                    f"/{fake_media.media_id}/move",
                ),
                data={"new_folder_id": "999"},
                headers=api_headers(fake_api_key.key),
            )
            assert resp.status_code == 400

    def test_move_error_does_not_leak_details(
        self, client, fake_app, fake_repository, fake_media, fake_api_key, db
    ):
        with patch(
            "routers.public.v1.repositories.MediaService.move_media_to_folder",
            side_effect=RuntimeError("shutil.move: permission denied /mnt/data"),
        ):
            resp = client.post(
                media_url(
                    fake_app.app_id,
                    fake_repository.repository_id,
                    f"/{fake_media.media_id}/move",
                ),
                data={"new_folder_id": "1"},
                headers=api_headers(fake_api_key.key),
            )
            assert resp.status_code == 500
            detail = resp.json()["detail"]
            assert "shutil" not in detail
            assert "permission denied" not in detail


# ---------------------------------------------------------------------------
# Delete media
# ---------------------------------------------------------------------------


class TestDeleteMedia:
    def test_delete_returns_200(
        self, client, fake_app, fake_repository, fake_media, fake_api_key, db
    ):
        with patch(
            "routers.public.v1.repositories.MediaService.delete_media"
        ) as mock_delete:
            mock_delete.return_value = True

            resp = client.delete(
                media_url(
                    fake_app.app_id,
                    fake_repository.repository_id,
                    f"/{fake_media.media_id}",
                ),
                headers=api_headers(fake_api_key.key),
            )
            assert resp.status_code == 200
            assert "deleted" in resp.json()["message"].lower()

    def test_delete_nonexistent_returns_404(
        self, client, fake_app, fake_repository, fake_api_key, db
    ):
        resp = client.delete(
            media_url(fake_app.app_id, fake_repository.repository_id, "/999999"),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 404

    def test_delete_idor_cross_repo_returns_404(
        self, client, fake_app, fake_repository, fake_media, fake_api_key, db
    ):
        """Deleting media via wrong repo_id should return 404."""
        from models.repository import Repository
        from models.silo import Silo

        silo2 = Silo(
            name="Other Silo",
            description="Other",
            status="active",
            silo_type="REPO",
            app_id=fake_app.app_id,
            vector_db_type="PGVECTOR",
        )
        db.add(silo2)
        db.flush()

        other_repo = Repository(
            name="Other Repo",
            type="default",
            status="active",
            app_id=fake_app.app_id,
            silo_id=silo2.silo_id,
            create_date=datetime.now(),
        )
        db.add(other_repo)
        db.flush()

        # Try deleting fake_media via other_repo — should fail
        resp = client.delete(
            media_url(
                fake_app.app_id,
                other_repo.repository_id,
                f"/{fake_media.media_id}",
            ),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Error leakage
# ---------------------------------------------------------------------------


class TestErrorLeakage:
    def test_upload_error_does_not_leak_details(
        self, client, fake_app, fake_repository, fake_api_key, db
    ):
        """Internal errors should return generic messages, not stack traces."""
        with patch(
            "routers.public.v1.repositories.MediaService.upload_media_files",
            new_callable=AsyncMock,
            side_effect=RuntimeError("disk full /dev/sda1 connection refused pg_hba.conf"),
        ):
            import io

            fake_file = io.BytesIO(b"content")
            resp = client.post(
                media_url(fake_app.app_id, fake_repository.repository_id),
                files={"files": ("test.mp3", fake_file, "audio/mpeg")},
                data={"transcription_service_id": "1"},
                headers=api_headers(fake_api_key.key),
            )
            assert resp.status_code == 500
            detail = resp.json()["detail"]
            assert "disk full" not in detail
            assert "pg_hba" not in detail

    def test_delete_error_does_not_leak_details(
        self, client, fake_app, fake_repository, fake_media, fake_api_key, db
    ):
        with patch(
            "routers.public.v1.repositories.MediaService.delete_media",
            side_effect=RuntimeError("FATAL: database connection pool exhausted"),
        ):
            resp = client.delete(
                media_url(
                    fake_app.app_id,
                    fake_repository.repository_id,
                    f"/{fake_media.media_id}",
                ),
                headers=api_headers(fake_api_key.key),
            )
            assert resp.status_code == 500
            detail = resp.json()["detail"]
            assert "FATAL" not in detail
            assert "pool exhausted" not in detail

    def test_youtube_error_does_not_leak_details(
        self, client, fake_app, fake_repository, fake_api_key, db
    ):
        with patch(
            "routers.public.v1.repositories.MediaService.create_media_from_youtube",
            new_callable=AsyncMock,
            side_effect=RuntimeError("ffmpeg crash: segfault at 0x7fff"),
        ):
            resp = client.post(
                media_url(fake_app.app_id, fake_repository.repository_id, "/youtube"),
                json={
                    "url": "https://www.youtube.com/watch?v=abc123",
                    "transcription_service_id": 1,
                },
                headers=api_headers(fake_api_key.key),
            )
            assert resp.status_code == 500
            detail = resp.json()["detail"]
            assert "ffmpeg" not in detail
            assert "segfault" not in detail
