"""
Integration tests for CrawlExecutorService using an in-process aiohttp mock HTTP server.

These tests run against the real test PostgreSQL database (via SessionLocal, just like
the production worker does). They depend on the session-scoped `test_engine` fixture
to ensure the schema is created before the executor's own SessionLocal() calls run.

Isolation: each test creates its own App/Domain/Policy/Job in the DB with real commits.
Teardown cleans up via cascading deletes on the App.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestServer

from db.database import SessionLocal
from models.app import App
from models.user import User
from models.domain import Domain
from models.crawl_job import CrawlJob
from models.crawl_policy import CrawlPolicy
from models.domain_url import DomainUrl
from models.enums.crawl_job_status import CrawlJobStatus
from models.enums.crawl_trigger import CrawlTrigger
from models.enums.domain_url_status import DomainUrlStatus
from models.enums.discovery_source import DiscoverySource
from models.silo import Silo
from services.crawl.normalization import normalize_url
from services.crawl_executor_service import CrawlExecutorService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sitemap_xml(*urls_with_lastmod) -> bytes:
    """Build a minimal sitemap XML with the given (url, lastmod_or_None) pairs."""
    entries = []
    for url, lastmod in urls_with_lastmod:
        loc = f"<loc>{url}</loc>"
        lm = f"<lastmod>{lastmod}</lastmod>" if lastmod else ""
        entries.append(f"<url>{loc}{lm}</url>")
    inner = "\n".join(entries)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{inner}"
        "</urlset>"
    ).encode()


def _setup_test_domain_and_job(
    db,
    seed_url: Optional[str] = None,
    sitemap_url: Optional[str] = None,
    manual_urls: Optional[list] = None,
    max_depth: int = 1,
    respect_robots_txt: bool = False,
) -> tuple:
    """
    Create a User, App, Domain, CrawlPolicy, and CrawlJob directly in the DB with real commits.
    Returns (domain, policy, job, app_id). Caller is responsible for cleanup.
    """
    # Create test user (allow duplicate email — use a unique one per test via timestamp)
    user = User(
        name="Executor Test User",
        email=f"executor-test-{datetime.utcnow().timestamp()}@test.com",
        is_active=True,
    )
    db.add(user)
    db.flush()

    # Create app
    app = App(name="Executor Test App", owner_id=user.user_id)
    db.add(app)
    db.flush()

    # Create a silo (required by Domain FK)
    silo = Silo(
        name="Executor Test Silo",
        silo_type="DOMAIN",
        app_id=app.app_id,
        vector_db_type="PGVECTOR",
    )
    db.add(silo)
    db.flush()

    # Create domain
    domain = Domain(
        name="Mock Site",
        base_url=seed_url or "http://localhost",
        app_id=app.app_id,
        silo_id=silo.silo_id,
        content_tag="body",
        create_date=datetime.utcnow(),
    )
    db.add(domain)
    db.flush()

    # Create crawl policy
    policy = CrawlPolicy(
        domain_id=domain.domain_id,
        seed_url=seed_url,
        sitemap_url=sitemap_url,
        manual_urls=manual_urls or [],
        max_depth=max_depth,
        include_globs=[],
        exclude_globs=[],
        rate_limit_rps=10.0,  # fast for tests
        refresh_interval_hours=168,
        respect_robots_txt=respect_robots_txt,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(policy)
    db.flush()

    # Create crawl job (already RUNNING — simulates being claimed by a worker)
    job = CrawlJob(
        domain_id=domain.domain_id,
        status=CrawlJobStatus.RUNNING,
        triggered_by=CrawlTrigger.MANUAL,
        started_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
    )
    db.add(job)
    db.flush()
    db.commit()  # real commit so SessionLocal() in executor can see these rows

    return domain, policy, job, app.app_id


def _cleanup(app_id: int):
    """Delete the test App and all cascade-deleted children."""
    db = SessionLocal()
    try:
        app = db.query(App).filter(App.app_id == app_id).first()
        if app:
            db.delete(app)
            db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tests — each opens its own SessionLocal for verification
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sitemap_discovery_creates_domain_urls(test_engine):
    """Sitemap-only policy: executor discovers and creates DomainUrl rows."""
    setup_db = SessionLocal()
    mock_app = web.Application()
    domain_id = None
    app_id = None

    async def sitemap_handler(request):
        xml = _sitemap_xml(
            ("http://testhost/", "2025-01-01"),
            ("http://testhost/docs/page-1", "2025-01-01"),
            ("http://testhost/docs/page-2", None),
            ("http://testhost/gone", None),
        )
        return web.Response(body=xml, content_type="application/xml")

    async def page_handler(request):
        return web.Response(
            body=b"<html><body>Content</body></html>",
            content_type="text/html",
        )

    async def gone_handler(request):
        return web.Response(status=404)

    mock_app.router.add_get("/sitemap.xml", sitemap_handler)
    mock_app.router.add_get("/", page_handler)
    mock_app.router.add_get("/docs/page-1", page_handler)
    mock_app.router.add_get("/docs/page-2", page_handler)
    mock_app.router.add_get("/gone", gone_handler)

    server = TestServer(mock_app, host="127.0.0.1")
    await server.start_server()
    base_url = f"http://127.0.0.1:{server.port}"

    try:
        domain, policy, job, app_id = _setup_test_domain_and_job(
            setup_db,
            sitemap_url=f"{base_url}/sitemap.xml",
        )
        domain_id = domain.domain_id
        job_id = job.id
        setup_db.close()

        with patch("services.crawl_executor_service.RobotFileParser"):
            await CrawlExecutorService.run_job(job_id)

        # Verify in a fresh session
        verify_db = SessionLocal()
        try:
            domain_urls = verify_db.query(DomainUrl).filter(
                DomainUrl.domain_id == domain_id
            ).all()
            url_strings = [u.url for u in domain_urls]
            assert any("/docs/page-1" in u for u in url_strings), f"page-1 missing from {url_strings}"
            assert any("/docs/page-2" in u for u in url_strings), f"page-2 missing from {url_strings}"
            assert any("/gone" in u for u in url_strings), f"gone missing from {url_strings}"

            job_row = verify_db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
            assert job_row.status == CrawlJobStatus.COMPLETED
        finally:
            verify_db.close()

    finally:
        await server.close()
        if app_id:
            _cleanup(app_id)


@pytest.mark.asyncio
async def test_404_marks_removed(test_engine):
    """A URL returning 404 should be marked REMOVED and job.removed_count incremented."""
    setup_db = SessionLocal()
    mock_app = web.Application()
    app_id = None

    async def gone_handler(request):
        return web.Response(status=404)

    mock_app.router.add_get("/gone-page", gone_handler)

    server = TestServer(mock_app, host="127.0.0.1")
    await server.start_server()
    base_url = f"http://127.0.0.1:{server.port}"

    try:
        domain, policy, job, app_id = _setup_test_domain_and_job(
            setup_db,
            manual_urls=[f"{base_url}/gone-page"],
        )
        domain_id = domain.domain_id
        job_id = job.id
        setup_db.close()

        with patch("services.crawl_executor_service.RobotFileParser"):
            await CrawlExecutorService.run_job(job_id)

        verify_db = SessionLocal()
        try:
            domain_urls = verify_db.query(DomainUrl).filter(
                DomainUrl.domain_id == domain_id
            ).all()
            gone_url = next((u for u in domain_urls if "/gone-page" in u.url), None)
            assert gone_url is not None, f"URL not found in {[u.url for u in domain_urls]}"
            assert gone_url.status == DomainUrlStatus.REMOVED

            job_row = verify_db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
            assert job_row.removed_count >= 1
        finally:
            verify_db.close()

    finally:
        await server.close()
        if app_id:
            _cleanup(app_id)


@pytest.mark.asyncio
async def test_5xx_marks_failed_with_backoff(test_engine):
    """A URL returning 503 should be marked FAILED with exponential backoff."""
    setup_db = SessionLocal()
    mock_app = web.Application()
    app_id = None

    async def flaky_handler(request):
        return web.Response(status=503)

    mock_app.router.add_get("/flaky", flaky_handler)

    server = TestServer(mock_app, host="127.0.0.1")
    await server.start_server()
    base_url = f"http://127.0.0.1:{server.port}"

    try:
        domain, policy, job, app_id = _setup_test_domain_and_job(
            setup_db,
            manual_urls=[f"{base_url}/flaky"],
        )
        domain_id = domain.domain_id
        job_id = job.id
        setup_db.close()

        with patch("services.crawl_executor_service.RobotFileParser"):
            await CrawlExecutorService.run_job(job_id)

        verify_db = SessionLocal()
        try:
            domain_urls = verify_db.query(DomainUrl).filter(
                DomainUrl.domain_id == domain_id
            ).all()
            flaky_url = next((u for u in domain_urls if "/flaky" in u.url), None)
            assert flaky_url is not None
            assert flaky_url.status == DomainUrlStatus.FAILED
            assert flaky_url.failure_count >= 1
            # Backoff: 2^failure_count hours — with failure_count=1 → 2 hours
            assert flaky_url.next_crawl_at is not None
            assert flaky_url.next_crawl_at > datetime.utcnow()

            job_row = verify_db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
            assert job_row.failed_count >= 1
        finally:
            verify_db.close()

    finally:
        await server.close()
        if app_id:
            _cleanup(app_id)


@pytest.mark.asyncio
async def test_200_indexes_content(test_engine):
    """A URL returning 200 with HTML content should be indexed (INDEXED status)."""
    setup_db = SessionLocal()
    mock_app = web.Application()
    app_id = None

    async def page_handler(request):
        return web.Response(
            body=b"<html><body>Test content for indexing</body></html>",
            content_type="text/html",
        )

    mock_app.router.add_get("/page", page_handler)

    server = TestServer(mock_app, host="127.0.0.1")
    await server.start_server()
    base_url = f"http://127.0.0.1:{server.port}"

    try:
        domain, policy, job, app_id = _setup_test_domain_and_job(
            setup_db,
            manual_urls=[f"{base_url}/page"],
        )
        domain_id = domain.domain_id
        job_id = job.id
        setup_db.close()

        with patch("services.crawl_executor_service.RobotFileParser"):
            await CrawlExecutorService.run_job(job_id)

        verify_db = SessionLocal()
        try:
            domain_urls = verify_db.query(DomainUrl).filter(
                DomainUrl.domain_id == domain_id
            ).all()
            page_url = next((u for u in domain_urls if "/page" in u.url), None)
            assert page_url is not None
            assert page_url.status == DomainUrlStatus.INDEXED
            assert page_url.content_hash is not None
            assert page_url.last_indexed_at is not None

            job_row = verify_db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
            assert job_row.indexed_count >= 1
            assert job_row.status == CrawlJobStatus.COMPLETED
        finally:
            verify_db.close()

    finally:
        await server.close()
        if app_id:
            _cleanup(app_id)


@pytest.mark.asyncio
async def test_conditional_get_304_marks_skipped(test_engine):
    """Second fetch of URL with ETag returns 304 — marks skipped (no re-indexing)."""
    setup_db = SessionLocal()
    mock_app = web.Application()
    app_id = None

    async def page2_handler(request):
        etag = '"abc123"'
        if request.headers.get("If-None-Match") == etag:
            return web.Response(status=304)
        return web.Response(
            body=b"<html><body>Page 2 content</body></html>",
            content_type="text/html",
            headers={"ETag": etag},
        )

    mock_app.router.add_get("/docs/page-2", page2_handler)

    server = TestServer(mock_app, host="127.0.0.1")
    await server.start_server()
    base_url = f"http://127.0.0.1:{server.port}"

    try:
        domain, policy, job, app_id = _setup_test_domain_and_job(
            setup_db,
            manual_urls=[f"{base_url}/docs/page-2"],
        )
        domain_id = domain.domain_id
        job_id = job.id
        setup_db.close()

        # First run — full fetch, stores ETag
        with patch("services.crawl_executor_service.RobotFileParser"):
            await CrawlExecutorService.run_job(job_id)

        verify_db = SessionLocal()
        try:
            page2 = verify_db.query(DomainUrl).filter(
                DomainUrl.domain_id == domain_id
            ).first()
            assert page2 is not None
            assert page2.status == DomainUrlStatus.INDEXED
            assert page2.http_etag == '"abc123"'

            # Second run with same ETag → 304 → skipped
            job2 = CrawlJob(
                domain_id=domain_id,
                status=CrawlJobStatus.RUNNING,
                triggered_by=CrawlTrigger.MANUAL,
                started_at=datetime.utcnow(),
                created_at=datetime.utcnow(),
            )
            verify_db.add(job2)
            verify_db.commit()
            job2_id = job2.id
        finally:
            verify_db.close()

        with patch("services.crawl_executor_service.RobotFileParser"):
            await CrawlExecutorService.run_job(job2_id)

        verify_db2 = SessionLocal()
        try:
            page2_after = verify_db2.query(DomainUrl).filter(
                DomainUrl.domain_id == domain_id
            ).first()
            job2_row = verify_db2.query(CrawlJob).filter(CrawlJob.id == job2_id).first()

            assert page2_after.status == DomainUrlStatus.INDEXED
            assert job2_row.skipped_count >= 1
            assert job2_row.indexed_count == 0  # no new indexing — it was 304
        finally:
            verify_db2.close()

    finally:
        await server.close()
        if app_id:
            _cleanup(app_id)


@pytest.mark.asyncio
async def test_sitemap_dedup_with_crawl(test_engine):
    """A URL that appears in both sitemap and crawl discovery is stored only once."""
    setup_db = SessionLocal()
    mock_app = web.Application()
    app_id = None

    # port is set after server.start_server(); use a closure that resolves it lazily
    _server_port_holder: list = [None]

    async def sitemap_handler(request):
        port = _server_port_holder[0]
        xml = _sitemap_xml(
            (f"http://127.0.0.1:{port}/docs/page-1", "2025-01-01"),
        )
        return web.Response(body=xml, content_type="application/xml")

    async def home_handler(request):
        html = b'<html><body><a href="/docs/page-1">Page 1</a></body></html>'
        return web.Response(body=html, content_type="text/html")

    async def page1_handler(request):
        return web.Response(
            body=b"<html><body>Page 1</body></html>",
            content_type="text/html",
        )

    mock_app.router.add_get("/sitemap.xml", sitemap_handler)
    mock_app.router.add_get("/", home_handler)
    mock_app.router.add_get("/docs/page-1", page1_handler)

    server = TestServer(mock_app, host="127.0.0.1")
    await server.start_server()
    base_url = f"http://127.0.0.1:{server.port}"
    _server_port_holder[0] = server.port  # set port so sitemap_handler can use it

    try:
        domain, policy, job, app_id = _setup_test_domain_and_job(
            setup_db,
            seed_url=f"{base_url}/",
            sitemap_url=f"{base_url}/sitemap.xml",
            max_depth=1,
        )
        domain_id = domain.domain_id
        job_id = job.id
        setup_db.close()

        with patch("services.crawl_executor_service.RobotFileParser"):
            await CrawlExecutorService.run_job(job_id)

        verify_db = SessionLocal()
        try:
            domain_urls = verify_db.query(DomainUrl).filter(
                DomainUrl.domain_id == domain_id
            ).all()
            page1_rows = [u for u in domain_urls if "/docs/page-1" in u.url]
            assert len(page1_rows) == 1, (
                f"Expected exactly 1 row for /docs/page-1, got {len(page1_rows)}: "
                f"{[u.url for u in page1_rows]}"
            )
        finally:
            verify_db.close()

    finally:
        await server.close()
        if app_id:
            _cleanup(app_id)
