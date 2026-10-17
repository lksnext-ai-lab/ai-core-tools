"""Turn exceptions raised by LLM / embedding provider SDKs into a short, user-facing reason.

Indexing and media processing catch provider failures and keep going, so the reason has to
be stored where a user will see it (the resource, the media, the service). Each SDK raises
its own exception types; this module only looks at the HTTP status they carry, so it works
for OpenAI, Azure, Anthropic, Mistral (httpx), Google (api_core) and Bedrock (botocore)
without importing any of them.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

# botocore reports failures as error codes rather than HTTP statuses.
_BEDROCK_AUTH_CODES = {
    "UnrecognizedClientException",
    "AccessDeniedException",
    "InvalidSignatureException",
    "ExpiredTokenException",
    "UnauthorizedException",
}
_BEDROCK_RATE_LIMIT_CODES = {"ThrottlingException", "ServiceQuotaExceededException", "TooManyRequestsException"}

# The Gemini API answers an invalid key with 400 (not 401) and this reason.
_INVALID_KEY_MARKERS = ("API_KEY_INVALID", "API key not valid")


class ProviderErrorKind(str, Enum):
    AUTH = "auth"              # 401/403: key missing, wrong, revoked or without access
    RATE_LIMIT = "rate_limit"  # 429: rate limit or quota exhausted
    UNAVAILABLE = "unavailable"  # 5xx: provider-side failure
    OTHER = "other"


@dataclass(frozen=True)
class ProviderError:
    kind: ProviderErrorKind
    message: str

    @property
    def concerns_service(self) -> bool:
        """True when the fix is on the service configuration (key or quota), not on the input."""
        return self.kind in (ProviderErrorKind.AUTH, ProviderErrorKind.RATE_LIMIT)


def _status_of(exc: BaseException) -> Optional[int]:
    """HTTP status carried by a provider exception, if any."""
    # Vector store clients (Qdrant) also carry HTTP statuses; those are not provider errors.
    if type(exc).__module__.startswith("qdrant_client"):
        return None
    for candidate in (
        getattr(exc, "status_code", None),
        getattr(getattr(exc, "response", None), "status_code", None),
        getattr(exc, "code", None),  # google.api_core
    ):
        try:
            if candidate is not None and 100 <= int(candidate) <= 599:
                return int(candidate)
        except (TypeError, ValueError):
            continue
    return None


def _bedrock_code(exc: BaseException) -> Optional[str]:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        return (response.get("Error") or {}).get("Code")
    return None


def _kind_of(exc: BaseException) -> ProviderErrorKind:
    # Walk the cause chain: LangChain and our own code often wrap the SDK exception.
    seen = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        status = _status_of(current)
        if status in (401, 403) or (status == 400 and any(m in str(current) for m in _INVALID_KEY_MARKERS)):
            return ProviderErrorKind.AUTH
        if status == 429:
            return ProviderErrorKind.RATE_LIMIT
        if status is not None and status >= 500:
            return ProviderErrorKind.UNAVAILABLE
        code = _bedrock_code(current)
        if code in _BEDROCK_AUTH_CODES:
            return ProviderErrorKind.AUTH
        if code in _BEDROCK_RATE_LIMIT_CODES:
            return ProviderErrorKind.RATE_LIMIT
        current = current.__cause__ or current.__context__
    return ProviderErrorKind.OTHER


def classify_provider_error(exc: BaseException, service_label: str, step: Optional[str] = None) -> ProviderError:
    """Classify ``exc`` and build the message to show for it.

    ``service_label`` names the service that was called, e.g. "Embedding service 'small'".
    ``step`` names what was being done ("Indexing"); it prefixes errors that may not come
    from the provider at all, so they are not blamed on the service.

    Messages never echo the exception text: it can carry part of a key, endpoint URLs with
    tokens, SQL or internal hosts, and these messages reach app users and the public API.
    Callers log the full exception server-side.
    """
    kind = _kind_of(exc)
    if kind is ProviderErrorKind.AUTH:
        message = f"{service_label} rejected its credentials (API key missing, wrong or revoked)."
    elif kind is ProviderErrorKind.RATE_LIMIT:
        message = f"{service_label} hit its rate limit or ran out of quota. Try again later or check the provider account."
    elif kind is ProviderErrorKind.UNAVAILABLE:
        message = f"{service_label} is unavailable right now (provider error). Try again later."
    else:
        message = f"{step or service_label} failed ({type(exc).__name__}). The details are in the server logs."
    return ProviderError(kind=kind, message=message)
