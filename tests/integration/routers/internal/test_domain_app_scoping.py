"""Regression tests for the cross-tenant IDOR on /internal/apps/{app_id}/domains/{domain_id}/...

Bug: every ``/{domain_id}`` route checked the caller's role on ``app_id`` from the URL but
loaded the domain by id alone, so a member of App A could read/modify/delete App B's domain.
Fix: ``routers.controls.domain_scope`` dependencies (role check first, then 404 unless the
domain belongs to the path's app).
"""

from datetime import datetime

import pytest

from models.crawl_job import CrawlJob
from models.crawl_policy import CrawlPolicy
from models.domain import Domain
from models.domain_url import DomainUrl
from models.enums.crawl_job_status import CrawlJobStatus
from models.enums.crawl_trigger import CrawlTrigger
from models.enums.discovery_source import DiscoverySource
from models.silo import Silo
from tests.factories import AppFactory, UserFactory, configure_factories

BASE = "/internal/apps"


def _make_domain(db, app, name):
    silo = Silo(name=f"{name} silo", description="s", silo_type="DOMAIN", app_id=app.app_id)
    db.add(silo)
    db.flush()
    domain = Domain(
        name=name, description="d", base_url="https://other.example.com", content_tag="body",
        app_id=app.app_id, silo_id=silo.silo_id, create_date=datetime.now(),
    )
    db.add(domain)
    db.flush()
    db.add(CrawlPolicy(
        domain_id=domain.domain_id, seed_url="https://other.example.com", manual_urls=[], max_depth=2,
        include_globs=[], exclude_globs=[], rate_limit_rps=1.0, refresh_interval_hours=168,
        respect_robots_txt=True, is_active=False, created_at=datetime.now(), updated_at=datetime.now(),
    ))
    url = DomainUrl(
        domain_id=domain.domain_id, url="https://other.example.com/p",
        normalized_url="https://other.example.com/p", discovered_via=DiscoverySource.MANUAL,
    )
    db.add(url)
    job = CrawlJob(
        domain_id=domain.domain_id, status=CrawlJobStatus.QUEUED, triggered_by=CrawlTrigger.MANUAL,
        created_at=datetime.utcnow(),
    )
    db.add(job)
    db.flush()
    return domain, silo, url, job


@pytest.fixture
def other_app(db, fake_user):
    """App B, owned by the same user so app-level RBAC on App A is never what rejects."""
    configure_factories(db)
    return AppFactory(owner_id=fake_user.user_id)


@pytest.fixture
def other(db, other_app):
    domain, silo, url, job = _make_domain(db, other_app, "Other Domain")
    return {"domain": domain, "silo": silo, "url": url, "job": job}


@pytest.fixture
def sibling(db, fake_app):
    """A second domain inside fake_app (same-app, different domain)."""
    domain, silo, url, job = _make_domain(db, fake_app, "Sibling Domain")
    return {"domain": domain, "silo": silo, "url": url, "job": job}


@pytest.fixture
def own_url(db, fake_domain):
    url = DomainUrl(
        domain_id=fake_domain.domain_id, url="https://example.com/own", normalized_url="https://example.com/own",
        discovered_via=DiscoverySource.MANUAL,
    )
    db.add(url)
    db.flush()
    return url


@pytest.fixture
def outsider_headers(db):
    from utils.local_auth_tokens import mint_access_token

    configure_factories(db)
    user = UserFactory(email="domain-outsider@mattin-test.com", name="Domain Outsider")
    db.flush()
    token, _ = mint_access_token(user.user_id, user.email, user.name)
    return {"Authorization": f"Bearer {token}"}


POLICY_BODY = {"seed_url": "https://evil.example.com", "is_active": True}


def _routes(d, url_id, job_id):
    """(method, path suffix, json body) for every /{domain_id} route."""
    b = f"/domains/{d}"
    return [
        ("GET", b, None),
        ("PUT", b, {"name": "pwned", "description": "x", "base_url": "https://evil.example.com", "content_tag": "body"}),
        ("DELETE", b, None),
        ("POST", f"{b}/export", None),
        ("GET", f"{b}/urls", None),
        ("POST", f"{b}/urls", {"url": "https://evil.example.com/x"}),
        ("GET", f"{b}/urls/{url_id}", None),
        ("DELETE", f"{b}/urls/{url_id}", None),
        ("POST", f"{b}/urls/{url_id}/recrawl", None),
        ("GET", f"{b}/urls/{url_id}/content", None),
        ("GET", f"{b}/crawl-policy", None),
        ("PUT", f"{b}/crawl-policy", POLICY_BODY),
        ("POST", f"{b}/crawl-jobs", None),
        ("GET", f"{b}/crawl-jobs", None),
        ("GET", f"{b}/crawl-jobs/{job_id}", None),
        ("POST", f"{b}/crawl-jobs/{job_id}/cancel", None),
    ]


ROUTE_COUNT = 16


def _call(client, app_id, route, headers):
    method, path, body = route
    return client.request(method, f"{BASE}/{app_id}{path}", json=body, headers=headers)


