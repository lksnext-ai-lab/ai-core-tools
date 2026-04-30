"""
Integration tests for the domain URL API endpoints.

Endpoints under test:
  GET    /internal/apps/{app_id}/domains/{domain_id}/urls
  POST   /internal/apps/{app_id}/domains/{domain_id}/urls
  GET    /internal/apps/{app_id}/domains/{domain_id}/urls/{url_id}
  DELETE /internal/apps/{app_id}/domains/{domain_id}/urls/{url_id}
  POST   /internal/apps/{app_id}/domains/{domain_id}/urls/{url_id}/recrawl
"""

import pytest
from datetime import datetime, timedelta

from models.domain_url import DomainUrl
from models.enums.domain_url_status import DomainUrlStatus
from models.enums.discovery_source import DiscoverySource
from services.crawl.normalization import normalize_url


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestListDomainUrls:
    """GET /internal/apps/{app_id}/domains/{domain_id}/urls"""

    def test_list_urls_empty(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """Listing URLs for a domain with no URLs returns empty result."""
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/urls",
            headers=owner_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_urls_returns_added_url(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """After adding a URL, listing returns it."""
        db.flush()
        # Add a URL
        add_resp = client.post(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/urls",
            json={"url": "https://example.com/page"},
            headers=owner_headers,
        )
        assert add_resp.status_code == 201

        # List URLs
        list_resp = client.get(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/urls",
            headers=owner_headers,
        )
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["url"] == "https://example.com/page"
        assert item["status"] == "PENDING"
        assert item["discovered_via"] == "MANUAL"

    def test_list_filter_by_status(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """Filter by status returns only matching URLs."""
        db.flush()
        # Add two URLs directly
        url1 = DomainUrl(
            domain_id=fake_domain.domain_id,
            url="https://example.com/page-pending",
            normalized_url=normalize_url("https://example.com/page-pending"),
            status=DomainUrlStatus.PENDING,
            discovered_via=DiscoverySource.MANUAL,
            depth=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        url2 = DomainUrl(
            domain_id=fake_domain.domain_id,
            url="https://example.com/page-indexed",
            normalized_url=normalize_url("https://example.com/page-indexed"),
            status=DomainUrlStatus.INDEXED,
            discovered_via=DiscoverySource.CRAWL,
            depth=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(url1)
        db.add(url2)
        db.flush()

        # Filter by PENDING
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/urls"
            f"?status=PENDING",
            headers=owner_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["url"] == "https://example.com/page-pending"

    def test_list_filter_by_discovered_via(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """Filter by discovered_via returns only matching URLs."""
        db.flush()
        url1 = DomainUrl(
            domain_id=fake_domain.domain_id,
            url="https://example.com/manual-url",
            normalized_url=normalize_url("https://example.com/manual-url"),
            status=DomainUrlStatus.PENDING,
            discovered_via=DiscoverySource.MANUAL,
            depth=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        url2 = DomainUrl(
            domain_id=fake_domain.domain_id,
            url="https://example.com/sitemap-url",
            normalized_url=normalize_url("https://example.com/sitemap-url"),
            status=DomainUrlStatus.PENDING,
            discovered_via=DiscoverySource.SITEMAP,
            depth=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(url1)
        db.add(url2)
        db.flush()

        response = client.get(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/urls"
            f"?discovered_via=SITEMAP",
            headers=owner_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["discovered_via"] == "SITEMAP"

    def test_list_search_q(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """Search by q returns only URLs matching the query string."""
        db.flush()
        url1 = DomainUrl(
            domain_id=fake_domain.domain_id,
            url="https://example.com/page-1",
            normalized_url=normalize_url("https://example.com/page-1"),
            status=DomainUrlStatus.PENDING,
            discovered_via=DiscoverySource.MANUAL,
            depth=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        url2 = DomainUrl(
            domain_id=fake_domain.domain_id,
            url="https://example.com/page-2",
            normalized_url=normalize_url("https://example.com/page-2"),
            status=DomainUrlStatus.PENDING,
            discovered_via=DiscoverySource.MANUAL,
            depth=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(url1)
        db.add(url2)
        db.flush()

        response = client.get(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/urls"
            f"?q=page-1",
            headers=owner_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert "page-1" in data["items"][0]["url"]


class TestAddDomainUrl:
    """POST /internal/apps/{app_id}/domains/{domain_id}/urls"""

    def test_add_manual_url(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """Adding a URL returns 201 with url_id."""
        db.flush()
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/urls",
            json={"url": "https://example.com/new-page"},
            headers=owner_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert "url_id" in data
        assert isinstance(data["url_id"], int)

    def test_add_duplicate_url_returns_existing(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """Adding the same URL twice returns the same url_id (upsert)."""
        db.flush()
        url = "https://example.com/duplicate"

        r1 = client.post(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/urls",
            json={"url": url},
            headers=owner_headers,
        )
        assert r1.status_code == 201
        url_id_1 = r1.json()["url_id"]

        r2 = client.post(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/urls",
            json={"url": url},
            headers=owner_headers,
        )
        assert r2.status_code == 201
        url_id_2 = r2.json()["url_id"]

        assert url_id_1 == url_id_2

    def test_add_url_nonexistent_domain_returns_404(
        self, client, fake_app, owner_headers, db
    ):
        """Adding a URL to a non-existent domain returns 404."""
        db.flush()
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/domains/99999/urls",
            json={"url": "https://example.com/page"},
            headers=owner_headers,
        )
        assert response.status_code == 404


class TestGetDomainUrl:
    """GET /internal/apps/{app_id}/domains/{domain_id}/urls/{url_id}"""

    def test_get_url_detail(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """Getting a specific URL returns its full detail."""
        db.flush()
        # Add URL via API
        add_resp = client.post(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/urls",
            json={"url": "https://example.com/detail-page"},
            headers=owner_headers,
        )
        assert add_resp.status_code == 201
        url_id = add_resp.json()["url_id"]

        # Get detail
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/urls/{url_id}",
            headers=owner_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == url_id
        assert data["url"] == "https://example.com/detail-page"
        assert data["domain_id"] == fake_domain.domain_id
        assert data["status"] == "PENDING"
        assert data["discovered_via"] == "MANUAL"
        assert data["depth"] == 0

    def test_get_url_nonexistent_returns_404(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """Getting a non-existent URL returns 404."""
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/urls/99999",
            headers=owner_headers,
        )
        assert response.status_code == 404


class TestDeleteDomainUrl:
    """DELETE /internal/apps/{app_id}/domains/{domain_id}/urls/{url_id}"""

    def test_delete_url(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """Deleting a URL removes it from the list."""
        db.flush()
        # Add URL
        add_resp = client.post(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/urls",
            json={"url": "https://example.com/delete-me"},
            headers=owner_headers,
        )
        assert add_resp.status_code == 201
        url_id = add_resp.json()["url_id"]

        # Delete it
        del_resp = client.delete(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/urls/{url_id}",
            headers=owner_headers,
        )
        assert del_resp.status_code == 200
        assert del_resp.json()["success"] is True

        # Verify it's gone
        list_resp = client.get(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/urls",
            headers=owner_headers,
        )
        assert list_resp.json()["total"] == 0

    def test_delete_nonexistent_url_returns_404(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """Deleting a non-existent URL returns 404."""
        db.flush()
        response = client.delete(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/urls/99999",
            headers=owner_headers,
        )
        assert response.status_code == 404


class TestRecrawlDomainUrl:
    """POST /internal/apps/{app_id}/domains/{domain_id}/urls/{url_id}/recrawl"""

    def test_recrawl_sets_next_crawl_at_now(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """Marking a URL for re-crawl sets next_crawl_at to now."""
        db.flush()
        # Add URL directly with INDEXED status
        url_obj = DomainUrl(
            domain_id=fake_domain.domain_id,
            url="https://example.com/indexed-page",
            normalized_url=normalize_url("https://example.com/indexed-page"),
            status=DomainUrlStatus.INDEXED,
            discovered_via=DiscoverySource.MANUAL,
            depth=0,
            last_indexed_at=datetime.utcnow() - timedelta(hours=1),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(url_obj)
        db.flush()
        url_id = url_obj.id

        before = datetime.utcnow()

        # Mark for re-crawl
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/urls/{url_id}/recrawl",
            headers=owner_headers,
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

        after = datetime.utcnow()

        # Verify next_crawl_at is set to approximately now
        db.refresh(url_obj)
        assert url_obj.next_crawl_at is not None
        # next_crawl_at should be within a reasonable window (5 seconds)
        assert url_obj.next_crawl_at >= before - timedelta(seconds=5)
        assert url_obj.next_crawl_at <= after + timedelta(seconds=5)
        assert url_obj.status == DomainUrlStatus.PENDING

    def test_recrawl_nonexistent_url_returns_404(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """Marking a non-existent URL for re-crawl returns 404."""
        db.flush()
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/urls/99999/recrawl",
            headers=owner_headers,
        )
        assert response.status_code == 404
