import os
from typing import Any


def normalize_langsmith_api_key(api_key: str | None) -> str:
    """Trim surrounding whitespace from a LangSmith API key."""
    return (api_key or "").strip()


def get_langsmith_client_kwargs(api_key: str | None) -> dict[str, Any]:
    """Build LangSmith client kwargs from the provided key and deployment config."""
    kwargs: dict[str, Any] = {
        "api_key": normalize_langsmith_api_key(api_key),
        "api_url": os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"),
    }

    workspace_id = os.getenv("LANGSMITH_WORKSPACE_ID", "").strip()
    if workspace_id:
        kwargs["workspace_id"] = workspace_id

    return kwargs


def get_langsmith_debug_metadata(api_key: str | None) -> dict[str, Any]:
    """Return non-sensitive diagnostics for LangSmith client setup."""
    normalized_key = normalize_langsmith_api_key(api_key)
    workspace_id = os.getenv("LANGSMITH_WORKSPACE_ID", "").strip()
    return {
        "key_present": bool(normalized_key),
        "key_length": len(normalized_key),
        "key_suffix": normalized_key[-4:] if normalized_key else "",
        "endpoint": os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"),
        "workspace_id_present": bool(workspace_id),
    }
