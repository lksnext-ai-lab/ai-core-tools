"""Utilities for handling secrets and sensitive data."""

from typing import Mapping, Any

MASKED_KEY_PREFIX = "****"
PLACEHOLDER_API_KEY = "CHANGE_ME"


def normalize_credential(value: Any) -> Any:
    """Strip leading/trailing whitespace from credential strings.

    Trailing newlines or spaces sneak in when users paste keys from emails,
    .env files, or password managers. They break HTTP header construction in
    httpx and surface as misleading 'Connection error' messages from SDKs.
    Non-string values are returned unchanged.
    """
    return value.strip() if isinstance(value, str) else value


def normalize_credential_map(data: Mapping[str, Any] | None) -> dict | None:
    """Apply :func:`normalize_credential` to every value of a mapping.

    Used at boundaries that receive credentials in dict form (e.g. the
    `api_keys_json` payload of the app import stepper) and bypass the
    schema-level validators.
    """
    if not isinstance(data, Mapping):
        return data
    return {k: normalize_credential(v) for k, v in data.items()}


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
