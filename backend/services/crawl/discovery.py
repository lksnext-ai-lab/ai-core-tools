"""URL discovery pipeline for a CrawlPolicy."""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator, Optional, Set
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import aiohttp

from models.crawl_policy import CrawlPolicy
from models.enums.discovery_source import DiscoverySource
from models.enums.domain_url_status import DomainUrlStatus
from services.crawl.normalization import normalize_url, same_host
from services.crawl.glob_matcher import should_include
from services.crawl.http_fetcher import fetch, parse_html_links, parse_sitemap
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class DomainUrlCandidate:
    """Candidate URL discovered during a crawl run."""
    url: str
    normalized_url: str
    discovered_via: DiscoverySource
    depth: int = 0
    sitemap_lastmod: Optional[datetime] = None
    status: DomainUrlStatus = DomainUrlStatus.PENDING
    last_error: Optional[str] = None


async def discover_urls(
    policy: CrawlPolicy,
    robots_parser: Optional[RobotFileParser],
    session: aiohttp.ClientSession,
    existing_normalized: Set[str],
) -> AsyncIterator[DomainUrlCandidate]:
    """
    Yield DomainUrlCandidate objects for all URLs discovered by this policy.
    Order: manual → sitemap → recursive crawl.
    Deduplicates using `existing_normalized` set (updated in-place).
    """
    # --- Manual URLs ---
    for raw_url in (policy.manual_urls or []):
        url = raw_url.strip()
        if not url:
            continue
        norm = normalize_url(url)
        if norm in existing_normalized:
            continue
        existing_normalized.add(norm)
        yield DomainUrlCandidate(
            url=url,
            normalized_url=norm,
            discovered_via=DiscoverySource.MANUAL,
            depth=0,
        )

    # --- Sitemap ---
    if policy.sitemap_url:
        async for candidate in _discover_from_sitemap(policy, session, existing_normalized, robots_parser):
            yield candidate

    # --- Recursive crawl ---
    if policy.seed_url:
        async for candidate in _discover_from_crawl(policy, session, existing_normalized, robots_parser):
            yield candidate


async def _discover_from_sitemap(
    policy: CrawlPolicy,
    session: aiohttp.ClientSession,
    existing_normalized: Set[str],
    robots_parser: Optional[RobotFileParser],
) -> AsyncIterator[DomainUrlCandidate]:
    """Fetch and parse sitemap(s), yield candidates."""
    sitemap_urls_to_fetch = [policy.sitemap_url]

    for sitemap_url in sitemap_urls_to_fetch:
        result = await fetch(sitemap_url, session=session)
        if result.status_code != 200 or not result.content:
            logger.warning(f"Failed to fetch sitemap {sitemap_url}: {result.status_code} {result.error}")
            continue

        entries = parse_sitemap(result.content)
        for loc, lastmod in entries:
            norm = normalize_url(loc)

            # Check if this is a child sitemap (sitemapindex pattern)
            if loc.endswith('.xml') or 'sitemap' in loc.lower():
                # Could be a child sitemap — fetch it too (one level deep)
                child_result = await fetch(loc, session=session)
                if child_result.status_code == 200 and child_result.content:
                    child_entries = parse_sitemap(child_result.content)
                    for child_loc, child_lastmod in child_entries:
                        child_norm = normalize_url(child_loc)
                        if child_norm in existing_normalized:
                            continue
                        candidate = _make_sitemap_candidate(child_loc, child_norm, child_lastmod, policy, robots_parser)
                        if candidate:
                            existing_normalized.add(child_norm)
                            yield candidate
                continue

            if norm in existing_normalized:
                continue
            candidate = _make_sitemap_candidate(loc, norm, lastmod, policy, robots_parser)
            if candidate:
                existing_normalized.add(norm)
                yield candidate


