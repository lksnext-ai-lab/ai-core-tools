"""URL normalization utilities for the crawl pipeline."""
from urllib.parse import urlparse, urlunparse, urlencode, parse_qsl
import re
from typing import Optional

# Tracking parameters to strip from URLs
_TRACKING_PARAMS = frozenset({
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'gclid', 'fbclid', 'mc_cid', 'mc_eid',
    'msclkid', 'dclid', '_ga', '_gl',
})


def normalize_url(url: str) -> str:
    """
    Normalize a URL for deduplication:
    - Lowercase scheme and host
    - Drop default ports (:80 for http, :443 for https)
    - Strip fragment
    - Strip tracking params (utm_*, gclid, fbclid, mc_cid, mc_eid)
    - Collapse // in path
    - Strip trailing slash unless path is '/'
    """
    parsed = urlparse(url)

    # Lowercase scheme and host
    scheme = parsed.scheme.lower()
    host = parsed.hostname or ''
    port = parsed.port

    # Drop default ports
    netloc = host
    if port is not None:
        if not (scheme == 'http' and port == 80) and not (scheme == 'https' and port == 443):
            netloc = f'{host}:{port}'

    # Normalise path: collapse double slashes
    path = re.sub(r'/+', '/', parsed.path)

    # Strip trailing slash unless path is exactly '/'
    if len(path) > 1 and path.endswith('/'):
        path = path.rstrip('/')

    # Strip tracking params
    query_pairs = [(k, v) for k, v in parse_qsl(parsed.query) if k.lower() not in _TRACKING_PARAMS]
    query = urlencode(query_pairs)

    # Drop fragment entirely
    normalized = urlunparse((scheme, netloc, path, parsed.params, query, ''))
    return normalized


def same_host(url_a: str, url_b: str) -> bool:
    """Returns True if both URLs have the same netloc (host[:port])."""
    return urlparse(url_a).netloc == urlparse(url_b).netloc
