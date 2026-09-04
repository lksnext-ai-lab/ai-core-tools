"""Helpers for per-provider SandboxService ``extra_config`` handling.

Three sandbox providers (OpenSandbox, Daytona, E2B) share the single
``extra_config`` JSON column on ``SandboxService`` for their non-secret
tuning knobs (the secret credential itself lives in the standard ``api_key``
column, and a provider connection URL — when applicable — lives in
``endpoint``, mirroring the ``base_url`` pattern used by ``AIService``):

- OpenSandbox: ``{"image": ...}``
  (mirrors ``OPENSANDBOX_CODE_INTERPRETER_IMAGE``)
- Daytona: ``{"target": ..., "workspace": ..., "cpu": ..., "memory_gb": ...}``
  (mirrors what ``daytona_provider.py``'s ``_create_params()`` reads from
  ``DAYTONA_TARGET`` / ``DAYTONA_WORKSPACE`` / ``DAYTONA_CPU`` /
  ``DAYTONA_MEMORY_GB``)
- E2B: ``{"template": ..., "workspace": ...}``
  (mirrors ``E2B_TEMPLATE`` / ``E2B_WORKSPACE``)

A per-provider field allowlist is enforced on both build and parse so that
switching a service's ``provider`` value never leaves stale fields from the
previous provider lingering in ``extra_config``.

This module is intentionally dependency-free (no SQLAlchemy) so it can be
imported by both the runtime provider-resolution code and the admin/service
layer without circular-import risk — mirroring ``tools.aws_bedrock_utils``.
"""

from __future__ import annotations

import json
from typing import Any, Optional

# Per-provider allowlist of extra_config field names.
PROVIDER_EXTRA_CONFIG_FIELDS: dict[str, tuple[str, ...]] = {
    "opensandbox": ("image",),
    "daytona": ("target", "workspace", "cpu", "memory_gb"),
    "e2b": ("template", "workspace"),
}


def _normalize_provider(provider: Optional[str]) -> str:
    return (provider or "").strip().lower()


def build_extra_config(provider: Optional[str], **fields: Any) -> Optional[str]:
    """Serialise the non-secret, provider-specific fields into a JSON string.

    Only keys present in :data:`PROVIDER_EXTRA_CONFIG_FIELDS` for *provider*
    are kept — passing fields belonging to a different provider (e.g. after
    a form switches providers) is safe and simply drops them. Returns
    ``None`` when there is nothing to persist so the column stays NULL.

    Args:
        provider: Provider identifier (e.g. ``"opensandbox"``, ``"daytona"``,
            ``"e2b"``). Case-insensitive.
        **fields: Candidate generic field values (e.g. ``image=...``,
            ``target=...``, ``workspace=...``, ``cpu=...``, ``memory_gb=...``,
            ``template=...``). Unknown keys for the given provider are
            ignored.
    """
    allowed = PROVIDER_EXTRA_CONFIG_FIELDS.get(_normalize_provider(provider), ())
    data: dict[str, Any] = {}
    for key in allowed:
        value = fields.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
        data[key] = value
    return json.dumps(data) if data else None


def parse_extra_config(provider: Optional[str], extra_config_json: Any) -> dict:
    """Parse a service ``extra_config`` value into a dict scoped to *provider*.

    Accepts a JSON string, an already-parsed dict, or ``None``. Anything
    malformed degrades to an empty dict rather than raising. The result is
    filtered to the field allowlist for *provider*, so stale fields left over
    from a prior provider (before it was switched) never leak through.
    """
    allowed = PROVIDER_EXTRA_CONFIG_FIELDS.get(_normalize_provider(provider), ())
    parsed = _parse_json(extra_config_json)
    return {k: v for k, v in parsed.items() if k in allowed}


def _parse_json(raw: Any) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}
