"""
Tests for public API files router.
Covers: attach_file, detach_file, list_attached_files, download_file.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from routers.public.v1 import files as files_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_auth(mocker):
    mocker.patch.object(files_module, "validate_api_key_for_app", return_value=None)
    agent = MagicMock()
    agent.has_memory = False
    agent.app_id = 1
    mocker.patch.object(
        files_module, "validate_agent_ownership", return_value=agent
    )
    return agent


def _mock_file_service(mocker):
    mock_cls = mocker.patch.object(files_module, "FileManagementService")
    svc = mock_cls.return_value
    return svc


def _mock_file_ref():
    ref = MagicMock()
    ref.file_id = "file_123"
    ref.filename = "test.pdf"
    ref.file_type = "pdf"
    ref.file_size_bytes = 1024
    ref.processing_status = "ready"
    ref.content_preview = "content..."
    ref.has_extractable_content = True
    ref.mime_type = "application/pdf"
    return ref


# ---------------------------------------------------------------------------
# TestAttachFile
# ---------------------------------------------------------------------------

class TestAttachFile:
    @pytest.mark.asyncio
    async def test_happy_path(self, mocker):
        _patch_auth(mocker)
        file_svc = _mock_file_service(mocker)
        file_ref = _mock_file_ref()
        file_svc.upload_file = AsyncMock(return_value=file_ref)
        mocker.patch.object(
            files_module.FileReference, "format_file_size", return_value="1.0 KB"
        )

        upload_file = MagicMock()
        upload_file.filename = "test.pdf"

        result = await files_module.attach_file(
            app_id=1, agent_id=1, file=upload_file,
            conversation_id=None, api_key="key", db=MagicMock(),
        )
        assert result.success is True
        assert result.file_id == "file_123"

    @pytest.mark.asyncio
    async def test_agent_not_found(self, mocker):
        mocker.patch.object(files_module, "validate_api_key_for_app")
        mocker.patch.object(
            files_module,
            "validate_agent_ownership",
            side_effect=HTTPException(status_code=404, detail="Agent not found"),
        )

        with pytest.raises(HTTPException) as exc_info:
            await files_module.attach_file(
                app_id=1, agent_id=999, file=MagicMock(),
                conversation_id=None, api_key="key", db=MagicMock(),
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_agent_wrong_app_id(self, mocker):
        mocker.patch.object(files_module, "validate_api_key_for_app")
        mocker.patch.object(
            files_module,
            "validate_agent_ownership",
            side_effect=HTTPException(status_code=404, detail="Agent not found"),
        )

        with pytest.raises(HTTPException) as exc_info:
            await files_module.attach_file(
                app_id=2, agent_id=1, file=MagicMock(),
                conversation_id=None, api_key="key", db=MagicMock(),
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_auto_creates_conversation_for_memory_agents(self, mocker):
        agent = _patch_auth(mocker)
        agent.has_memory = True

        conv = MagicMock()
        conv.conversation_id = 42
        mocker.patch.object(
            files_module.ConversationService,
            "create_conversation",
            return_value=conv,
        )

        file_svc = _mock_file_service(mocker)
        file_ref = _mock_file_ref()
        file_svc.upload_file = AsyncMock(return_value=file_ref)
        mocker.patch.object(
            files_module.FileReference, "format_file_size", return_value="1.0 KB"
        )

        result = await files_module.attach_file(
            app_id=1, agent_id=1, file=MagicMock(filename="test.pdf"),
            conversation_id=None, api_key="key", db=MagicMock(),
        )
        assert result.conversation_id == "42"
        files_module.ConversationService.create_conversation.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_does_not_leak(self, mocker):
        _patch_auth(mocker)
        file_svc = _mock_file_service(mocker)
        file_svc.upload_file = AsyncMock(side_effect=RuntimeError("disk full /dev/sda1"))

        with pytest.raises(HTTPException) as exc_info:
            await files_module.attach_file(
                app_id=1, agent_id=1, file=MagicMock(filename="test.pdf"),
                conversation_id=None, api_key="key", db=MagicMock(),
            )
        assert exc_info.value.status_code == 500
        assert "disk" not in exc_info.value.detail
        assert exc_info.value.detail == "Failed to attach file"


# ---------------------------------------------------------------------------
# TestDetachFile
# ---------------------------------------------------------------------------

class TestDetachFile:
    @pytest.mark.asyncio
    async def test_happy_path(self, mocker):
        _patch_auth(mocker)
        file_svc = _mock_file_service(mocker)
        file_svc.remove_file = AsyncMock(return_value=True)

        result = await files_module.detach_file(
            app_id=1, agent_id=1, file_id="f1",
            conversation_id=None, api_key="key", db=MagicMock(),
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_agent_ownership_validated(self, mocker):
        mocker.patch.object(files_module, "validate_api_key_for_app")
        mocker.patch.object(
            files_module,
            "validate_agent_ownership",
            side_effect=HTTPException(status_code=404, detail="Agent not found"),
        )

        with pytest.raises(HTTPException) as exc_info:
            await files_module.detach_file(
                app_id=1, agent_id=999, file_id="f1",
                conversation_id=None, api_key="key", db=MagicMock(),
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_file_not_found_returns_false(self, mocker):
        _patch_auth(mocker)
        file_svc = _mock_file_service(mocker)
        file_svc.remove_file = AsyncMock(return_value=False)

        result = await files_module.detach_file(
            app_id=1, agent_id=1, file_id="nonexistent",
            conversation_id=None, api_key="key", db=MagicMock(),
        )
        assert result.success is False


# ---------------------------------------------------------------------------
# TestListAttachedFiles
# ---------------------------------------------------------------------------

class TestListAttachedFiles:
    @pytest.mark.asyncio
    async def test_happy_path(self, mocker):
        _patch_auth(mocker)
        file_svc = _mock_file_service(mocker)
        file_svc.list_attached_files = AsyncMock(return_value=[
            {
                "file_id": "f1",
                "filename": "test.pdf",
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
        ])
        mocker.patch.object(
            files_module.FileReference, "format_file_size", return_value="1.0 KB"
        )

        result = await files_module.list_attached_files(
            app_id=1, agent_id=1, conversation_id=None,
            api_key="key", db=MagicMock(),
        )
        assert len(result.files) == 1
        assert result.total_size_bytes == 1024

    @pytest.mark.asyncio
    async def test_agent_ownership_validated(self, mocker):
        mocker.patch.object(files_module, "validate_api_key_for_app")
        mocker.patch.object(
            files_module,
            "validate_agent_ownership",
            side_effect=HTTPException(status_code=404, detail="Agent not found"),
        )

        with pytest.raises(HTTPException) as exc_info:
            await files_module.list_attached_files(
                app_id=1, agent_id=999, conversation_id=None,
                api_key="key", db=MagicMock(),
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_empty_list(self, mocker):
        _patch_auth(mocker)
        file_svc = _mock_file_service(mocker)
        file_svc.list_attached_files = AsyncMock(return_value=[])
        mocker.patch.object(
            files_module.FileReference, "format_file_size", return_value="0 B"
        )

        result = await files_module.list_attached_files(
            app_id=1, agent_id=1, conversation_id=None,
            api_key="key", db=MagicMock(),
        )
        assert result.files == []
        assert result.total_size_bytes == 0


# ---------------------------------------------------------------------------
# TestDownloadFile
# ---------------------------------------------------------------------------

class TestDownloadFile:
    @pytest.mark.asyncio
    async def test_happy_path(self, mocker):
        _patch_auth(mocker)
        file_svc = _mock_file_service(mocker)
        file_svc.list_attached_files = AsyncMock(return_value=[
            {"file_id": "f1", "file_path": "/data/tmp/test.pdf", "filename": "test.pdf"}
        ])
        mocker.patch.object(
            files_module, "generate_signature", return_value="sig123"
        )

        request = MagicMock()
        request.base_url = "http://localhost:8000/"
        mocker.patch.dict("os.environ", {"AICT_BASE_URL": ""})

        result = await files_module.download_file(
            app_id=1, agent_id=1, file_id="f1", request=request,
            conversation_id=None, api_key="key", db=MagicMock(),
        )
        assert result.filename == "test.pdf"
        assert "static/" in result.download_url
        assert "sig=sig123" in result.download_url

    @pytest.mark.asyncio
    async def test_file_not_found(self, mocker):
        _patch_auth(mocker)
        file_svc = _mock_file_service(mocker)
        file_svc.list_attached_files = AsyncMock(return_value=[])

        request = MagicMock()
        request.base_url = "http://localhost:8000/"

        with pytest.raises(HTTPException) as exc_info:
            await files_module.download_file(
                app_id=1, agent_id=1, file_id="nonexistent", request=request,
                conversation_id=None, api_key="key", db=MagicMock(),
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_agent_ownership_validated(self, mocker):
        mocker.patch.object(files_module, "validate_api_key_for_app")
        mocker.patch.object(
            files_module,
            "validate_agent_ownership",
            side_effect=HTTPException(status_code=404, detail="Agent not found"),
        )

        request = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await files_module.download_file(
                app_id=1, agent_id=999, file_id="f1", request=request,
                conversation_id=None, api_key="key", db=MagicMock(),
            )
        assert exc_info.value.status_code == 404
