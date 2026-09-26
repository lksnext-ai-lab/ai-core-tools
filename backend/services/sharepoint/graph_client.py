"""Microsoft Graph API client for SharePoint drive operations."""
from __future__ import annotations

import httpx


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class GraphAuthError(Exception):
    """Raised when authentication against Microsoft identity platform fails."""
    pass


class GraphAccessError(Exception):
    """Raised when the Graph API returns a non-200 response for a resource request."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


class GraphDeltaExpiredError(Exception):
    """Raised when the Graph API returns HTTP 410 (delta token expired)."""
    pass


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class GraphClient:
    """Stateless Microsoft Graph API client. All methods are static/classmethod."""

    @staticmethod
    async def get_token(tenant_id: str, client_id: str, client_secret: str) -> str:
        """Obtain a client-credentials access token from Microsoft identity platform.

        Returns the access_token string.
        Raises GraphAuthError on failure.
        """
        url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, data=data)
        if response.status_code != 200:
            raise GraphAuthError(
                f"Token request failed ({response.status_code}): {response.text}"
            )
        return response.json()["access_token"]

    @staticmethod
    async def search_sites(token: str, query: str) -> list[dict]:
        """Search SharePoint sites by keyword.

        Returns a list of dicts with keys: id, displayName, webUrl.
        """
        url = f"{GRAPH_BASE}/sites?search={query}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        response.raise_for_status()
        return response.json().get("value", [])

    @staticmethod
    async def resolve_site(token: str, site_url: str) -> dict:
        """Resolve a SharePoint site by its URL.

        Accepts full URLs like https://tenant.sharepoint.com/sites/Marketing
        or just the hostname https://tenant.sharepoint.com.
        Returns the site dict (id, displayName, webUrl).
        Raises GraphAccessError if the site cannot be resolved.
        """
        from urllib.parse import urlparse
        parsed = urlparse(site_url if site_url.startswith("http") else f"https://{site_url}")
        hostname = parsed.netloc or parsed.path.split("/")[0]
        path = parsed.path.rstrip("/") or "/"
        url = f"{GRAPH_BASE}/sites/{hostname}:{path}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        if response.status_code != 200:
            raise GraphAccessError(
                response.status_code,
                f"Site not found ({response.status_code}): {response.text}",
            )
        return response.json()

    @staticmethod
    async def list_drives(token: str, site_id: str) -> list[dict]:
        """List all drives for a SharePoint site.

        Returns a list of dicts with keys: id, name, driveType.
        """
        url = f"{GRAPH_BASE}/sites/{site_id}/drives"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        response.raise_for_status()
        return response.json().get("value", [])

    @staticmethod
    async def verify_drive_access(token: str, drive_id: str) -> dict:
        """Verify that the service account can access a specific drive.

        Returns the drive metadata dict.
        Raises GraphAccessError if the drive cannot be reached.
        """
        url = f"{GRAPH_BASE}/drives/{drive_id}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        if response.status_code != 200:
            raise GraphAccessError(
                response.status_code,
                f"Drive access check failed ({response.status_code}): {response.text}",
            )
        return response.json()

    @staticmethod
    async def delta_query(
        token: str,
        drive_id: str,
        delta_token: str | None,
        select_fields: str | None = None,
    ) -> tuple[list[dict], str | None]:
        """Execute a delta query against a drive root.

        If `delta_token` is None, performs an initial full-drive delta request.
        If `delta_token` is provided, it is used directly as the next delta URL.

        Paginates via @odata.nextLink until exhausted.
        Returns (items, new_delta_token_or_none).

        Raises GraphDeltaExpiredError when the server responds with HTTP 410 (token expired).
        """
        if delta_token is None:
            fields = select_fields or (
                "id,name,file,folder,lastModifiedDateTime,deleted,"
                "webUrl,parentReference,size,mimeType"
            )
            url: str = f"{GRAPH_BASE}/drives/{drive_id}/root/delta?$select={fields}"
        else:
            url = delta_token  # stored token IS the full delta URL

        headers = {"Authorization": f"Bearer {token}"}
        all_items: list[dict] = []
        new_delta_token: str | None = None

        async with httpx.AsyncClient(follow_redirects=True) as client:
            while url:
                response = await client.get(url, headers=headers)

                if response.status_code == 410:
                    raise GraphDeltaExpiredError("Delta token has expired; full re-sync required.")

                response.raise_for_status()
                payload = response.json()

                all_items.extend(payload.get("value", []))

                next_link = payload.get("@odata.nextLink")
                delta_link = payload.get("@odata.deltaLink")

                if next_link:
                    url = next_link
                else:
                    # Final page — extract delta token from deltaLink
                    if delta_link:
                        new_delta_token = delta_link
                    url = None  # stop pagination

        return all_items, new_delta_token

    @staticmethod
    async def download_file(
        token: str,
        drive_id: str,
        item_id: str,
        dest_path: str,
    ) -> None:
        """Stream a drive item's content to a local file.

        Follows redirects (Graph returns a short-lived redirect to the file).
        """
        url = f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/content"
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(follow_redirects=True) as client:
            async with client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()
                with open(dest_path, "wb") as f:
                    async for chunk in response.aiter_bytes():
                        f.write(chunk)
