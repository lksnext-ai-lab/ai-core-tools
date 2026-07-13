"""Regression test for Issue #183.

Bug: CrawlExecutorService.run_job finishes with indexed=0 when robots.txt blocks
all discovered URLs, but the finish-log line omits an 'excluded=' count.
Operators cannot distinguish "no URLs found" from "all URLs were robots-blocked".

This test MUST FAIL on the current code and PASS after the fix.

Reproduce-first step — do NOT modify application code here.
"""
import logging
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Set deployment-mode env var before any backend import so config initialises cleanly.
os.environ.setdefault("AICT_DEPLOYMENT_MODE", "self_managed")
os.environ.setdefault("SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
os.environ.setdefault("REPO_BASE_FOLDER", "./data/repositories")

from models.enums.crawl_job_status import CrawlJobStatus
from models.enums.domain_url_status import DomainUrlStatus
from models.enums.discovery_source import DiscoverySource
from services.crawl.discovery import DomainUrlCandidate
from services.crawl_executor_service import CrawlExecutorService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job(job_id: int = 1, domain_id: int = 42) -> MagicMock:
    """Return a MagicMock that looks like a CrawlJob with integer counters."""
    job = MagicMock()
    job.id = job_id
    job.domain_id = domain_id
    job.status = CrawlJobStatus.QUEUED
    job.indexed_count = 0
    job.skipped_count = 0
    job.removed_count = 0
    job.failed_count = 0
    job.discovered_count = 0
    job.error_log = None
    return job


def _make_domain(domain_id: int = 42) -> MagicMock:
    domain = MagicMock()
    domain.domain_id = domain_id
    domain.silo_id = None
    domain.content_tag = "body"
    domain.content_id = None
    domain.content_class = None
    return domain


def _make_policy(domain_id: int = 42) -> MagicMock:
    """CrawlPolicy with seed_url set and respect_robots_txt=True."""
    policy = MagicMock()
    policy.domain_id = domain_id
    policy.seed_url = "http://example.test"
    policy.sitemap_url = None
    policy.respect_robots_txt = True
    policy.rate_limit_rps = 0.0   # skip rate-limit sleep inside the service
    policy.refresh_interval_hours = 168
    policy.include_globs = []
    policy.exclude_globs = []
    policy.manual_urls = []
    return policy


async def _one_excluded_candidate(*args, **kwargs):
    """Async generator: yields a single robots-blocked candidate."""
    yield DomainUrlCandidate(
        url="http://example.test/page",
        normalized_url="http://example.test/page",
        discovered_via=DiscoverySource.CRAWL,
        depth=1,
        status=DomainUrlStatus.EXCLUDED,
        last_error="robots disallow",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRobotsExcludedCountInFinishLog:
    """Issue #183 — finish log must include 'excluded=' when robots blocks all URLs."""

    @pytest.mark.asyncio
    async def test_finish_log_contains_excluded_count_when_all_urls_are_robots_blocked(
        self, caplog, capsys
    ):
        """
        When robots.txt blocks every discovered URL the finish log must contain
        'excluded=<N>' so operators can diagnose why indexed=0.

        Current code emits:
            "Job 1 finished: indexed=0, skipped=0, removed=0, failed=0"

        Expected after fix (something like):
            "Job 1 finished: indexed=0, skipped=0, removed=0, failed=0, excluded=1"

        This assertion FAILS on the current code because 'excluded=' is absent.
        """
        job_id = 1
        mock_job = _make_job(job_id=job_id, domain_id=42)
        mock_domain = _make_domain(domain_id=42)
        mock_policy = _make_policy(domain_id=42)

        # Minimal DB session mock.
        # Phase 1 — existing_normalized set: db.query(...).filter(...).all() → []
        # Phase 1 — per-candidate check:     db.query(...).filter(...).first() → None
        # Phase 2 — fetch_urls:              db.query(...).filter(...).all() → []
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # aiohttp.ClientSession is used as an async context manager in two places.
        mock_aiohttp_session = MagicMock()
        mock_aiohttp_session.__aenter__ = AsyncMock(return_value=mock_aiohttp_session)
        mock_aiohttp_session.__aexit__ = AsyncMock(return_value=False)

        with (
            # Inject our mock DB session so no real DB is needed.
            patch(
                "services.crawl_executor_service.SessionLocal",
                return_value=mock_db,
            ),
            # Repository-level patches — avoids complex db.query chain wiring.
            patch(
                "services.crawl_executor_service.CrawlJobRepository.get_by_id",
                return_value=mock_job,
            ),
            patch(
                "services.crawl_executor_service.DomainRepository.get_by_id",
                return_value=mock_domain,
            ),
            patch(
                "services.crawl_executor_service.CrawlPolicyRepository.get_by_domain",
                return_value=mock_policy,
            ),
            # Stub the discovery pipeline to yield one EXCLUDED candidate.
            patch(
                "services.crawl_executor_service.discover_urls",
                side_effect=_one_excluded_candidate,
            ),
            # Prevent real network calls for robots.txt fetch.
            patch("urllib.robotparser.RobotFileParser.read"),
            patch(
                "urllib.robotparser.RobotFileParser.can_fetch",
                return_value=False,
            ),
            # Prevent real HTTP connections inside the fetch phase.
            patch(
                "services.crawl_executor_service.aiohttp.ClientSession",
                return_value=mock_aiohttp_session,
            ),
            # Replace the module logger with a mock to reliably capture the finish/info calls
            patch("services.crawl_executor_service.logger") as mock_logger,
        ):
            with caplog.at_level(logging.INFO):
                # Patches are active on the module namespace; run_job picks them up.
                await CrawlExecutorService.run_job(job_id)

        # Locate the finish-summary log line via caplog first.
        finish_lines = [
            r.message
            for r in caplog.records
            if "finished" in r.message and str(job_id) in r.message
        ]
        # Fallback to captured stdout if caplog didn't capture the module logger
        if not finish_lines:
            out = capsys.readouterr().out
            finish_lines = [
                line for line in out.splitlines() if "finished" in line and str(job_id) in line
            ]

        # If still not found, and we patched the module logger, inspect its calls.
        if not finish_lines and "mock_logger" in locals():
            try:
                mock_logger.info.assert_called()
                finish_calls = [
                    call for call in mock_logger.info.call_args_list if f"Job {job_id} finished" in str(call)
                ]
                if finish_calls:
                    finish_lines = [str(finish_calls[-1])]
            except Exception:
                pass

        assert finish_lines, (
            "No 'finished' log line was emitted — service may have raised an error "
            "before reaching the finish block. Check caplog/captured stdout/mock_logger for details."
        )
        finish_log = finish_lines[-1]

        # ------------------------------------------------------------------
        # BUG ASSERTION (Issue #183)
        # This assertion FAILS on the current code because the finish log
        # does not include an 'excluded=' counter.
        # ------------------------------------------------------------------
        assert "excluded=" in finish_log, (
            f"Finish log is missing 'excluded=' counter (Issue #183).\n"
            f"Actual finish log:  {finish_log!r}\n"
            f"Expected to contain: 'excluded='"
        )
