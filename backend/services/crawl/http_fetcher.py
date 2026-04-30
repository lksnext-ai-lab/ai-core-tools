"""HTTP fetching utilities for the crawl pipeline."""
import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

import aiohttp
from bs4 import BeautifulSoup

from utils.logger import get_logger

logger = get_logger(__name__)

# XML namespaces used in sitemaps
_SITEMAP_NS = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}


@dataclass
class FetchResult:
    status_code: int
    content: Optional[bytes] = None
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    error: Optional[str] = None


async def fetch(
    url: str,
    etag: Optional[str] = None,
    last_modified: Optional[str] = None,
    timeout: float = 30.0,
    session: Optional[aiohttp.ClientSession] = None,
) -> FetchResult:
    """
    Fetch a URL, optionally sending conditional GET headers.
    Returns a FetchResult. On error, status_code=0 and error is set.
    """
    headers = {}
    if etag:
        headers['If-None-Match'] = etag
    if last_modified:
        headers['If-Modified-Since'] = last_modified

    close_session = session is None
    if session is None:
        session = aiohttp.ClientSession()

    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            status_code = resp.status
            response_etag = resp.headers.get('ETag')
            response_last_modified = resp.headers.get('Last-Modified')

            content = None
            if status_code == 200:
                content = await resp.read()

            return FetchResult(
                status_code=status_code,
                content=content,
                etag=response_etag,
                last_modified=response_last_modified,
            )
    except asyncio.TimeoutError as e:
        return FetchResult(status_code=0, error=f'Timeout: {e}')
    except aiohttp.ClientError as e:
        return FetchResult(status_code=0, error=f'ClientError: {e}')
    except Exception as e:
        return FetchResult(status_code=0, error=f'Error: {e}')
    finally:
        if close_session:
            await session.close()


def parse_html_links(base_url: str, html_bytes: bytes) -> List[str]:
    """
    Extract all <a href> links from HTML, resolve to absolute URLs, return unique list.
    """
    try:
        soup = BeautifulSoup(html_bytes, 'html.parser')
        seen = set()
        links = []
        for tag in soup.find_all('a', href=True):
            href = tag['href'].strip()
            if not href or href.startswith('#') or href.startswith('javascript:') or href.startswith('mailto:'):
                continue
            absolute = urljoin(base_url, href)
            # Strip fragment
            absolute = absolute.split('#')[0]
            if absolute not in seen:
                seen.add(absolute)
                links.append(absolute)
        return links
    except Exception as e:
        logger.warning(f"Failed to parse HTML links from {base_url}: {e}")
        return []


def parse_sitemap(sitemap_bytes: bytes) -> List[Tuple[str, Optional[datetime]]]:
    """
    Parse a sitemap XML.
    Returns list of (url, lastmod_or_None) tuples.
    For <sitemapindex>, returns tuples where url is a child sitemap URL and lastmod may be None.
    The caller can distinguish by checking if the returned URLs are sitemaps themselves.
    """
    try:
        root = ET.fromstring(sitemap_bytes)
    except ET.ParseError as e:
        logger.warning(f"Failed to parse sitemap XML: {e}")
        return []

    # Strip namespace from tag
    tag = root.tag
    if '}' in tag:
        tag = tag.split('}', 1)[1]

    results = []

    if tag == 'sitemapindex':
        # Child sitemaps
        for sitemap_el in root.iter('{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap'):
            loc_el = sitemap_el.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
            if loc_el is not None and loc_el.text:
                results.append((loc_el.text.strip(), None))
    else:
        # Regular <urlset>
        for url_el in root.iter('{http://www.sitemaps.org/schemas/sitemap/0.9}url'):
            loc_el = url_el.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
            lastmod_el = url_el.find('{http://www.sitemaps.org/schemas/sitemap/0.9}lastmod')

            if loc_el is None or not loc_el.text:
                continue

            loc = loc_el.text.strip()
            lastmod = None
            if lastmod_el is not None and lastmod_el.text:
                try:
                    lastmod = datetime.fromisoformat(lastmod_el.text.strip()[:10])
                except ValueError:
                    pass

            results.append((loc, lastmod))

    return results
