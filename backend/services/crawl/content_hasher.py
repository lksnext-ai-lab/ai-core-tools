"""Content hashing utilities for change detection in the crawl pipeline."""
import hashlib
import re


def normalize_text_for_hash(text: str) -> str:
    """Collapse whitespace runs to single space and strip leading/trailing whitespace."""
    return re.sub(r'\s+', ' ', text).strip()


def compute_hash(text: str) -> str:
    """Return SHA-256 hex digest of the UTF-8 encoded text."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()
