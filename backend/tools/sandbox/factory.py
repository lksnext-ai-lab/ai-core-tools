"""
Sandbox provider factory.

``resolve_provider`` is the single entry point used by ``agentTools.py`` to
obtain a concrete ``SandboxProvider`` instance.

Resolution order (IT-0 / IT-1+):
1. ``agent.app.sandbox_provider``  — app-level override (available from IT-1)
2. ``SANDBOX_DEFAULT_PROVIDER``    — system-wide default env var

The resolved provider name must match a registered provider; if it does not,
``SandboxProviderUnavailableError`` is raised instead of silently falling
back to a default.

The ``SANDBOX_ALLOWED_PROVIDERS`` env var (comma-separated) is checked in
IT-2 to gate which providers app owners may select.  It is parsed here
already so the variable name is consistent across iterations.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from utils.logger import get_logger
from .provider import SandboxProvider

if TYPE_CHECKING:
    from models.agent import Agent

logger = get_logger(__name__)


class SandboxProviderUnavailableError(RuntimeError):
    """Raised when no usable sandbox provider can be resolved."""


def _build_registry() -> dict[str, type[SandboxProvider]]:
    """Build the provider registry, importing optional providers lazily."""
    registry: dict[str, type[SandboxProvider]] = {}
    try:
        from .opensandbox_provider import OpenSandboxProvider  # noqa: PLC0415
        registry[OpenSandboxProvider.PROVIDER_NAME] = OpenSandboxProvider
    except Exception:
        # opensandbox package not installed — provider unavailable.
        pass
    try:
        from .daytona_provider import DaytonaProvider  # noqa: PLC0415
        registry[DaytonaProvider.PROVIDER_NAME] = DaytonaProvider
    except Exception:
        logger.exception("Failed to register Daytona sandbox provider")
    try:
        from .e2b_provider import E2BProvider  # noqa: PLC0415
        registry[E2BProvider.PROVIDER_NAME] = E2BProvider
    except Exception:
        logger.exception("Failed to register E2B sandbox provider")
    return registry


# Registry maps provider name → class.  Extend here when new providers land.
_PROVIDER_REGISTRY: dict[str, type[SandboxProvider]] = _build_registry()

_DEFAULT_PROVIDER_ENV = "SANDBOX_DEFAULT_PROVIDER"
_ALLOWED_PROVIDERS_ENV = "SANDBOX_ALLOWED_PROVIDERS"


def resolve_provider(agent: "Agent | None" = None) -> SandboxProvider:
    """Return an instantiated ``SandboxProvider`` for *agent*.

    Resolution order:
    1. ``agent.app.sandbox_provider``   — app-level override (IT-1)
    2. ``SANDBOX_DEFAULT_PROVIDER``     — system-wide default env var

    Args:
        agent: The agent requesting a sandbox.  May be ``None`` in tests.

    Returns:
        A ready-to-use ``SandboxProvider`` instance.

    Raises:
        SandboxProviderUnavailableError: If the resolved provider name is not
            registered (unknown name, or the package/dependency required by
            that provider is not installed).
    """
    # 1. App-level override (IT-1)
    app_provider: str | None = None
    try:
        if agent is not None and hasattr(agent, "app") and agent.app is not None:
            app_provider = getattr(agent.app, "sandbox_provider", None)
    except Exception:
        pass  # Relationship not loaded — fall through to system default

    # 2. System default
    system_default = os.getenv(_DEFAULT_PROVIDER_ENV, "opensandbox").lower()

    provider_name = (app_provider or system_default).lower()

    provider_class = _PROVIDER_REGISTRY.get(provider_name)
    if provider_class is None:
        available = ", ".join(sorted(_PROVIDER_REGISTRY.keys())) or "<none registered>"
        raise SandboxProviderUnavailableError(
            f"Sandbox provider '{provider_name}' is not available. "
            f"Registered providers: {available}."
        )

    logger.debug("Resolved sandbox provider: %s (agent=%s)", provider_class.PROVIDER_NAME, agent)
    return provider_class()
