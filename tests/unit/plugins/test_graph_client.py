"""Unit tests for GraphClient — all HTTP mocked via unittest.mock."""
from __future__ import annotations

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

pytest.importorskip("mattin_sharepoint", reason="mattin-sharepoint plugin not installed")

from mattin_sharepoint.graph_client import (
    GraphClient,
    GraphAuthError,
    GraphAccessError,
    GraphDeltaExpiredError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(status_code: int, json_data: dict) -> MagicMock:
    """Return a MagicMock that mimics an httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return resp


# ---------------------------------------------------------------------------
# get_token
# ---------------------------------------------------------------------------

class TestGetToken:
    @pytest.mark.asyncio
    async def test_get_token_success(self):
        token_json = {"access_token": "my-token-abc"}
        mock_resp = _make_response(200, token_json)

        with patch("mattin_sharepoint.graph_client.httpx.AsyncClient") as mock_client_cls:
            instance = AsyncMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = instance

            token = await GraphClient.get_token("tenant", "client_id", "secret")

        assert token == "my-token-abc"

    @pytest.mark.asyncio
    async def test_get_token_failure(self):
        mock_resp = _make_response(400, {"error": "invalid_client"})

        with patch("mattin_sharepoint.graph_client.httpx.AsyncClient") as mock_client_cls:
            instance = AsyncMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = instance

            with pytest.raises(GraphAuthError):
                await GraphClient.get_token("tenant", "client_id", "bad-secret")


# ---------------------------------------------------------------------------
# search_sites
# ---------------------------------------------------------------------------

class TestSearchSites:
    @pytest.mark.asyncio
    async def test_search_sites_returns_list(self):
        sites = [{"id": "s1", "displayName": "Site A", "webUrl": "https://example.com"}]
        mock_resp = _make_response(200, {"value": sites})

        with patch("mattin_sharepoint.graph_client.httpx.AsyncClient") as mock_client_cls:
            instance = AsyncMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = instance

            result = await GraphClient.search_sites("my-token", "marketing")

        assert result == sites


# ---------------------------------------------------------------------------
# list_drives
# ---------------------------------------------------------------------------

class TestListDrives:
    @pytest.mark.asyncio
    async def test_list_drives_returns_list(self):
        drives = [{"id": "d1", "name": "Documents", "driveType": "documentLibrary"}]
        mock_resp = _make_response(200, {"value": drives})

        with patch("mattin_sharepoint.graph_client.httpx.AsyncClient") as mock_client_cls:
            instance = AsyncMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = instance

            result = await GraphClient.list_drives("my-token", "site-123")

        assert result == drives


# ---------------------------------------------------------------------------
# delta_query
# ---------------------------------------------------------------------------

class TestDeltaQuery:
    @pytest.mark.asyncio
    async def test_delta_query_initial_paginates(self):
        """First call should paginate nextLink then stop at deltaLink."""
        page1 = {
            "value": [{"id": "item1", "name": "a.pdf", "file": {}}],
            "@odata.nextLink": "https://graph.microsoft.com/next-page",
        }
        page2 = {
            "value": [{"id": "item2", "name": "b.docx", "file": {}}],
            "@odata.deltaLink": "https://graph.microsoft.com/delta?token=abc123",
        }
        resp1 = _make_response(200, page1)
        resp2 = _make_response(200, page2)

        with patch("mattin_sharepoint.graph_client.httpx.AsyncClient") as mock_client_cls:
            instance = AsyncMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.get = AsyncMock(side_effect=[resp1, resp2])
            mock_client_cls.return_value = instance

            items, delta_token = await GraphClient.delta_query("tok", "drive-1", None)

        assert len(items) == 2
        assert items[0]["id"] == "item1"
        assert items[1]["id"] == "item2"
        assert delta_token == "https://graph.microsoft.com/delta?token=abc123"

    @pytest.mark.asyncio
    async def test_delta_query_incremental_uses_stored_token(self):
        """When delta_token is provided it should be used as the URL directly."""
        stored_url = "https://graph.microsoft.com/v1.0/drives/drv/root/delta?token=xyz"
        page = {
            "value": [],
            "@odata.deltaLink": stored_url,
        }
        mock_resp = _make_response(200, page)

        captured_urls = []

        async def fake_get(url, headers=None):
            captured_urls.append(url)
            return mock_resp

        with patch("mattin_sharepoint.graph_client.httpx.AsyncClient") as mock_client_cls:
            instance = AsyncMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.get = fake_get
            mock_client_cls.return_value = instance

            await GraphClient.delta_query("tok", "drive-1", stored_url)

        # First call must use stored_url, not construct a new initial URL
        assert captured_urls[0] == stored_url

    @pytest.mark.asyncio
    async def test_delta_query_410_raises_expired_error(self):
        """HTTP 410 from the delta endpoint must raise GraphDeltaExpiredError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 410

        with patch("mattin_sharepoint.graph_client.httpx.AsyncClient") as mock_client_cls:
            instance = AsyncMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = instance

            with pytest.raises(GraphDeltaExpiredError):
                await GraphClient.delta_query("tok", "drive-1", None)
