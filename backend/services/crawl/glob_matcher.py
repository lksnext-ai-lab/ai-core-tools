"""Glob-based URL filtering for the crawl pipeline."""
import fnmatch
import re
from typing import List
from urllib.parse import urlparse


def matches_glob(pattern: str, path_and_query: str) -> bool:
    """
    Returns True if path_and_query matches pattern using fnmatch with ** support.
    '**' matches any sequence of characters including '/'.
    '*' does NOT match '/'.
    """
    # Ensure path starts with /
    subject = path_and_query if path_and_query.startswith('/') else '/' + path_and_query

    # Replace ** with a placeholder, then escape the pattern for fnmatch,
    # then restore the ** as a wildcard that matches '/' too.
    # Strategy: use re.fullmatch after converting glob to regex manually.
    regex = _glob_to_regex(pattern)
    return bool(re.fullmatch(regex, subject))


def _glob_to_regex(pattern: str) -> str:
    """Convert a glob pattern (with ** support) to a regex string."""
    # Ensure pattern starts with /
    if not pattern.startswith('/'):
        pattern = '/' + pattern

    result = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == '*':
            if i + 1 < len(pattern) and pattern[i + 1] == '*':
                # ** — match everything including /
                result.append('.*')
                i += 2
                # Consume trailing slash after ** if present
                if i < len(pattern) and pattern[i] == '/':
                    result.append('/?')
                    i += 1
            else:
                # Single * — match anything except /
                result.append('[^/]*')
                i += 1
        elif ch in '.+^${}[]|()\\':
            result.append('\\' + ch)
            i += 1
        elif ch == '?':
            result.append('[^/]')
            i += 1
        else:
            result.append(re.escape(ch))
            i += 1
    return ''.join(result)


def should_include(url: str, include_globs: List[str], exclude_globs: List[str]) -> bool:
    """
    Decide whether a URL should be included:
    1. If include_globs is non-empty and no pattern matches → False.
    2. If any exclude_glob matches → False.
    3. Otherwise → True.
    """
    parsed = urlparse(url)
    path_and_query = parsed.path + ('?' + parsed.query if parsed.query else '')

    if include_globs:
        if not any(matches_glob(p, path_and_query) for p in include_globs):
            return False

    if exclude_globs:
        if any(matches_glob(p, path_and_query) for p in exclude_globs):
            return False

    return True


def validate_globs(globs: List[str]) -> List[str]:
    """
    Returns list of invalid glob patterns.
    A pattern is invalid if converting it to a regex raises an exception.
    """
    invalid = []
    for pattern in globs:
        try:
            regex = _glob_to_regex(pattern)
            re.compile(regex)
        except Exception:
            invalid.append(pattern)
    return invalid
