"""SDK adapters that list models for each provider.

Each ``list_*_models`` function instantiates a fresh SDK client (no DB,
no shared state), calls the provider's listing endpoint, and normalises
the response into ``ProviderModelInfo`` instances using
``model_catalog.enrich``. Errors are wrapped in ``ProviderListingError``
with a sanitised message — original exceptions often include the API
key or full URLs and must never reach the client.
"""

from __future__ import annotations

import datetime as _dt
from typing import List, Optional

import httpx
from openai import OpenAI

from schemas.provider_models_schemas import (
    ListProviderModelsRequest,
    ProviderCapabilities,
    ProviderModelInfo,
)
from tools.ai.model_catalog import (
    PROVIDER_ANTHROPIC,
    PROVIDER_GOOGLE,
    PROVIDER_MISTRAL,
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI,
    enrich,
)
from tools.aiServiceTools import build_ollama_auth_headers
from utils.logger import get_logger

logger = get_logger(__name__)


_DEFAULT_TIMEOUT_SECONDS = 15.0
_DEFAULT_OLLAMA_HOST = "http://localhost:11434"


def _datetime_to_unix(value) -> Optional[int]:
    """Convert a datetime / date / unix-timestamp to int unix seconds.

    Anthropic and Ollama return :class:`datetime.datetime` objects. OpenAI
    and Mistral return integers already. Anything else (None, malformed)
    becomes ``None`` so the sort keeps the model at the bottom.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, _dt.datetime):
        return int(value.timestamp())
    if isinstance(value, _dt.date):
        return int(_dt.datetime(value.year, value.month, value.day).timestamp())
    return None


# ==================== ERROR TYPES ====================


class ProviderListingError(Exception):
    """Raised by adapters when listing models fails.

    ``code`` is a short machine-readable identifier the router maps to an
    HTTP status. ``message`` is the user-facing message — must never
    contain the API key or other secrets.
    """

    VALID_CODES = (
        "unauthorized",
        "not_found",
        "timeout",
        "network",
        "unsupported",
        "invalid_request",
    )

    def __init__(self, code: str, message: str):
        if code not in self.VALID_CODES:
            raise ValueError(f"Invalid ProviderListingError code: {code!r}")
        self.code = code
        self.message = message
        super().__init__(message)


# ==================== HELPERS ====================


def _sanitize(message: str, *secrets: str) -> str:
    """Strip credentials from an exception message before propagating it."""
    cleaned = message or ""
    for secret in secrets:
        if secret and len(secret) >= 4 and secret in cleaned:
            cleaned = cleaned.replace(secret, "****")
    return cleaned


def _classify_by_status(status_code: int | None) -> str:
    if status_code in (401, 403):
        return "unauthorized"
    if status_code == 404:
        return "not_found"
    if status_code == 408:
        return "timeout"
    if status_code and 500 <= status_code < 600:
        return "network"
    return "network"


def _classify_httpx(exc: BaseException) -> str | None:
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.ConnectError):
        return "network"
    if isinstance(exc, httpx.HTTPError):
        return "network"
    return None


# ==================== OPENAI / CUSTOM ====================


def _classify_openai_error(exc: Exception) -> str:
    name = type(exc).__name__
    if name in ("AuthenticationError", "PermissionDeniedError"):
        return "unauthorized"
    if name == "NotFoundError":
        return "not_found"
    if name in ("APITimeoutError", "TimeoutError"):
        return "timeout"
    return "network"


def _list_openai_compatible(
    req: ListProviderModelsRequest,
    *,
    provider: str,
) -> List[ProviderModelInfo]:
    """Shared implementation for OpenAI and OpenAI-compatible Custom endpoints."""
    client_kwargs = {
        "api_key": req.api_key or "not-needed",  # vLLM and similar accept any string
        "timeout": _DEFAULT_TIMEOUT_SECONDS,
    }
    if req.base_url:
        client_kwargs["base_url"] = req.base_url

    try:
        client = OpenAI(**client_kwargs)
        listing = client.models.list()
    except Exception as exc:  # noqa: BLE001 — must wrap any SDK error
        code = _classify_openai_error(exc)
        sanitized = _sanitize(str(exc), req.api_key, req.base_url or "")
        logger.warning(
            "OpenAI-compatible list failed (provider=%s, code=%s): %s",
            provider,
            code,
            sanitized,
        )
        raise ProviderListingError(code, sanitized or "Provider listing failed")

    models: List[ProviderModelInfo] = []
    for raw in getattr(listing, "data", []) or []:
        model_id = getattr(raw, "id", None)
        if not model_id:
            continue
        owned_by = getattr(raw, "owned_by", None)
        created = getattr(raw, "created", None)
        base = ProviderModelInfo(
            id=model_id,
            display_name=model_id,
            owned_by=owned_by,
            created_at=int(created) if isinstance(created, (int, float)) else None,
            source="api",
        )
        models.append(enrich(provider, model_id, base=base))
    return models


def list_openai_models(req: ListProviderModelsRequest) -> List[ProviderModelInfo]:
    if not req.api_key:
        raise ProviderListingError(
            "invalid_request",
            "API key is required to list OpenAI models.",
        )
    return _list_openai_compatible(req, provider=PROVIDER_OPENAI)


# ==================== ANTHROPIC ====================


def list_anthropic_models(req: ListProviderModelsRequest) -> List[ProviderModelInfo]:
    if not req.api_key:
        raise ProviderListingError(
            "invalid_request",
            "API key is required to list Anthropic models.",
        )

    from anthropic import Anthropic

    try:
        client = Anthropic(api_key=req.api_key, timeout=_DEFAULT_TIMEOUT_SECONDS)
        listing = client.models.list()
    except Exception as exc:  # noqa: BLE001
        name = type(exc).__name__
        if name in ("AuthenticationError", "PermissionDeniedError"):
            code = "unauthorized"
        elif name == "NotFoundError":
            code = "not_found"
        elif name == "APITimeoutError":
            code = "timeout"
        else:
            code = "network"
        sanitized = _sanitize(str(exc), req.api_key)
        logger.warning("Anthropic list failed (code=%s): %s", code, sanitized)
        raise ProviderListingError(code, sanitized or "Anthropic listing failed")

    models: List[ProviderModelInfo] = []
    for raw in getattr(listing, "data", []) or []:
        model_id = getattr(raw, "id", None)
        if not model_id:
            continue
        display_name = getattr(raw, "display_name", None) or model_id
        created_at = _datetime_to_unix(getattr(raw, "created_at", None))
        # Anthropic only ships chat models — but we leave capabilities
        # empty so the heuristic can flag vision/reasoning per family.
        base = ProviderModelInfo(
            id=model_id,
            display_name=display_name,
            created_at=created_at,
            source="api",
        )
        models.append(enrich(PROVIDER_ANTHROPIC, model_id, base=base))
    return models


# ==================== MISTRAL AI ====================


def list_mistral_models(req: ListProviderModelsRequest) -> List[ProviderModelInfo]:
    if not req.api_key:
        raise ProviderListingError(
            "invalid_request",
            "API key is required to list MistralAI models.",
        )

    from mistralai import Mistral

    try:
        client = Mistral(api_key=req.api_key, timeout_ms=int(_DEFAULT_TIMEOUT_SECONDS * 1000))
        listing = client.models.list()
    except Exception as exc:  # noqa: BLE001
        # mistralai surfaces a single SDKError plus raw httpx exceptions.
        status_code = getattr(exc, "status_code", None)
        if status_code is not None:
            code = _classify_by_status(status_code)
        else:
            code = _classify_httpx(exc) or "network"
        sanitized = _sanitize(str(exc), req.api_key)
        logger.warning("MistralAI list failed (code=%s): %s", code, sanitized)
        raise ProviderListingError(code, sanitized or "MistralAI listing failed")

    models: List[ProviderModelInfo] = []
    for raw in getattr(listing, "data", []) or []:
        model_id = getattr(raw, "id", None)
        if not model_id:
            continue
        display_name = (
            getattr(raw, "name", None)
            or getattr(raw, "display_name", None)
            or model_id
        )
        owned_by = getattr(raw, "owned_by", None)
        context_window = getattr(raw, "max_context_length", None)
        deprecation = getattr(raw, "deprecation", None)
        created_at = _datetime_to_unix(getattr(raw, "created", None))

        caps = ProviderCapabilities()
        raw_caps = getattr(raw, "capabilities", None)
        if raw_caps is not None:
            caps.chat = bool(getattr(raw_caps, "completion_chat", False))
            caps.function_calling = bool(getattr(raw_caps, "function_calling", False))
            caps.vision = bool(getattr(raw_caps, "vision", False))
            if caps.function_calling:
                caps.tool_use = True
            # MistralAI does not expose an embedding flag — embedding models
            # show up with completion_chat=False. The heuristic detects
            # them by id (e.g. "mistral-embed").

        base = ProviderModelInfo(
            id=model_id,
            display_name=display_name,
            owned_by=owned_by,
            context_window=context_window,
            deprecated=bool(deprecation),
            created_at=created_at,
            capabilities=caps,
            source="api",
        )
        models.append(enrich(PROVIDER_MISTRAL, model_id, base=base))
    return models


# ==================== GOOGLE GENAI (AI STUDIO) ====================


def _google_caps_from_actions(actions) -> ProviderCapabilities:
    """Translate the Google supported_actions list into our capability flags."""
    caps = ProviderCapabilities()
    if not actions:
        return caps
    flat = {str(a) for a in actions}
    if any("embedContent" in a for a in flat):
        caps.embedding = True
    if any("generateContent" in a for a in flat) or any("countTokens" in a for a in flat):
        caps.chat = True
    return caps


def list_google_models(req: ListProviderModelsRequest) -> List[ProviderModelInfo]:
    if not req.api_key:
        raise ProviderListingError(
            "invalid_request",
            "API key is required to list Google AI Studio models.",
        )

    from google import genai

    client_options = {"api_key": req.api_key}
    if req.base_url:
        client_options["http_options"] = {"base_url": req.base_url}

    try:
        client = genai.Client(**client_options)
        pager = client.models.list(config={"query_base": True, "page_size": 100})
    except Exception as exc:  # noqa: BLE001
        code = _classify_google_error(exc)
        sanitized = _sanitize(str(exc), req.api_key)
        logger.warning("Google list failed (code=%s): %s", code, sanitized)
        raise ProviderListingError(code, sanitized or "Google listing failed")

    models: List[ProviderModelInfo] = []
    try:
        for raw in pager:
            raw_name = getattr(raw, "name", None) or ""
            short_id = raw_name.rsplit("/", 1)[-1] if raw_name else ""
            if not short_id:
                continue
            display_name = getattr(raw, "display_name", None) or short_id
            input_limit = getattr(raw, "input_token_limit", None)
            actions = getattr(raw, "supported_actions", None)

            caps = _google_caps_from_actions(actions)
            # Embedding models on Google never support generation.
            if caps.embedding:
                caps.chat = False

            # google-genai exposes neither created_at nor an obvious
            # version timestamp, so leave it None and rely on family
            # ordering done downstream.
            base = ProviderModelInfo(
                id=short_id,
                display_name=display_name,
                context_window=input_limit,
                capabilities=caps,
                source="api",
            )
            models.append(enrich(PROVIDER_GOOGLE, short_id, base=base))
    except Exception as exc:  # noqa: BLE001 — pager iteration may fault late
        code = _classify_google_error(exc)
        sanitized = _sanitize(str(exc), req.api_key)
        logger.warning("Google iteration failed (code=%s): %s", code, sanitized)
        raise ProviderListingError(code, sanitized or "Google listing failed")
    return models


def _classify_google_error(exc: BaseException) -> str:
    code_attr = getattr(exc, "code", None)
    if isinstance(code_attr, int):
        return _classify_by_status(code_attr)
    name = type(exc).__name__
    if name == "ClientError":
        return _classify_by_status(getattr(exc, "code", None))
    if name == "ServerError":
        return "network"
    return _classify_httpx(exc) or "network"


# ==================== OLLAMA ====================


_OLLAMA_EMBEDDING_FAMILIES = {"nomic-bert", "bert", "mxbai", "minilm"}
_OLLAMA_VISION_FAMILIES = {"llava", "moondream", "bakllava"}


def _ollama_caps_from_details(family: str | None, families: list[str] | None) -> ProviderCapabilities:
    caps = ProviderCapabilities()
    fam_set = {(f or "").lower() for f in (families or [])}
    if family:
        fam_set.add(family.lower())

    if fam_set & _OLLAMA_EMBEDDING_FAMILIES:
        caps.embedding = True
        return caps
    if fam_set & _OLLAMA_VISION_FAMILIES:
        caps.chat = True
        caps.vision = True
        return caps

    caps.chat = True
    return caps


def list_ollama_models(req: ListProviderModelsRequest) -> List[ProviderModelInfo]:
    """List models from an Ollama-protocol endpoint.

    Auth headers are built by :func:`tools.aiServiceTools.build_ollama_auth_headers`
    so the listing path uses exactly the same logic as the runtime LLM
    builder — Bearer token from the API key, optional Basic auth from
    user:password embedded in the URL.
    """
    from ollama import Client

    host = (req.base_url or "").strip() or _DEFAULT_OLLAMA_HOST
    headers = build_ollama_auth_headers(req.api_key, host)

    try:
        client = Client(host=host, timeout=_DEFAULT_TIMEOUT_SECONDS, headers=headers)
        listing = client.list()
    except Exception as exc:  # noqa: BLE001
        name = type(exc).__name__
        if name == "ResponseError":
            code = _classify_by_status(getattr(exc, "status_code", None))
        elif name == "RequestError":
            code = "invalid_request"
        elif isinstance(exc, ConnectionError):
            code = "network"
        else:
            code = _classify_httpx(exc) or "network"
        sanitized = _sanitize(str(exc), host)
        logger.warning("Ollama list failed (code=%s): %s", code, sanitized)
        raise ProviderListingError(code, sanitized or "Ollama listing failed")

    raw_models = getattr(listing, "models", None) or []
    models: List[ProviderModelInfo] = []
    for raw in raw_models:
        model_id = getattr(raw, "model", None)
        if not model_id:
            continue
        details = getattr(raw, "details", None)
        family = getattr(details, "family", None) if details else None
        families = getattr(details, "families", None) if details else None
        modified_at = _datetime_to_unix(getattr(raw, "modified_at", None))

        caps = _ollama_caps_from_details(family, families)
        base = ProviderModelInfo(
            id=model_id,
            display_name=model_id,
            family=family,
            capabilities=caps,
            created_at=modified_at,
            source="api",
        )
        models.append(enrich(PROVIDER_OLLAMA, model_id, base=base))
    return models
