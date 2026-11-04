"""Public/extended agent card builders and catalog entries (step_011, FR-5/FR-6/FR-7/FR-8/FR-9).

Every function here is pure: it reads only an `A2AAgentSnapshot` (already
resolved by `visibility_service.resolve`/`list_visible`, with no DB access of
its own) plus process config (`CLIENT_CONFIG`, `APP_VERSION`,
`utils.a2a_config`). This is deliberate -- the SDK's `extended_card_modifier`
(`services/a2a_server/runtime.py`, step_012) calls `build_extended_card` on
every `GetExtendedAgentCard` request with no DB session available, and the
card/catalog endpoints (step_017) must stay well under NFR-8's p95 budget.

**Leak surface (AC-2).** `build_public_card`/`build_extended_card` read only
the fields `A2AAgentSnapshot` exposes -- never `Agent.system_prompt`,
`Agent.silo_id`, MCP/tool associations, or any AIService credential. The
extended card additionally exposes `a2a_examples`, which are operator-curated
usage examples (FR-6), not secrets.
"""

from __future__ import annotations

import os
from typing import Dict, List, Tuple

from a2a.server.request_handlers.response_helpers import agent_card_to_dict
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentProvider,
)
from a2a.types import AgentSkill as A2ASkill
from a2a.types import (
    APIKeySecurityScheme,
    SecurityRequirement,
    SecurityScheme,
    StringList,
)
from a2a.utils.constants import PROTOCOL_VERSION_1_0, TransportProtocol

from config import CLIENT_CONFIG
from services.a2a_server.snapshot import A2AAgentSnapshot
from tools.ai.model_catalog import heuristic_capabilities_from_id
from utils.a2a_config import agent_card_url, agent_rpc_url

# Same default as the FastAPI app's own `version=` (backend/main.py's
# `FastAPI(..., version=os.getenv('APP_VERSION', '0.2.37'))`) -- FR-5's
# `version` field is Mattin's own release version, not the agent's.
_APP_VERSION_DEFAULT = "0.2.37"

# Always declared, regardless of the agent's own configuration (FR-7).
_JSON_MEDIA_TYPE = "application/json"
_BASE_INPUT_MODES: Tuple[str, ...] = ("text/plain", _JSON_MEDIA_TYPE)
_BASE_OUTPUT_MODES: Tuple[str, ...] = ("text/plain",)

# Document MIME types the existing chat file pipeline accepts, taken verbatim
# from `FileReference.MIME_TYPES` (`backend/services/file_management_service.py`)
# -- never invented here (FR-7). `"image"`/`"unknown"` are excluded: images are
# handled separately, gated on the vision heuristic, and "unknown" has no real
# MIME type of its own.
_DOCUMENT_INPUT_MODES: Tuple[str, ...] = ("application/pdf", "application/msword")

# Concrete image MIME types, from `FileReference.IMAGE_MIME_TYPES`
# (same module) -- added only when the model is heuristically vision-capable.
_IMAGE_MIME_TYPES: Tuple[str, ...] = (
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/bmp",
    "image/webp",
)

# File output modes declared when the agent can produce files (FR-7).
_FILE_OUTPUT_MODES: Tuple[str, ...] = ("application/octet-stream",)


def _is_vision_capable(snap: A2AAgentSnapshot) -> bool:
    """`heuristic_capabilities_from_id(provider, model_id).vision` (FR-7).

    Deliberately ignores `supports_video` -- the spec is explicit that only
    the vision heuristic may add `image/*` input modes.
    """
    if not snap.ai_provider or not snap.model_id:
        return False
    return bool(heuristic_capabilities_from_id(snap.ai_provider, snap.model_id).vision)


def _default_input_modes(snap: A2AAgentSnapshot) -> List[str]:
    modes = list(_BASE_INPUT_MODES)
    if snap.accepts_files:
        for mime in _DOCUMENT_INPUT_MODES:
            if mime not in modes:
                modes.append(mime)
        if _is_vision_capable(snap):
            for mime in _IMAGE_MIME_TYPES:
                if mime not in modes:
                    modes.append(mime)
    return modes


def _default_output_modes(snap: A2AAgentSnapshot) -> List[str]:
    modes = list(_BASE_OUTPUT_MODES)
    if snap.has_output_parser and _JSON_MEDIA_TYPE not in modes:
        modes.append(_JSON_MEDIA_TYPE)
    if snap.can_produce_files:
        for mime in _FILE_OUTPUT_MODES:
            if mime not in modes:
                modes.append(mime)
        if _is_vision_capable(snap):
            for mime in _IMAGE_MIME_TYPES:
                if mime not in modes:
                    modes.append(mime)
    return modes


