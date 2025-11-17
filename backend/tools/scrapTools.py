from collections import Counter
import requests
from bs4 import BeautifulSoup
from typing import Optional
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
    # Count the frequency of items in the array
    counts = Counter(arr)
    
    # Remove repetitions and sort the array by frequency
    sorted_arr = sorted(counts, key=lambda x: counts[x], reverse=True)
    return sorted_arr


def get_text_from_url(url: str, tag: str = "body", id: Optional[str] = None, class_name: Optional[str] = None) -> str:
    """
    Extract text content from a web page using specified HTML selectors
    
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
        # Make request with timeout and user agent
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, verify=True, timeout=30, headers=headers)
        response.raise_for_status()  # Raise an exception for bad status codes
        
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


def scrape_and_index_url(domain, url_path: str, url_id: int = None, db = None) -> bool:
    """
    Scrape a URL and index its content into the domain's silo
    
    Args:
        domain: Domain object with scraping configuration
        url_path: URL path to scrape (will be combined with domain.base_url)
        url_id: Optional URL ID to update status
        db: Database session (required if url_id is provided)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Update status to indexing if URL ID provided
        if url_id and db:
            from services.url_service import UrlService
            UrlService.update_url_indexing(url_id, db, domain.domain_id)
        
        # Construct full URL
        full_url = domain.base_url + url_path
        
        # Extract content using domain's scraping configuration
        content = get_text_from_url(
            url=full_url,
            tag=domain.content_tag or "body",
            id=domain.content_id if domain.content_id else None,
            class_name=domain.content_class if domain.content_class else None
        )
        
        if not content:
            logger.warning(f"No content extracted from {full_url}")
            if url_id and db:
                UrlService.update_url_rejected(url_id, db, domain.domain_id)
            return False
        
        # Index content into domain's silo
        from services.silo_service import SiloService
        SiloService.index_single_content(
            domain.silo_id, 
            content, 
            {"url": full_url, "domain_id": domain.domain_id},
            db
        )
        
        # Update status to indexed if successful
        if url_id and db:
            UrlService.update_url_indexed(url_id, db, domain.domain_id)
        
        logger.info(f"Successfully scraped and indexed {full_url}")
        return True
        
    except Exception as e:
        logger.error(f"Error scraping and indexing {full_url}: {str(e)}")
        if url_id and db:
            UrlService.update_url_rejected(url_id, db, domain.domain_id)
        return False


def reindex_domain_urls(domain, db = None) -> dict:
    """
    Re-index all URLs for a domain (skips rejected URLs)
    
    Args:
        domain: Domain object with URLs
        db: Database session (required for URL status updates)
        
    Returns:
        Dictionary with success/failure counts
    """
    results = {"success": 0, "failed": 0, "total": 0, "skipped": 0}
    
    try:
        from services.silo_service import SiloService
        
        for url in domain.urls:
            # Skip rejected URLs - they should never be auto-indexed
            if url.status == 'rejected':
                results["skipped"] += 1
                logger.info(f"Skipping rejected URL: {domain.base_url + url.url}")
                continue
            
            results["total"] += 1
            full_url = domain.base_url + url.url
            
            try:
                # Remove old content
                SiloService.delete_url(domain.silo_id, full_url, db)
                
                # Re-scrape and index with URL ID for status updates
                if scrape_and_index_url(domain, url.url, url.url_id, db):
                    results["success"] += 1
                else:
                    results["failed"] += 1
                    
            except Exception as e:
                logger.error(f"Error re-indexing URL {full_url}: {str(e)}")
                results["failed"] += 1
        
        logger.info(f"Re-indexing complete for domain {domain.name}: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Error during domain re-indexing: {str(e)}")
        results["failed"] = results["total"]
        return results
