"""
Integration tests for the crawl policy API endpoints.

Endpoints under test:
  GET  /internal/apps/{app_id}/domains/{domain_id}/crawl-policy
  PUT  /internal/apps/{app_id}/domains/{domain_id}/crawl-policy
"""

import pytest
from datetime import datetime

from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
from tests.factories import configure_factories, UserFactory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def valid_policy_payload(**overrides) -> dict:
    """Build a minimal valid CrawlPolicySchema payload."""
    payload = {
        "seed_url": "https://example.com",
        "sitemap_url": None,
        "manual_urls": [],
        "max_depth": 2,
        "include_globs": [],
        "exclude_globs": [],
        "rate_limit_rps": 1.0,
        "refresh_interval_hours": 168,
        "respect_robots_txt": True,
        "is_active": False,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def viewer_headers(db, client, fake_app, fake_user):
    """Auth headers for a VIEWER on fake_app."""
    configure_factories(db)
    viewer_user = UserFactory(email="viewer-crawl@mattin-test.com", name="Viewer User")
    collab = AppCollaborator(
        app_id=fake_app.app_id,
        user_id=viewer_user.user_id,
        role=CollaborationRole.VIEWER,
        status=CollaborationStatus.ACCEPTED,
        invited_by=fake_user.user_id,
        invited_at=datetime.now(),
        accepted_at=datetime.now(),
    )
    db.add(collab)
    db.flush()
    response = client.post("/internal/auth/dev-login", json={"email": viewer_user.email})
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# GET /{domain_id}/crawl-policy
# ---------------------------------------------------------------------------

class TestGetCrawlPolicy:
    """GET /internal/apps/{app_id}/domains/{domain_id}/crawl-policy"""

    def test_get_policy_returns_default_after_domain_create(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """After creating a domain, GET crawl-policy returns the inactive default."""
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/crawl-policy",
            headers=owner_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["domain_id"] == fake_domain.domain_id
        assert data["is_active"] is False
        assert data["seed_url"] == fake_domain.base_url

    def test_get_policy_returns_404_for_nonexistent_domain(
        self, client, fake_app, owner_headers, db
    ):
        """GET policy for a domain that doesn't exist returns 404."""
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/domains/99999/crawl-policy",
            headers=owner_headers,
        )
        assert response.status_code == 404

    def test_get_policy_viewer_can_read(
        self, client, fake_app, fake_domain, viewer_headers, db
    ):
        """VIEWER role can read the crawl policy."""
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/crawl-policy",
            headers=viewer_headers,
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# PUT /{domain_id}/crawl-policy
# ---------------------------------------------------------------------------

class TestUpsertCrawlPolicy:
    """PUT /internal/apps/{app_id}/domains/{domain_id}/crawl-policy"""

    def test_put_policy_owner_can_update(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """Owner can update the crawl policy."""
        db.flush()
        payload = valid_policy_payload(
            seed_url="https://example.com/updated",
            is_active=True,
            max_depth=3,
        )
        response = client.put(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/crawl-policy",
            json=payload,
            headers=owner_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["seed_url"] == "https://example.com/updated"
        assert data["is_active"] is True
        assert data["max_depth"] == 3

    def test_put_policy_viewer_gets_403(
        self, client, fake_app, fake_domain, viewer_headers, db
    ):
        """VIEWER cannot update crawl policy — expects 403."""
        db.flush()
        payload = valid_policy_payload(seed_url="https://example.com")
        response = client.put(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/crawl-policy",
            json=payload,
            headers=viewer_headers,
        )
        assert response.status_code == 403

    def test_put_policy_no_source_returns_422(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """PUT with no discovery source configured returns 422."""
        db.flush()
        payload = {
            "seed_url": None,
            "sitemap_url": None,
            "manual_urls": [],
            "max_depth": 2,
            "include_globs": [],
            "exclude_globs": [],
            "rate_limit_rps": 1.0,
            "refresh_interval_hours": 168,
            "respect_robots_txt": True,
            "is_active": False,
        }
        response = client.put(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/crawl-policy",
            json=payload,
            headers=owner_headers,
        )
        assert response.status_code == 422

    def test_put_policy_depth_over_limit_returns_422(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """max_depth=6 exceeds Pydantic limit — returns 422."""
        db.flush()
        payload = valid_policy_payload(max_depth=6)
        response = client.put(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/crawl-policy",
            json=payload,
            headers=owner_headers,
        )
        assert response.status_code == 422

    def test_put_policy_updates_existing_policy(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """PUT twice updates the existing record (id stays the same)."""
        db.flush()
        payload = valid_policy_payload(seed_url="https://example.com/v1")
        r1 = client.put(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/crawl-policy",
            json=payload,
            headers=owner_headers,
        )
        assert r1.status_code == 200
        id1 = r1.json()["id"]

        payload2 = valid_policy_payload(seed_url="https://example.com/v2")
        r2 = client.put(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/crawl-policy",
            json=payload2,
            headers=owner_headers,
        )
        assert r2.status_code == 200
        assert r2.json()["id"] == id1  # same policy row updated
        assert r2.json()["seed_url"] == "https://example.com/v2"

    def test_put_policy_with_globs(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """Valid glob patterns are accepted."""
        db.flush()
        payload = valid_policy_payload(
            include_globs=["/docs/**", "/blog/*"],
            exclude_globs=["/private/**"],
        )
        response = client.put(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/crawl-policy",
            json=payload,
            headers=owner_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "/docs/**" in data["include_globs"]
