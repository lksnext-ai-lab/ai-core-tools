"""
Integration tests for public API file endpoints.

File storage (upload/download) is mocked — these tests validate
the HTTP layer: routing, status codes, auth, and Pydantic serialization.
"""

import io
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def files_url(app_id: int, agent_id: int, path: str = "") -> str:
    return f"/public/v1/app/{app_id}/files/{agent_id}{path}"


def api_headers(key: str) -> dict:
    return {"X-API-KEY": key}


def mock_file_ref():
    ref = MagicMock()
    ref.file_id = "file_integration_123"
    ref.filename = "test.pdf"
    ref.file_type = "pdf"
    ref.file_size_bytes = 2048
    ref.processing_status = "ready"
    ref.content_preview = "Sample content..."
    ref.has_extractable_content = True
    ref.mime_type = "application/pdf"
    return ref


# ---------------------------------------------------------------------------
# Attach file
# ---------------------------------------------------------------------------


class TestAttachFile:
    def test_attach_file_returns_200(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        file_ref = mock_file_ref()

        with patch(
            "services.file_management_service.FileManagementService.upload_file",
            new=AsyncMock(return_value=file_ref),
        ), patch(
            "services.file_management_service.FileReference.format_file_size",
            return_value="2.0 KB",
        ):
            resp = client.post(
                files_url(fake_app.app_id, fake_agent.agent_id, "/attach-file"),
                files={"file": ("test.pdf", io.BytesIO(b"fake pdf content"), "application/pdf")},
                headers=api_headers(fake_api_key.key),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["file_id"] == "file_integration_123"
        assert data["filename"] == "test.pdf"
        assert data["file_type"] == "pdf"
        assert data["processing_status"] == "ready"

    def test_agent_wrong_app_returns_404(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        other_app_id = fake_app.app_id + 1000
        resp = client.post(
            files_url(other_app_id, fake_agent.agent_id, "/attach-file"),
            files={"file": ("test.pdf", io.BytesIO(b"data"), "application/pdf")},
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code in (401, 403, 404)

    def test_error_does_not_leak_internal_details(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        with patch(
            "services.file_management_service.FileManagementService.upload_file",
            new=AsyncMock(side_effect=RuntimeError("disk full /dev/sda1")),
        ):
            resp = client.post(
                files_url(fake_app.app_id, fake_agent.agent_id, "/attach-file"),
                files={"file": ("test.pdf", io.BytesIO(b"data"), "application/pdf")},
                headers=api_headers(fake_api_key.key),
            )

        assert resp.status_code == 500
        assert "disk" not in resp.json()["detail"]
        assert resp.json()["detail"] == "Failed to attach file"


# ---------------------------------------------------------------------------
# Detach file
# ---------------------------------------------------------------------------


class TestDetachFile:
    def test_detach_returns_success(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        with patch(
            "services.file_management_service.FileManagementService.remove_file",
            new=AsyncMock(return_value=True),
        ):
            resp = client.delete(
                files_url(fake_app.app_id, fake_agent.agent_id, "/detach-file/f1"),
                headers=api_headers(fake_api_key.key),
            )

        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_detach_not_found_returns_false(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        with patch(
            "services.file_management_service.FileManagementService.remove_file",
            new=AsyncMock(return_value=False),
        ):
            resp = client.delete(
                files_url(fake_app.app_id, fake_agent.agent_id, "/detach-file/nonexistent"),
                headers=api_headers(fake_api_key.key),
            )

        assert resp.status_code == 200
        assert resp.json()["success"] is False


# ---------------------------------------------------------------------------
# List attached files
# ---------------------------------------------------------------------------


class TestListAttachedFiles:
    def test_list_returns_200(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        files_data = [
            {
                "file_id": "f1",
                "filename": "doc.pdf",
                "file_type": "pdf",
                "uploaded_at": None,
                "file_size_bytes": 1024,
                "file_size_display": "1.0 KB",
                "processing_status": "ready",
                "content_preview": None,
                "has_extractable_content": True,
                "mime_type": "application/pdf",
                "conversation_id": None,
            }
        ]

        with patch(
            "services.file_management_service.FileManagementService"
            ".list_attached_files",
            new=AsyncMock(return_value=files_data),
        ), patch(
            "services.file_management_service.FileReference.format_file_size",
            return_value="1.0 KB",
        ):
            resp = client.get(
                files_url(fake_app.app_id, fake_agent.agent_id, "/attached-files"),
                headers=api_headers(fake_api_key.key),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["files"]) == 1
        assert data["total_size_bytes"] == 1024

    def test_empty_list_returns_200(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        with patch(
            "services.file_management_service.FileManagementService"
            ".list_attached_files",
            new=AsyncMock(return_value=[]),
        ), patch(
            "services.file_management_service.FileReference.format_file_size",
            return_value="0 B",
        ):
            resp = client.get(
                files_url(fake_app.app_id, fake_agent.agent_id, "/attached-files"),
                headers=api_headers(fake_api_key.key),
            )

        assert resp.status_code == 200
        assert resp.json()["files"] == []
        assert resp.json()["total_size_bytes"] == 0


# ---------------------------------------------------------------------------
# Download file
# ---------------------------------------------------------------------------


class TestDownloadFile:
    def test_download_returns_200(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        files_data = [
            {"file_id": "f1", "file_path": "/data/tmp/test.pdf", "filename": "test.pdf"}
        ]

        with patch(
            "services.file_management_service.FileManagementService"
            ".list_attached_files",
            new=AsyncMock(return_value=files_data),
        ), patch(
            "routers.public.v1.files.generate_signature",
            return_value="sig_test_123",
        ), patch.dict("os.environ", {"AICT_BASE_URL": ""}):
            resp = client.get(
                files_url(fake_app.app_id, fake_agent.agent_id, "/files/f1/download"),
                headers=api_headers(fake_api_key.key),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["filename"] == "test.pdf"
        assert "download_url" in data
        assert "sig=sig_test_123" in data["download_url"]

    def test_file_not_found_returns_404(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        with patch(
            "services.file_management_service.FileManagementService"
            ".list_attached_files",
            new=AsyncMock(return_value=[]),
        ):
            resp = client.get(
                files_url(fake_app.app_id, fake_agent.agent_id, "/files/nonexistent/download"),
                headers=api_headers(fake_api_key.key),
            )

        assert resp.status_code == 404