def _build_skills(snap: A2AAgentSnapshot, *, with_examples: bool) -> List[A2ASkill]:
    """One `AgentSkill` per attached Mattin Skill, else a synthetic `chat` skill (FR-6).

    Examples (`a2a_examples`) are attached only when `with_examples` is True --
    the public card never carries them (FR-5), only the extended card (FR-8).
    """
    tags = list(snap.skill_tags)
    examples = list(snap.examples) if with_examples else []

    if not snap.skills:
        return [
            A2ASkill(
                id="chat",
                name=snap.card_name,
                description=snap.card_description,
                tags=tags,
                examples=examples,
            )
        ]

    return [
        A2ASkill(
            id=f"skill-{skill_id}",
            name=name,
            description=description,
            tags=tags,
            examples=examples,
        )
        for skill_id, name, description in snap.skills
    ]


def build_public_card(snap: A2AAgentSnapshot, base_url: str) -> AgentCard:
    """Builds the minimal public A2A v1.0 card for one agent (FR-5).

    Exposes only name/description (override or agent default), version,
    provider, the RPC interface, capabilities, the apiKey security scheme,
    input/output modes and skills -- no prompt, model, provider id, silo or
    tool/MCP names, and no examples (AC-2).
    """
    rpc_url = agent_rpc_url(base_url, snap.app_slug, snap.agent_id)
    security_scheme = SecurityScheme(
        api_key_security_scheme=APIKeySecurityScheme(location="header", name="X-API-KEY")
    )
    return AgentCard(
        name=snap.card_name,
        description=snap.card_description,
        version=os.getenv("APP_VERSION", _APP_VERSION_DEFAULT),
        provider=AgentProvider(organization=CLIENT_CONFIG.client_name, url=base_url),
        supported_interfaces=[
            AgentInterface(
                url=rpc_url,
                protocol_binding=TransportProtocol.JSONRPC,
                protocol_version=PROTOCOL_VERSION_1_0,
            )
        ],
        capabilities=AgentCapabilities(streaming=True, push_notifications=False, extended_agent_card=True),
        security_schemes={"apiKey": security_scheme},
        security_requirements=[SecurityRequirement(schemes={"apiKey": StringList(list=[])})],
        default_input_modes=_default_input_modes(snap),
        default_output_modes=_default_output_modes(snap),
        skills=_build_skills(snap, with_examples=False),
    )


def _extended_description(snap: A2AAgentSnapshot) -> str:
    """The public description plus a one-line capability summary (FR-8).

    Never includes secrets, prompt text, or any id beyond `agent_id`
    (which is not added here -- the caller already knows it, it is in the
    URL path).
    """
    accepts = "yes" if snap.accepts_files else "no"
    structured = "yes" if snap.has_output_parser else "no"
    memory = "yes" if snap.has_memory else "no"
    summary = f"Accepts files: {accepts}; Structured output: {structured}; Memory: {memory}"
    base = snap.card_description
    return f"{base} {summary}".strip() if base else summary


def build_extended_card(snap: A2AAgentSnapshot, base_url: str) -> AgentCard:
    """Builds the extended card: the public card plus examples and an extended description (FR-8).

    Called by `GetExtendedAgentCard`, through the SDK's `extended_card_modifier`
    (`services/a2a_server/runtime.py`'s `_extended_modifier`, step_012), which
    passes `ctx.state["a2a"].snapshot` -- so the returned card is always bound
    to the exact agent the caller authenticated against, never another one.
    """
    card = build_public_card(snap, base_url)
    extended_skills = _build_skills(snap, with_examples=True)
    return AgentCard(
        name=card.name,
        description=_extended_description(snap),
        version=card.version,
        provider=card.provider,
        supported_interfaces=list(card.supported_interfaces),
        capabilities=card.capabilities,
        security_schemes=dict(card.security_schemes),
        security_requirements=list(card.security_requirements),
        default_input_modes=list(card.default_input_modes),
        default_output_modes=list(card.default_output_modes),
        skills=extended_skills,
    )


def card_to_json(card: AgentCard) -> dict:
    """Serializes an `AgentCard` to the SDK's canonical JSON shape."""
    return agent_card_to_dict(card)


def catalog_entry(snap: A2AAgentSnapshot, base_url: str) -> Dict[str, object]:
    """One FR-9 catalog row: `agent_id`, name, description, and absolute URLs."""
    return {
        "agent_id": snap.agent_id,
        "name": snap.card_name,
        "description": snap.card_description,
        "card_url": agent_card_url(base_url, snap.app_slug, snap.agent_id),
        "rpc_url": agent_rpc_url(base_url, snap.app_slug, snap.agent_id),
    }


__all__ = ["build_public_card", "build_extended_card", "card_to_json", "catalog_entry"]
