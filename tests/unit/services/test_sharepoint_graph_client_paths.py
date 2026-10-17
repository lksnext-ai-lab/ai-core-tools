"""Ids from user configuration must never change the Graph request path (Sonar pythonsecurity:S7044)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.sharepoint.graph_client import GraphAccessError, GraphAuthError, GraphClient

SITE_ID = "contoso.sharepoint.com,1b2c3d4e-0000-1111-2222-333344445555,9f8e7d6c-0000-1111-2222-333344445555"
DRIVE_ID = "b!AbC-123_xyz"


def _mock_client(json_body=None, status=200):
    response = MagicMock(status_code=status)
    response.json.return_value = json_body or {"value": []}
    response.raise_for_status = MagicMock()
    client = AsyncMock()
    client.get.return_value = response
    client.post.return_value = response
    cm = AsyncMock()
    cm.__aenter__.return_value = client
    return cm, client


@pytest.mark.asyncio
@pytest.mark.parametrize("tenant", ["../evil", "a/b", "tenant?x=1", "", "x#y"])
async def test_get_token_rejects_tenant_that_alters_the_url(tenant):
    with patch("services.sharepoint.graph_client.httpx.AsyncClient") as cls:
        with pytest.raises(GraphAuthError):
            await GraphClient.get_token(tenant, "client", "secret")
        cls.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("tenant", ["1b2c3d4e-0000-1111-2222-333344445555", "contoso.onmicrosoft.com"])
async def test_get_token_accepts_guid_and_domain_tenants(tenant):
    cm, client = _mock_client({"access_token": "tok"})
    with patch("services.sharepoint.graph_client.httpx.AsyncClient", return_value=cm):
        assert await GraphClient.get_token(tenant, "client", "secret") == "tok"
    assert client.post.call_args.args[0] == f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"


@pytest.mark.asyncio
@pytest.mark.parametrize("site_id", ["../../users", "site/../x", "..", "a?b", ""])
async def test_list_drives_rejects_site_id_that_alters_the_path(site_id):
    with patch("services.sharepoint.graph_client.httpx.AsyncClient") as cls:
        with pytest.raises(GraphAccessError):
            await GraphClient.list_drives("tok", site_id)
        cls.assert_not_called()


@pytest.mark.asyncio
async def test_real_graph_ids_are_used_unchanged():
    cm, client = _mock_client()
    with patch("services.sharepoint.graph_client.httpx.AsyncClient", return_value=cm):
        await GraphClient.list_drives("tok", SITE_ID)
    assert client.get.call_args.args[0] == f"https://graph.microsoft.com/v1.0/sites/{SITE_ID}/drives"


@pytest.mark.asyncio
@pytest.mark.parametrize("drive_id,item_id", [("../me", "1"), (DRIVE_ID, "../../users"), (DRIVE_ID, "a/b")])
async def test_download_rejects_ids_that_alter_the_path(tmp_path, drive_id, item_id):
    with patch("services.sharepoint.graph_client.httpx.AsyncClient") as cls:
        with pytest.raises(GraphAccessError):
            await GraphClient.download_file("tok", drive_id, item_id, str(tmp_path / "f"))
        cls.assert_not_called()


@pytest.mark.asyncio
async def test_search_query_is_sent_as_an_encoded_parameter():
    cm, client = _mock_client()
    with patch("services.sharepoint.graph_client.httpx.AsyncClient", return_value=cm):
        await GraphClient.search_sites("tok", "sales&$select=secret")
    assert client.get.call_args.args[0] == "https://graph.microsoft.com/v1.0/sites"
    assert client.get.call_args.kwargs["params"] == {"search": "sales&$select=secret"}


@pytest.mark.asyncio
@pytest.mark.parametrize("site_url", ["https://contoso.sharepoint.com/sites/../../users", "https://evil/host/../x/.."])
async def test_resolve_site_rejects_traversal(site_url):
    with patch("services.sharepoint.graph_client.httpx.AsyncClient") as cls:
        with pytest.raises(GraphAccessError):
            await GraphClient.resolve_site("tok", site_url)
        cls.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_site_keeps_valid_site_path():
    cm, client = _mock_client({"id": SITE_ID})
    with patch("services.sharepoint.graph_client.httpx.AsyncClient", return_value=cm):
        await GraphClient.resolve_site("tok", "https://contoso.sharepoint.com/sites/Marketing")
    assert client.get.call_args.args[0] == "https://graph.microsoft.com/v1.0/sites/contoso.sharepoint.com:/sites/Marketing"