def _make_sitemap_candidate(
    url: str,
    norm: str,
    lastmod: Optional[datetime],
    policy: CrawlPolicy,
    robots_parser: Optional[RobotFileParser],
) -> Optional[DomainUrlCandidate]:
    """Build a DomainUrlCandidate from a sitemap entry, applying robots and glob filters."""
    from urllib.parse import urlparse
    parsed = urlparse(url)

    # Robots check
    if policy.respect_robots_txt and robots_parser:
        if not robots_parser.can_fetch('*', url):
            return DomainUrlCandidate(
                url=url, normalized_url=norm,
                discovered_via=DiscoverySource.SITEMAP, depth=0,
                sitemap_lastmod=lastmod,
                status=DomainUrlStatus.EXCLUDED,
                last_error='robots disallow',
            )

    # Glob filter
    path_and_query = parsed.path + ('?' + parsed.query if parsed.query else '')
    if not should_include(url, policy.include_globs or [], policy.exclude_globs or []):
        return DomainUrlCandidate(
            url=url, normalized_url=norm,
            discovered_via=DiscoverySource.SITEMAP, depth=0,
            sitemap_lastmod=lastmod,
            status=DomainUrlStatus.EXCLUDED,
            last_error='glob filter',
        )

    return DomainUrlCandidate(
        url=url,
        normalized_url=norm,
        discovered_via=DiscoverySource.SITEMAP,
        depth=0,
        sitemap_lastmod=lastmod,
    )


async def _discover_from_crawl(
    policy: CrawlPolicy,
    session: aiohttp.ClientSession,
    existing_normalized: Set[str],
    robots_parser: Optional[RobotFileParser],
) -> AsyncIterator[DomainUrlCandidate]:
    """BFS recursive crawl from policy.seed_url."""
    seed = policy.seed_url
    max_depth = policy.max_depth
    rate_limit_rps = policy.rate_limit_rps or 1.0

    # BFS queue: (url, depth)
    queue = [(seed, 0)]
    visited = set()

    while queue:
        url, depth = queue.pop(0)
        norm = normalize_url(url)

        if norm in visited:
            continue
        visited.add(norm)

        # Cross-host check
        if not same_host(url, seed):
            if norm not in existing_normalized:
                existing_normalized.add(norm)
                yield DomainUrlCandidate(
                    url=url, normalized_url=norm,
                    discovered_via=DiscoverySource.CRAWL, depth=depth,
                    status=DomainUrlStatus.EXCLUDED,
                    last_error='cross-host',
                )
            continue

        # Robots check
        if policy.respect_robots_txt and robots_parser:
            if not robots_parser.can_fetch('*', url):
                if norm not in existing_normalized:
                    existing_normalized.add(norm)
                    yield DomainUrlCandidate(
                        url=url, normalized_url=norm,
                        discovered_via=DiscoverySource.CRAWL, depth=depth,
                        status=DomainUrlStatus.EXCLUDED,
                        last_error='robots disallow',
                    )
                continue

        # Glob filter
        if not should_include(url, policy.include_globs or [], policy.exclude_globs or []):
            if norm not in existing_normalized:
                existing_normalized.add(norm)
                yield DomainUrlCandidate(
                    url=url, normalized_url=norm,
                    discovered_via=DiscoverySource.CRAWL, depth=depth,
                    status=DomainUrlStatus.EXCLUDED,
                    last_error='glob filter',
                )
            continue

        # Yield this URL as a candidate (if not already seen from manual/sitemap)
        if norm not in existing_normalized:
            existing_normalized.add(norm)
            yield DomainUrlCandidate(
                url=url,
                normalized_url=norm,
                discovered_via=DiscoverySource.CRAWL,
                depth=depth,
            )

        # Crawl further if within depth limit
        if depth < max_depth:
            await asyncio.sleep(1.0 / rate_limit_rps)
            result = await fetch(url, session=session)
            if result.status_code == 200 and result.content:
                links = parse_html_links(url, result.content)
                for link in links:
                    link_norm = normalize_url(link)
                    if link_norm not in visited:
                        queue.append((link, depth + 1))
