"""Orchestrator for the provider model listing flow.

The service validates incoming requests, dispatches to the appropriate
SDK adapter in :mod:`tools.ai.provider_model_clients`, removes obvious
junk and dated snapshots, applies the requested ``purpose`` filter
(chat vs embedding), and returns a ``ListProviderModelsResponse`` sorted
newest-first.

Routers should map :class:`tools.ai.provider_model_clients.ProviderListingError`
to HTTP status codes via :data:`PROVIDER_ERROR_STATUS`.
"""

from __future__ import annotations

import re
from typing import Dict, List

from schemas.provider_models_schemas import (
    ListProviderModelsRequest,
    ListProviderModelsResponse,
    ProviderModelInfo,
)
from tools.ai import provider_model_clients
from tools.ai.model_catalog import (
    MANUAL_INPUT_PROVIDERS,
    PROVIDER_ANTHROPIC,
    PROVIDER_CUSTOM,
    PROVIDER_GOOGLE,
    PROVIDER_MISTRAL,
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI,
    drop_dated_snapshots_when_alias_exists,
    is_chat_model,
    is_embedding_model,
    is_junk_model,
)
from tools.ai.provider_model_clients import ProviderListingError
from utils.secret_utils import PLACEHOLDER_API_KEY, is_masked_key


# ==================== DISPATCH TABLE ====================
# Names are resolved against `provider_model_clients` at call time so
# tests can monkeypatch the adapter without re-importing the orchestrator.

_DISPATCH: Dict[str, str] = {
    PROVIDER_OPENAI: "list_openai_models",
    PROVIDER_ANTHROPIC: "list_anthropic_models",
    PROVIDER_MISTRAL: "list_mistral_models",
    PROVIDER_GOOGLE: "list_google_models",
    PROVIDER_OLLAMA: "list_ollama_models",
    # Custom is handled in-line: the AI Service runtime is ChatOllama, so
    # listing reuses the Ollama tags endpoint. Embeddings under Custom
    # use HuggingFace Inference which has no generic listing — those go
    # through the manual_input branch in :meth:`list_models`.
    PROVIDER_CUSTOM: "list_ollama_models",
}


PROVIDER_ERROR_STATUS: Dict[str, int] = {
    "invalid_request": 400,
    "unauthorized": 401,
    "not_found": 404,
    "timeout": 408,
    "network": 502,
    "unsupported": 501,
}


_VERSION_IN_ID_RE = re.compile(r"-(\d+(?:\.\d+)?)")


class ProviderModelsService:
    """Stateless orchestrator — all methods are static."""

    @staticmethod
    def list_models(req: ListProviderModelsRequest) -> ListProviderModelsResponse:
        """Validate, dispatch and post-process the listing for ``purpose``."""
        provider = (req.provider or "").strip()
        if not provider:
            raise ProviderListingError(
                "invalid_request", "Provider is required."
            )

        # Manual-input providers (Azure, GoogleCloud) skip the listing
        # entirely. Same for Custom embeddings (HuggingFace Inference).
        if provider in MANUAL_INPUT_PROVIDERS or (
            provider == PROVIDER_CUSTOM and req.purpose == "embedding"
        ):
            return ListProviderModelsResponse(
                provider=provider,
                models=[],
                requires_manual_input=True,
            )

        ProviderModelsService._validate_credentials(req)

        lister_name = _DISPATCH.get(provider)
        if lister_name is None:
            raise ProviderListingError(
                "unsupported", f"Provider '{provider}' is not supported."
            )

        lister = getattr(provider_model_clients, lister_name)
        models: List[ProviderModelInfo] = lister(req)

        # 1) Drop noise the API returned (dall-e, davinci, fine-tunes, ...).
        models = [m for m in models if not is_junk_model(m.id)]

        # 2) Hide dated snapshots whose canonical alias is in the listing.
        models = drop_dated_snapshots_when_alias_exists(models)

        # 3) Filter by purpose.
        models = ProviderModelsService._apply_purpose_filter(models, req.purpose)

        # 4) Sort: non-deprecated first, then newest first, alphabetical last.
        models = ProviderModelsService._sort(models)

        return ListProviderModelsResponse(
            provider=provider,
            models=models,
            requires_manual_input=False,
        )

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _validate_credentials(req: ListProviderModelsRequest) -> None:
        """Reject requests that cannot possibly succeed.

        Ollama (and Custom, which is Ollama under the hood) may run
        without an API key when the server has auth disabled, so the
        check is skipped for those providers.
        """
        if req.provider in (PROVIDER_OLLAMA, PROVIDER_CUSTOM):
            return

        api_key = req.api_key or ""
        if not api_key or api_key == PLACEHOLDER_API_KEY:
            raise ProviderListingError(
                "invalid_request",
                "API key is required to list models.",
            )
        if is_masked_key(api_key):
            raise ProviderListingError(
                "invalid_request",
                "Re-enter the API key — the masked value cannot be used to list models.",
            )

    @staticmethod
    def _apply_purpose_filter(
        models: List[ProviderModelInfo],
        purpose: str,
    ) -> List[ProviderModelInfo]:
        if purpose == "embedding":
            return [m for m in models if is_embedding_model(m)]
        return [m for m in models if is_chat_model(m)]

    @staticmethod
    def _recency_key(model: ProviderModelInfo) -> tuple:
        """Sort key that puts the newest models first.

        Preference order:

        1. Models with an explicit ``created_at`` from the SDK.
        2. Models with a numeric version embedded in the id
           (``gemini-2.5-pro`` → 2.5) — used for providers like Google
           that don't return timestamps.
        3. Everything else, sorted alphabetically.
        """
        if model.created_at is not None:
            return (0, -model.created_at)
        match = _VERSION_IN_ID_RE.search(model.id)
        if match:
            try:
                return (1, -float(match.group(1)))
            except ValueError:
                pass
        return (2, 0.0)

    @staticmethod
    def _sort(models: List[ProviderModelInfo]) -> List[ProviderModelInfo]:
        return sorted(
            models,
            key=lambda m: (
                m.deprecated,
                *ProviderModelsService._recency_key(m),
                m.id.lower(),
            ),
        )
