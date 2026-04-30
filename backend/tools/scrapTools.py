from collections import Counter
import requests
from bs4 import BeautifulSoup
from typing import Callable, Optional
from utils.logger import get_logger

logger = get_logger(__name__)


def remove_duplicates_and_sort(arr):
    """
    Remove duplicates from array and sort by frequency

    Args:
        arr: List of items

    Returns:
        Sorted list with duplicates removed
    """
    counts = Counter(arr)
    sorted_arr = sorted(counts, key=lambda x: counts[x], reverse=True)
    return sorted_arr


def get_text_from_url(url: str, tag: str = "body", id: Optional[str] = None, class_name: Optional[str] = None) -> str:
    """
    Extract text content from a web page using specified HTML selectors.

    Args:
        url: The URL to scrape
        tag: HTML tag to extract content from (default: "body")
        id: HTML id attribute to filter by
        class_name: HTML class attribute to filter by

    Returns:
        Extracted text content or empty string if failed
    """
    attr_dict = {}
    if id:
        attr_dict["id"] = id
    if class_name:
        attr_dict["class"] = class_name

    logger.info(f"Getting text from {url} with tag {tag} and attrs {attr_dict}")

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, verify=True, timeout=30, headers=headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")
        main_content = soup.find(tag, attrs=attr_dict)

        if main_content is None:
            logger.warning(f"No main content found for {url} with tag {tag} and attrs {attr_dict}")
            return ""

        text_content = main_content.get_text(strip=True, separator=' ')
        logger.info(f"Extracted {len(text_content)} characters from {url}")
        return text_content

    except requests.exceptions.RequestException as e:
        logger.error(f"Request error when scraping {url}: {str(e)}")
        return ""
    except Exception as e:
        logger.error(f"Unexpected error when scraping {url}: {str(e)}")
        return ""


def extract_text_from_html(
    html_bytes: bytes,
    tag: str = "body",
    id: Optional[str] = None,
    class_name: Optional[str] = None,
) -> str:
    """
    Extract text content from pre-fetched HTML bytes using specified selectors.

    Args:
        html_bytes: Raw HTML bytes
        tag: HTML tag to extract content from (default: "body")
        id: HTML id attribute to filter by
        class_name: HTML class attribute to filter by

    Returns:
        Extracted text content or empty string if not found
    """
    attr_dict = {}
    if id:
        attr_dict["id"] = id
    if class_name:
        attr_dict["class"] = class_name

    try:
        soup = BeautifulSoup(html_bytes, "html.parser")
        main_content = soup.find(tag, attrs=attr_dict)
        if main_content is None:
            return ""
        return main_content.get_text(strip=True, separator=' ')
    except Exception as e:
        logger.error(f"Error extracting text from HTML bytes: {e}")
        return ""


def scrape_and_index_url(
    domain,
    url_path: str,
    html_bytes: Optional[bytes] = None,
    status_callback: Optional[Callable[[str], None]] = None,
    db=None,
) -> bool:
    """
    Scrape a URL and index its content into the domain's silo.

    If html_bytes is provided, skip the HTTP fetch and use those bytes directly
    for BeautifulSoup parsing. This allows the crawl executor to pass pre-fetched
    content without a second HTTP round-trip.

    Args:
        domain: Domain object with scraping configuration
        url_path: URL path to scrape (combined with domain.base_url if html_bytes is None).
                  If html_bytes is provided, this is treated as the full URL for metadata.
        html_bytes: Optional pre-fetched HTML bytes. If provided, skips HTTP fetch.
        status_callback: Optional callable(str) — receives status strings ('indexing', 'indexed', 'failed').
        db: Database session (unused, kept for backward compatibility)

    Returns:
        True if successful, False otherwise
    """
    # Determine full URL for metadata / logging
    if html_bytes is not None:
        full_url = url_path  # caller passes absolute URL
    else:
        full_url = domain.base_url + url_path

    try:
        if html_bytes is not None:
            # Use pre-fetched HTML bytes
            content = extract_text_from_html(
                html_bytes=html_bytes,
                tag=domain.content_tag or "body",
                id=domain.content_id if domain.content_id else None,
                class_name=domain.content_class if domain.content_class else None,
            )
        else:
            content = get_text_from_url(
                url=full_url,
                tag=domain.content_tag or "body",
                id=domain.content_id if domain.content_id else None,
                class_name=domain.content_class if domain.content_class else None,
            )

        if not content:
            logger.warning(f"No content extracted from {full_url}")
            if status_callback:
                status_callback('failed')
            return False

        from services.silo_service import SiloService
        SiloService.index_single_content(
            domain.silo_id,
            content,
            {"url": full_url, "domain_id": domain.domain_id},
            db,
        )

        if status_callback:
            status_callback('indexed')

        logger.info(f"Successfully scraped and indexed {full_url}")
        return True

    except Exception as e:
        logger.error(f"Error scraping and indexing {full_url}: {str(e)}")
        if status_callback:
            status_callback('failed')
        return False
