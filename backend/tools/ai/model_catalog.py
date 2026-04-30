"""Pattern-based model classification.

We intentionally do NOT keep a hand-curated catalog of every model id —
provider model lists evolve too fast and a hardcoded list quickly drifts
from reality. Instead this module exposes:

* ``heuristic_capabilities_from_id`` — regex pattern rules that infer
  ``ProviderCapabilities`` from a model id (vision, reasoning, audio…).
* ``is_junk_model`` — drops obvious noise (dall-e, davinci, moderation,
  realtime-only protocols, etc.) so the wizard never shows them.
* ``drop_dated_snapshots_when_alias_exists`` — collapses dated variants
  (``gpt-4o-2024-08-06``) when the canonical alias (``gpt-4o``) is also
  present in the same listing.
* ``enrich`` — merges the SDK response with heuristic data.
* ``is_chat_model`` / ``is_embedding_model`` — final filters used by the
  service to split the result by purpose.

When a provider exposes capability metadata natively (MistralAI's
``capabilities``, Google's ``supported_actions``), the SDK adapter passes
it via the ``base`` argument and the heuristic is only used for fields
the API didn't fill.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

from schemas.provider_models_schemas import (
    ProviderCapabilities,
    ProviderModelInfo,
)


# ==================== PROVIDER CONSTANTS ====================
# Mirror of models.ai_service.ProviderEnum / models.embedding_service.EmbeddingProvider
# Defined as plain strings so this module never imports the SQLAlchemy
# models — keeps the listing pipeline cheap and importable from anywhere.

PROVIDER_OPENAI = "OpenAI"
PROVIDER_ANTHROPIC = "Anthropic"
PROVIDER_MISTRAL = "MistralAI"
PROVIDER_GOOGLE = "Google"
PROVIDER_OLLAMA = "Ollama"
PROVIDER_CUSTOM = "Custom"
PROVIDER_AZURE = "Azure"
PROVIDER_GOOGLE_CLOUD = "GoogleCloud"

MANUAL_INPUT_PROVIDERS = frozenset({PROVIDER_AZURE, PROVIDER_GOOGLE_CLOUD})


# ==================== JUNK FILTERS ====================
# Patterns we always drop from the listing. These are non-chat models
# (image generation, moderation, transcription-only fine-tunes), legacy
# completion engines, or specialised protocols (WebRTC realtime).

_JUNK_ID_PATTERNS = (
    re.compile(r"^dall-e-"),
    re.compile(r"^gpt-image"),
    re.compile(r"^omni-moderation"),
    re.compile(r"^text-moderation"),
    re.compile(r"^(text-)?(babbage|davinci|curie|ada)(?:[-_].+)?$"),
    re.compile(r"-realtime-preview"),  # WebRTC, not standard chat
    re.compile(r"^chatgpt-"),  # consumer ChatGPT, not API
    re.compile(r"^ft:"),  # fine-tunes, account-specific noise
    re.compile(r"^stable-diffusion"),
)

_DATED_SNAPSHOT_RE = re.compile(r"-\d{4}-\d{2}-\d{2}(?:-preview)?$")


def is_junk_model(model_id: str) -> bool:
    """True for ids that should never reach the wizard."""
    if not model_id:
        return True
    lid = model_id.lower()
    return any(p.search(lid) for p in _JUNK_ID_PATTERNS)


def drop_dated_snapshots_when_alias_exists(
    models: list[ProviderModelInfo],
) -> list[ProviderModelInfo]:
    """Hide ``gpt-4o-2024-08-06`` if ``gpt-4o`` is in the same listing.

    Providers like OpenAI return the canonical alias plus several dated
    pinned snapshots; users almost always want the alias.
    """
    canonical = {m.id for m in models if not _DATED_SNAPSHOT_RE.search(m.id)}
    out: list[ProviderModelInfo] = []
    for m in models:
        if _DATED_SNAPSHOT_RE.search(m.id):
            stripped = _DATED_SNAPSHOT_RE.sub("", m.id)
            if stripped in canonical:
                continue
        out.append(m)
    return out


# ==================== HEURISTIC PATTERNS ====================

_EMBEDDING_PATTERNS = (
    re.compile(r"^text-embedding"),
    re.compile(r"^embed"),
    re.compile(r"-embed(?:ding)?(?:-|$)"),
    re.compile(r"-bge-"),
    re.compile(r"^bge-"),
    re.compile(r"^nomic-embed"),
    re.compile(r"^mxbai-embed"),
    re.compile(r"^e5-"),
    re.compile(r"^all-minilm"),
)

# Pure-audio (transcription / TTS only). They get audio=True without chat.
_PURE_AUDIO_PATTERNS = (
    re.compile(r"^whisper"),
    re.compile(r"^tts-"),
    re.compile(r"^gpt-4o.*-transcribe"),
    re.compile(r"^speech-"),
)

# Audio chat hybrids — chat models that also accept/emit audio.
_AUDIO_CHAT_PATTERNS = (
    re.compile(r"-audio-preview"),
    re.compile(r"-realtime"),  # post-junk-filter survivors
)

_REASONING_PATTERNS = (
    re.compile(r"^o[1-9](?:-|$)"),
    re.compile(r"^o\d{2,}(?:-|$)"),  # o10, o20, future-proof
    re.compile(r"-thinking"),
    re.compile(r"-reasoning"),
    re.compile(r"-deep-research"),
)

# Modern multimodal flagship families. These accept image input.
_VISION_PATTERNS = (
    re.compile(r"^gpt-[5-9]"),
    re.compile(r"^gpt-4o"),
    re.compile(r"^gpt-4\.1"),
    re.compile(r"^gpt-4-turbo"),
    re.compile(r"^claude-opus-[3-9]"),
    re.compile(r"^claude-sonnet-[3-9]"),
    re.compile(r"^claude-haiku-[3-9]"),
    re.compile(r"^claude-3-5-"),
    re.compile(r"^claude-3-(?:opus|sonnet|haiku)"),
    re.compile(r"^claude-[4-9]"),
    re.compile(r"^gemini-[2-9]"),
    re.compile(r"^gemini-1\.5"),
    re.compile(r"^pixtral"),
    re.compile(r"^llava"),
    re.compile(r"^moondream"),
    re.compile(r"^bakllava"),
    re.compile(r"-vision"),
    re.compile(r"-multimodal"),
)

def _matches_any(value: str, patterns: Iterable[re.Pattern[str]]) -> bool:
    return any(p.search(value) for p in patterns)


def heuristic_capabilities_from_id(provider: str, model_id: str) -> ProviderCapabilities:
    """Best-effort capability inference from the model id alone.

    Order matters: we resolve the most distinctive shapes first
    (embedding, pure audio) before falling back to vision / reasoning /
    plain chat.
    """
    lid = (model_id or "").lower()
    caps = ProviderCapabilities()

    if _matches_any(lid, _EMBEDDING_PATTERNS):
        caps.embedding = True
        return caps

    if _matches_any(lid, _PURE_AUDIO_PATTERNS):
        caps.audio = True
        return caps

    if _matches_any(lid, _AUDIO_CHAT_PATTERNS):
        caps.chat = True
        caps.audio = True
        return caps

    is_reasoning = _matches_any(lid, _REASONING_PATTERNS)
    is_vision = _matches_any(lid, _VISION_PATTERNS)

    caps.chat = True
    caps.function_calling = True
    caps.tool_use = True
    if is_vision:
        caps.vision = True
    if is_reasoning:
        caps.reasoning = True
    return caps


# ==================== MERGE / ENRICH ====================


def enrich(
    provider: str,
    raw_id: str,
    base: Optional[ProviderModelInfo] = None,
) -> ProviderModelInfo:
    """Return a normalised :class:`ProviderModelInfo` for ``raw_id``.

    The API response (``base``) is the authoritative source: every flag
    the SDK explicitly set to ``True`` is preserved. Heuristic flags are
    OR-merged on top so that fields the API did not determine
    (e.g. Google AI Studio reports ``chat`` from ``supported_actions``
    but never emits a vision/reasoning flag) get filled in by the
    family-pattern regex. The heuristic can only ADD truths — it never
    overrides a ``True`` from the API.
    """
    heuristic_caps = heuristic_capabilities_from_id(provider, raw_id)

    if base is None:
        return ProviderModelInfo(
            id=raw_id,
            display_name=raw_id,
            capabilities=heuristic_caps,
            source="heuristic",
        )

    merged = base.model_copy(deep=True)

    # Embedding ids must never be flagged as chat/vision/etc by the
    # heuristic — that would smuggle them into the AI Service list.
    if heuristic_caps.embedding:
        merged.capabilities.embedding = True
        return merged

    # OR-merge for the remaining flags. API truths win; heuristic only
    # contributes capabilities the API left at False.
    for field_name in ProviderCapabilities.model_fields:
        if not getattr(merged.capabilities, field_name) and getattr(
            heuristic_caps, field_name
        ):
            setattr(merged.capabilities, field_name, True)
    return merged


# ==================== FILTERS ====================


def is_embedding_model(info: ProviderModelInfo) -> bool:
    """True for models suitable for an Embedding Service."""
    return info.capabilities.embedding


def is_chat_model(info: ProviderModelInfo) -> bool:
    """True for models suitable for an AI Service.

    AI Services are an umbrella over chat, vision, audio and reasoning
    models — anything that is not a pure embedding. ``whisper-1`` /
    ``tts-1`` keep ``chat=False`` but ``audio=True`` so they show up in
    the AI Service wizard but are clearly tagged.
    """
    caps = info.capabilities
    if caps.embedding:
        return False
    return any((caps.chat, caps.audio, caps.vision, caps.reasoning))
