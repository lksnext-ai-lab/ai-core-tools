"""Unit tests for SharePointSourceService and SharePointSyncService.

All external dependencies (DB, GraphClient, SiloService) are mocked.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

pytest.importorskip("mattin_sharepoint", reason="mattin-sharepoint plugin not installed")

from mattin_sharepoint.graph_client import GraphAuthError, GraphDeltaExpiredError
from mattin_sharepoint.schemas import SharePointSourceCreateRequest
from models.enums.sharepoint_sync_status import SharePointSyncStatus
from models.enums.sharepoint_file_status import SharePointFileStatus


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_source(**kwargs):
    """Create a minimal mock SharePointSource object."""
    source = MagicMock()
    source.id = kwargs.get("id", 1)
    source.app_id = kwargs.get("app_id", 10)
    source.silo_id = kwargs.get("silo_id", 5)
    source.name = kwargs.get("name", "Test Source")
    source.tenant_id = kwargs.get("tenant_id", "tenant-abc")
    source.client_id = kwargs.get("client_id", "client-abc")
    source.client_secret = kwargs.get("client_secret", "secret-abc")
    source.site_id = kwargs.get("site_id", "site-1")
    source.drive_id = kwargs.get("drive_id", "drive-1")
    source.last_delta_token = kwargs.get("last_delta_token", None)
    source.last_sync_status = kwargs.get("last_sync_status", SharePointSyncStatus.IDLE)
    source.file_extension_filters = kwargs.get("file_extension_filters", None)
    return source


def _make_file_item(item_id: str, name: str) -> dict:
    """Return a Graph API file item dict."""
    return {
        "id": item_id,
        "name": name,
        "file": {"mimeType": "application/pdf"},
        "webUrl": f"https://example.com/{name}",
        "parentReference": {"path": "/drives/drv/root"},
        "size": 1024,
        "lastModifiedDateTime": "2026-01-01T00:00:00Z",
    }


# ---------------------------------------------------------------------------
# TestSharePointSourceService — test-connection logic
# ---------------------------------------------------------------------------

class TestSharePointSourceService:
    @pytest.mark.asyncio
    async def test_test_connection_happy_path(self):
        from mattin_sharepoint.service import SharePointSourceService

        with patch("mattin_sharepoint.service.GraphClient") as mock_gc:
            mock_gc.get_token = AsyncMock(return_value="tok")
            mock_gc.verify_drive_access = AsyncMock(return_value={"id": "drive-1"})

            # Should not raise
            await SharePointSourceService._test_connection(
                "tenant", "client", "secret", site_id=None, drive_id="drive-1"
            )

        mock_gc.get_token.assert_awaited_once()
        mock_gc.verify_drive_access.assert_awaited_once_with("tok", "drive-1")

    @pytest.mark.asyncio
    async def test_test_connection_auth_failure_raises_graph_auth_error(self):
        from mattin_sharepoint.service import SharePointSourceService

        with patch("mattin_sharepoint.service.GraphClient") as mock_gc:
            mock_gc.get_token = AsyncMock(side_effect=GraphAuthError("bad creds"))

            with pytest.raises(GraphAuthError):
                await SharePointSourceService._test_connection(
                    "tenant", "client", "bad-secret", site_id=None, drive_id=None
                )

    @pytest.mark.asyncio
    async def test_test_connection_no_drive_skips_verify(self):
        from mattin_sharepoint.service import SharePointSourceService

        with patch("mattin_sharepoint.service.GraphClient") as mock_gc:
            mock_gc.get_token = AsyncMock(return_value="tok")
            mock_gc.verify_drive_access = AsyncMock()

            await SharePointSourceService._test_connection(
                "tenant", "client", "secret", site_id=None, drive_id=None
            )

        mock_gc.verify_drive_access.assert_not_awaited()


# ---------------------------------------------------------------------------
# TestSharePointSyncService — run_sync logic
# ---------------------------------------------------------------------------

class TestSharePointSyncService:
    """Tests for SharePointSyncService.run_sync()."""

    def _patch_sync_deps(
        self,
        source: MagicMock,
        items: list[dict],
        delta_token_out: str | None = "new-delta-token",
    ):
        """Return a context-manager stack of patches for the sync service dependencies."""
        patches = {
            "db": patch("mattin_sharepoint.service.SessionLocal"),
            "graph": patch("mattin_sharepoint.service.GraphClient"),
            "src_repo": patch("mattin_sharepoint.service.SharePointSourceRepository"),
            "file_repo": patch("mattin_sharepoint.service.SharePointFileRepository"),
            "silo_svc": patch("mattin_sharepoint.service.SiloService", create=True),
        }
        return patches

    @pytest.mark.asyncio
    async def test_first_run_indexes_files(self):
        """Initial sync with two file items should upsert both with INDEXED status."""
        source = _make_source(last_delta_token=None)
        items = [
            _make_file_item("i1", "doc1.pdf"),
            _make_file_item("i2", "doc2.pdf"),
        ]

        with (
            patch("db.database.SessionLocal") as mock_sl,
            patch("mattin_sharepoint.service.GraphClient") as mock_gc,
            patch("mattin_sharepoint.service.SharePointSourceRepository") as mock_src_repo,
            patch("mattin_sharepoint.service.SharePointFileRepository") as mock_file_repo,
            patch("services.silo_service.SiloService") as mock_silo_svc,
        ):
            # DB session
            mock_db = MagicMock()
            mock_sl.return_value = mock_db

            # Source fetch
            mock_src_repo.get_by_id = MagicMock(return_value=source)
            mock_src_repo.update = MagicMock(return_value=source)

            # Graph client
            mock_gc.get_token = AsyncMock(return_value="tok")
            mock_gc.delta_query = AsyncMock(return_value=(items, "new-delta"))
            mock_gc.download_file = AsyncMock()

            # SiloService
            mock_silo_svc.extract_documents_from_file = MagicMock(return_value=[
                MagicMock(page_content="content", metadata={})
            ])
            mock_silo_svc.index_multiple_content = MagicMock(return_value=["vec-id-1"])

            # FileRepository
            mock_file_repo.get_by_drive_item = MagicMock(return_value=None)
            mock_file_repo.upsert_by_drive_item = MagicMock()

            from mattin_sharepoint.service import SharePointSyncService
            await SharePointSyncService.run_sync(source.id)

        # Both files should have been upserted
        assert mock_file_repo.upsert_by_drive_item.call_count == 2
        # Source should be set to SUCCESS at the end
        final_call_args = mock_src_repo.update.call_args_list[-1]
        updated_source = final_call_args[0][0]
        assert updated_source.last_sync_status == SharePointSyncStatus.SUCCESS
        assert updated_source.last_delta_token == "new-delta"

    @pytest.mark.asyncio
    async def test_incremental_run_uses_existing_delta_token(self):
        """Sync with a stored delta token should pass it to delta_query."""
        existing_token = "https://graph.microsoft.com/v1.0/drives/drv/root/delta?token=xyz"
        source = _make_source(last_delta_token=existing_token)

        with (
            patch("db.database.SessionLocal") as mock_sl,
            patch("mattin_sharepoint.service.GraphClient") as mock_gc,
            patch("mattin_sharepoint.service.SharePointSourceRepository") as mock_src_repo,
            patch("mattin_sharepoint.service.SharePointFileRepository"),
            patch("services.silo_service.SiloService"),
        ):
            mock_db = MagicMock()
            mock_sl.return_value = mock_db
            mock_src_repo.get_by_id = MagicMock(return_value=source)
            mock_src_repo.update = MagicMock(return_value=source)
            mock_gc.get_token = AsyncMock(return_value="tok")
            mock_gc.delta_query = AsyncMock(return_value=([], "new-delta"))

            from mattin_sharepoint.service import SharePointSyncService
            await SharePointSyncService.run_sync(source.id)

        mock_gc.delta_query.assert_awaited_once_with("tok", source.drive_id, existing_token)

    @pytest.mark.asyncio
    async def test_deleted_items_remove_rows(self):
        """Items with 'deleted' key should trigger file row deletion."""
        source = _make_source()
        deleted_item = {"id": "i1", "name": "gone.pdf", "deleted": {}}
        existing_file = MagicMock()
        existing_file.id = 99
        existing_file.vector_doc_ids = []

        with (
            patch("db.database.SessionLocal") as mock_sl,
            patch("mattin_sharepoint.service.GraphClient") as mock_gc,
            patch("mattin_sharepoint.service.SharePointSourceRepository") as mock_src_repo,
            patch("mattin_sharepoint.service.SharePointFileRepository") as mock_file_repo,
            patch("services.silo_service.SiloService"),
        ):
            mock_sl.return_value = MagicMock()
            mock_src_repo.get_by_id = MagicMock(return_value=source)
            mock_src_repo.update = MagicMock(return_value=source)
            mock_gc.get_token = AsyncMock(return_value="tok")
            mock_gc.delta_query = AsyncMock(return_value=([deleted_item], None))
            mock_file_repo.get_by_drive_item = MagicMock(return_value=existing_file)
            mock_file_repo.delete_file = MagicMock()

            from mattin_sharepoint.service import SharePointSyncService
            await SharePointSyncService.run_sync(source.id)

        mock_file_repo.delete_file.assert_called_once_with(existing_file.id, mock_sl.return_value)

    @pytest.mark.asyncio
    async def test_per_file_error_marks_sync_partial(self):
        """A download exception on one file should set PARTIAL status after sync."""
        source = _make_source()
        items = [_make_file_item("i1", "fail.pdf")]

        with (
            patch("db.database.SessionLocal") as mock_sl,
            patch("mattin_sharepoint.service.GraphClient") as mock_gc,
            patch("mattin_sharepoint.service.SharePointSourceRepository") as mock_src_repo,
            patch("mattin_sharepoint.service.SharePointFileRepository") as mock_file_repo,
            patch("services.silo_service.SiloService"),
        ):
            mock_db = MagicMock()
            mock_sl.return_value = mock_db
            mock_src_repo.get_by_id = MagicMock(return_value=source)
            mock_src_repo.update = MagicMock(return_value=source)
            mock_gc.get_token = AsyncMock(return_value="tok")
            mock_gc.delta_query = AsyncMock(return_value=(items, "delta"))
            mock_gc.download_file = AsyncMock(side_effect=Exception("network error"))
            mock_file_repo.upsert_by_drive_item = MagicMock()

            from mattin_sharepoint.service import SharePointSyncService
            await SharePointSyncService.run_sync(source.id)

        # Last update should be PARTIAL
        final_call = mock_src_repo.update.call_args_list[-1]
        updated_source = final_call[0][0]
        assert updated_source.last_sync_status == SharePointSyncStatus.PARTIAL

    @pytest.mark.asyncio
    async def test_410_gone_clears_delta_token_and_restarts(self):
        """GraphDeltaExpiredError should clear the delta token and retry with None."""
        stored_token = "https://graph.microsoft.com/delta?token=old"
        source = _make_source(last_delta_token=stored_token)

        call_count = 0
        called_delta_tokens: list = []

        async def fake_delta_query(token, drive_id, delta_token, **kwargs):
            nonlocal call_count
            call_count += 1
            called_delta_tokens.append(delta_token)
            if call_count == 1:
                raise GraphDeltaExpiredError()
            return [], "new-delta"

        with (
            patch("db.database.SessionLocal") as mock_sl,
            patch("mattin_sharepoint.service.GraphClient") as mock_gc,
            patch("mattin_sharepoint.service.SharePointSourceRepository") as mock_src_repo,
            patch("mattin_sharepoint.service.SharePointFileRepository"),
            patch("services.silo_service.SiloService"),
        ):
            mock_sl.return_value = MagicMock()
            mock_src_repo.get_by_id = MagicMock(return_value=source)
            mock_src_repo.update = MagicMock(return_value=source)
            mock_gc.get_token = AsyncMock(return_value="tok")
            mock_gc.delta_query = fake_delta_query

            from mattin_sharepoint.service import SharePointSyncService
            await SharePointSyncService.run_sync(source.id)

        # delta_query must have been called twice: first with stored token, then with None
        assert call_count == 2
        assert called_delta_tokens[0] == stored_token  # first call used stored token
        assert called_delta_tokens[1] is None  # second call (after 410) used None

    @pytest.mark.asyncio
    async def test_filter_exclusion_removes_previously_indexed_files(self):
        """Files that violate the current extension filter should be removed."""
        source = _make_source(file_extension_filters=["pdf"])
        stale_file = MagicMock()
        stale_file.id = 77
        stale_file.vector_doc_ids = []

        with (
            patch("db.database.SessionLocal") as mock_sl,
            patch("mattin_sharepoint.service.GraphClient") as mock_gc,
            patch("mattin_sharepoint.service.SharePointSourceRepository") as mock_src_repo,
            patch("mattin_sharepoint.service.SharePointFileRepository") as mock_file_repo,
            patch("services.silo_service.SiloService"),
        ):
            mock_sl.return_value = MagicMock()
            mock_src_repo.get_by_id = MagicMock(return_value=source)
            mock_src_repo.update = MagicMock(return_value=source)
            mock_gc.get_token = AsyncMock(return_value="tok")
            mock_gc.delta_query = AsyncMock(return_value=([], "delta"))
            # Stale file that is not pdf
            mock_file_repo.get_files_with_extension_not_in = MagicMock(return_value=[stale_file])
            mock_file_repo.delete_file = MagicMock()

            from mattin_sharepoint.service import SharePointSyncService
            await SharePointSyncService.run_sync(source.id)

        mock_file_repo.get_files_with_extension_not_in.assert_called_once_with(
            source.id, ["pdf"], mock_sl.return_value
        )
        mock_file_repo.delete_file.assert_called_once_with(stale_file.id, mock_sl.return_value)
