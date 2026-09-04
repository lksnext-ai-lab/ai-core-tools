"""
Sandbox provider factory.

``resolve_provider`` is the single entry point used by ``agentTools.py`` to
obtain a concrete ``SandboxProvider`` instance.

Resolution order:
1. ``agent.sandbox_service``           — agent-level ``SandboxService`` override
2. ``agent.app.default_sandbox_service`` — app-level ``SandboxService`` override
3. ``SANDBOX_DEFAULT_PROVIDER``         — system-wide default env var (zero-arg
   provider construction — behaviour is unchanged when nothing is configured)

The resolved provider name must match a registered provider; if it does not,
``SandboxProviderUnavailableError`` is raised instead of silently falling
back to a default.

The ``SANDBOX_ALLOWED_PROVIDERS`` env var (comma-separated, parsed by
``config.py``) is enforced in ``_provider_class_for`` — a provider that is
registered but not in this allowlist raises ``SandboxProviderUnavailableError``
just like an unregistered one. An empty/unset allowlist means "no
restriction" (preserves prior behavior for deployments that have not
configured it). ``SandboxServiceService`` performs the same check at
config-save time so the UI gets immediate feedback rather than only failing
on first use.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from utils.logger import get_logger
from .provider import SandboxProvider

if TYPE_CHECKING:
    from models.agent import Agent
    from models.sandbox_service import SandboxService

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


def _credentials_from_service(service: "SandboxService") -> dict[str, Any]:
    """Map a resolved ``SandboxService`` row onto the credentials dict shape
    each concrete provider's constructor expects.

    Args:
        service: The resolved ``SandboxService`` row (agent- or app-level).

    Returns:
        A provider-specific credentials dict. Unknown providers return an
        empty dict (the provider constructor then behaves as if unconfigured,
        falling back to its own env-var defaults).
    """
    from tools.sandbox_service_utils import parse_extra_config  # noqa: PLC0415

    provider_name = (service.provider or "").strip().lower()
    extra = parse_extra_config(provider_name, service.extra_config)

    if provider_name == "opensandbox":
        return {
            "domain": service.endpoint or None,
            "api_key": service.api_key or None,
            "image": extra.get("image"),
        }
    if provider_name == "daytona":
        return {
            "api_key": service.api_key or None,
            "api_url": service.endpoint or None,
            "target": extra.get("target"),
        }
    if provider_name == "e2b":
        return {
            "api_key": service.api_key or None,
            "template": extra.get("template"),
        }
    return {}


def _resolve_sandbox_service(agent: "Agent | None") -> "SandboxService | None":
    """Return the ``SandboxService`` that applies to *agent*, if any.

    Checks ``agent.sandbox_service`` first, then falls back to
    ``agent.app.default_sandbox_service``. Any relationship-loading error
    (e.g. detached instance) is treated as "not configured" so callers fall
    through to the system-wide default.
    """
    try:
        if agent is None:
            return None
        service = getattr(agent, "sandbox_service", None)
        if service is not None:
            return service
        app = getattr(agent, "app", None)
        if app is not None:
            return getattr(app, "default_sandbox_service", None)
    except Exception:
        logger.debug("resolve_provider: SandboxService relationship not loaded", exc_info=True)
    return None


def _allowed_providers() -> list[str] | None:
    """Return the configured ``SANDBOX_ALLOWED_PROVIDERS`` allowlist, if any.

    Reads ``config.SANDBOX_ALLOWED_PROVIDERS`` (imported lazily to match the
    lazy-import convention used elsewhere in this module). An empty/unset
    list means "no restriction" — every registered provider stays usable,
    preserving existing behavior for deployments that have not opted into
    this restriction.
    """
    import config as settings  # noqa: PLC0415

    allowed = getattr(settings, "SANDBOX_ALLOWED_PROVIDERS", None)
    return allowed or None


def _provider_class_for(provider_name: str) -> type[SandboxProvider]:
    """Return the registered provider class for *provider_name* or raise."""
    provider_class = _PROVIDER_REGISTRY.get(provider_name)
    if provider_class is None:
        available = ", ".join(sorted(_PROVIDER_REGISTRY.keys())) or "<none registered>"
        raise SandboxProviderUnavailableError(
            f"Sandbox provider '{provider_name}' is not available. "
            f"Registered providers: {available}."
        )

    allowed = _allowed_providers()
    if allowed is not None and provider_name not in {p.strip().lower() for p in allowed}:
        raise SandboxProviderUnavailableError(
            f"Sandbox provider '{provider_name}' is not allowed in this deployment. "
            f"Allowed providers: {', '.join(sorted(allowed))}."
        )
    return provider_class


def resolve_provider_and_service_id(
    agent: "Agent | None" = None,
) -> tuple[SandboxProvider, int | None]:
    """Return an instantiated ``SandboxProvider`` for *agent*, plus the
    resolved ``SandboxService.service_id`` that produced it (``None`` when
    falling back to the system-wide env-var default, i.e. no DB-backed
    ``SandboxService`` row is involved).

    The id is needed by callers that persist sandbox session state (see
    ``SandboxSessionService``) so cleanup/reaper paths can later rebuild a
    provider with the *same* tenant credentials rather than falling back to
    zero-credential env defaults.

    Resolution order:
    1. ``agent.sandbox_service``            — agent-level override
    2. ``agent.app.default_sandbox_service`` — app-level override
    3. ``SANDBOX_DEFAULT_PROVIDER``          — system-wide default env var

    Args:
        agent: The agent requesting a sandbox.  May be ``None`` in tests.

    Returns:
        A ``(provider, sandbox_service_id)`` tuple.

    Raises:
        SandboxProviderUnavailableError: If the resolved provider name is not
            registered (unknown name, or the package/dependency required by
            that provider is not installed), or is registered but excluded
            by ``SANDBOX_ALLOWED_PROVIDERS``.
    """
    service = _resolve_sandbox_service(agent)

    if service is not None:
        provider_name = (service.provider or "").strip().lower()
        provider_class = _provider_class_for(provider_name)
        credentials = _credentials_from_service(service)
        service_id = getattr(service, "service_id", None)
        logger.debug(
            "Resolved sandbox provider: %s (agent=%s, sandbox_service_id=%s)",
            provider_class.PROVIDER_NAME,
            agent,
            service_id,
        )
        return provider_class(credentials=credentials), service_id

    system_default = os.getenv(_DEFAULT_PROVIDER_ENV, "opensandbox").lower()
    provider_class = _provider_class_for(system_default)

    logger.debug("Resolved sandbox provider: %s (agent=%s)", provider_class.PROVIDER_NAME, agent)
    return provider_class(), None


def resolve_provider(agent: "Agent | None" = None) -> SandboxProvider:
    """Return an instantiated ``SandboxProvider`` for *agent*.

    Thin wrapper over :func:`resolve_provider_and_service_id` for callers
    that don't need the resolved ``SandboxService.service_id`` (most tool
    call sites — see ``tools/agentTools.py``).

    Raises:
        SandboxProviderUnavailableError: see
            :func:`resolve_provider_and_service_id`.
    """
    provider, _service_id = resolve_provider_and_service_id(agent)
    return provider