@pytest.mark.parametrize("idx", range(ROUTE_COUNT))
class TestCrossAppReturns404:
    def test_cross_app_404_no_side_effects(self, idx, client, fake_app, other, owner_headers, db):
        d, u, j = other["domain"].domain_id, other["url"].id, other["job"].id
        route = _routes(d, u, j)[idx]
        response = _call(client, fake_app.app_id, route, owner_headers)
        assert response.status_code == 404, (route, response.text)

        db.expire_all()
        assert db.get(Domain, d).name == "Other Domain"
        assert db.get(Silo, other["silo"].silo_id) is not None
        assert db.get(DomainUrl, u) is not None
        assert db.get(DomainUrl, u).status.value == "PENDING"
        job = db.get(CrawlJob, j)
        assert job.status == CrawlJobStatus.QUEUED
        assert db.query(CrawlJob).filter(CrawlJob.domain_id == d).count() == 1
        assert db.query(DomainUrl).filter(DomainUrl.domain_id == d).count() == 1
        policy = db.query(CrawlPolicy).filter(CrawlPolicy.domain_id == d).one()
        assert policy.seed_url == "https://other.example.com"
        assert policy.is_active is False

    def test_non_member_403_existing_and_missing(
        self, idx, client, fake_app, fake_domain, fake_user, outsider_headers, db
    ):
        for domain_id in (fake_domain.domain_id, 999999):
            route = _routes(domain_id, 1, 1)[idx]
            response = _call(client, fake_app.app_id, route, outsider_headers)
            assert response.status_code == 403, (route, response.text)

    def test_missing_domain_404(self, idx, client, fake_app, owner_headers, db):
        route = _routes(999999, 1, 1)[idx]
        assert _call(client, fake_app.app_id, route, owner_headers).status_code == 404

    def test_domain_zero_404_except_get(self, idx, client, fake_app, owner_headers, db):
        route = _routes(0, 1, 1)[idx]
        response = _call(client, fake_app.app_id, route, owner_headers)
        if idx == 0:
            assert response.status_code == 200
        else:
            assert response.status_code == 404


class TestChildOfAnotherDomainInSameApp:
    def test_url_of_other_domain_404(self, client, fake_app, fake_domain, sibling, owner_headers, db):
        u = sibling["url"].id
        base = f"{BASE}/{fake_app.app_id}/domains/{fake_domain.domain_id}/urls/{u}"
        assert client.get(base, headers=owner_headers).status_code == 404
        assert client.get(f"{base}/content", headers=owner_headers).status_code == 404
        assert client.post(f"{base}/recrawl", headers=owner_headers).status_code == 404
        assert client.delete(base, headers=owner_headers).status_code == 404
        db.expire_all()
        assert db.get(DomainUrl, u) is not None

    def test_job_of_other_domain_404(self, client, fake_app, fake_domain, sibling, owner_headers, db):
        j = sibling["job"].id
        base = f"{BASE}/{fake_app.app_id}/domains/{fake_domain.domain_id}/crawl-jobs/{j}"
        assert client.get(base, headers=owner_headers).status_code == 404
        assert client.post(f"{base}/cancel", headers=owner_headers).status_code == 404
        db.expire_all()
        assert db.get(CrawlJob, j).status == CrawlJobStatus.QUEUED


class TestOwnAppStillWorks:
    def test_get_new_domain_form(self, client, fake_app, owner_headers, db):
        r = client.get(f"{BASE}/{fake_app.app_id}/domains/0", headers=owner_headers)
        assert r.status_code == 200
        assert r.json()["domain_id"] == 0

    def test_read_routes(self, client, fake_app, fake_domain, own_url, owner_headers, db):
        d = fake_domain.domain_id
        for path in ("", "/urls", f"/urls/{own_url.id}", "/crawl-policy", "/crawl-jobs"):
            r = client.get(f"{BASE}/{fake_app.app_id}/domains/{d}{path}", headers=owner_headers)
            assert r.status_code == 200, (path, r.text)

    def test_update_and_policy(self, client, fake_app, fake_domain, owner_headers, db):
        d = fake_domain.domain_id
        r = client.put(
            f"{BASE}/{fake_app.app_id}/domains/{d}",
            json={"name": "Renamed", "description": "x", "base_url": "https://example.com", "content_tag": "body"},
            headers=owner_headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "Renamed"
        r = client.put(
            f"{BASE}/{fake_app.app_id}/domains/{d}/crawl-policy",
            json={"seed_url": "https://example.com", "is_active": False},
            headers=owner_headers,
        )
        assert r.status_code == 200, r.text

    def test_trigger_cancel_and_delete_url(self, client, fake_app, fake_domain, own_url, owner_headers, db):
        d = fake_domain.domain_id
        r = client.post(f"{BASE}/{fake_app.app_id}/domains/{d}/crawl-jobs", headers=owner_headers)
        assert r.status_code == 202
        job_id = r.json()["job_id"]
        r = client.post(f"{BASE}/{fake_app.app_id}/domains/{d}/crawl-jobs/{job_id}/cancel", headers=owner_headers)
        assert r.status_code == 200
        r = client.delete(f"{BASE}/{fake_app.app_id}/domains/{d}/urls/{own_url.id}", headers=owner_headers)
        assert r.status_code == 200


class TestEveryDomainIdRouteIsGuarded:
    def test_all_domain_id_routes_have_scope_dependency(self):
        from routers.controls.domain_scope import (
            validate_domain_app_ownership,
            validate_domain_app_ownership_allow_new,
        )
        from routers.internal.domains import domains_router

        guards = {validate_domain_app_ownership, validate_domain_app_ownership_allow_new}
        checked = 0
        for route in domains_router.routes:
            if "{domain_id}" not in route.path:
                continue
            deps = {d.dependency for d in route.dependencies}
            assert deps & guards, f"{sorted(route.methods)} {route.path} lacks the domain scope dependency"
            if validate_domain_app_ownership_allow_new in deps:
                assert route.path == "/{domain_id}" and route.methods == {"GET"}
            checked += 1
        assert checked == ROUTE_COUNT
