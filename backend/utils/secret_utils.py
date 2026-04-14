"""Utilities for handling secrets and sensitive data."""

MASKED_KEY_PREFIX = "****"
PLACEHOLDER_API_KEY = "CHANGE_ME"


def mask_api_key(key: str | None) -> str:
    """Mask an API key for safe display, showing only the last 4 characters.

    Examples:
        mask_api_key("sk-abc123456789") -> "****6789"
        mask_api_key(None) -> ""
        mask_api_key("CHANGE_ME") -> ""
        mask_api_key("abc") -> "****"
    """
    if not key or key == PLACEHOLDER_API_KEY:
        return ""
    if len(key) <= 4:
        return MASKED_KEY_PREFIX
    return MASKED_KEY_PREFIX + key[-4:]


def is_masked_key(key: str | None) -> bool:
    """Check if a key value is a masked placeholder (not a real key)."""
    if not key:
        return False
    return key.startswith(MASKED_KEY_PREFIX)
