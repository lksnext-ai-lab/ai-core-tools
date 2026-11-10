from urllib.parse import quote, urlparse, urlunparse


def normalize_azure_openai_endpoint(endpoint: str | None, model: str | None) -> str | None:
    """Expand a bare Azure OpenAI resource endpoint to its deployment route."""
    url = (endpoint or "").strip().rstrip("/")
    if not url:
        return endpoint

    parsed = urlparse(url)
    if not parsed.hostname or not parsed.hostname.lower().endswith(".openai.azure.com"):
        return url
    if "/openai" in parsed.path:
        return url

    deployment = quote(model or "", safe="")
    if not deployment:
        return url

    path = f"{parsed.path.rstrip('/')}/openai/deployments/{deployment}"
    return urlunparse(parsed._replace(path=path))
