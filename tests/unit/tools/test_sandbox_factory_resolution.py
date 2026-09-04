"""
Unit tests — ``tools.sandbox.factory.resolve_provider`` resolution chain.

Verifies the resolution precedence introduced alongside the ``SandboxService``
entity:

1. ``agent.sandbox_service``            — agent-level override
2. ``agent.app.default_sandbox_service`` — app-level override
3. ``SANDBOX_DEFAULT_PROVIDER``          — system-wide default env var
4. ``SandboxProviderUnavailableError``   — unknown/unregistered provider name

Also verifies that a resolved ``SandboxService`` row's credentials
(``provider``/``endpoint``/``api_key``/``extra_config``) reach the concrete
provider constructor as the expected ``credentials`` dict shape.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest


def _make_sandbox_service(
    provider: str,
    *,
    service_id: int = 1,
    endpoint: str | None = None,
    api_key: str | None = None,
    extra_config: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        service_id=service_id,
        provider=provider,
        endpoint=endpoint,
        api_key=api_key,
        extra_config=extra_config,
    )


def _make_agent(
    *,
    sandbox_service: SimpleNamespace | None = None,
    app_default_sandbox_service: SimpleNamespace | None = None,
) -> SimpleNamespace:
    app = SimpleNamespace(default_sandbox_service=app_default_sandbox_service)
    return SimpleNamespace(id=1, app=app, sandbox_service=sandbox_service)


class TestResolutionPrecedence:
    def test_agent_sandbox_service_takes_precedence_over_app_default(self, monkeypatch):
        """agent.sandbox_service wins even when agent.app.default_sandbox_service is also set."""
        monkeypatch.delenv("SANDBOX_DEFAULT_PROVIDER", raising=False)
        from tools.sandbox.factory import resolve_provider
        from tools.sandbox.opensandbox_provider import OpenSandboxProvider
        from tools.sandbox.daytona_provider import DaytonaProvider

        agent_service = _make_sandbox_service("opensandbox", service_id=1)
        app_service = _make_sandbox_service("daytona", service_id=2)
        agent = _make_agent(sandbox_service=agent_service, app_default_sandbox_service=app_service)

        provider = resolve_provider(agent)

        assert isinstance(provider, OpenSandboxProvider)
        assert not isinstance(provider, DaytonaProvider)

    def test_falls_back_to_app_default_sandbox_service(self, monkeypatch):
        """When agent.sandbox_service is unset, agent.app.default_sandbox_service applies."""
        monkeypatch.delenv("SANDBOX_DEFAULT_PROVIDER", raising=False)
        from tools.sandbox.factory import resolve_provider
        from tools.sandbox.daytona_provider import DaytonaProvider

        app_service = _make_sandbox_service("daytona", service_id=2)
        agent = _make_agent(sandbox_service=None, app_default_sandbox_service=app_service)

        provider = resolve_provider(agent)

        assert isinstance(provider, DaytonaProvider)

    def test_falls_back_to_env_default_when_no_service_configured(self, monkeypatch):
        """No SandboxService anywhere → SANDBOX_DEFAULT_PROVIDER env var applies."""
        monkeypatch.setenv("SANDBOX_DEFAULT_PROVIDER", "e2b")
        from tools.sandbox.factory import resolve_provider
        from tools.sandbox.e2b_provider import E2BProvider

        agent = _make_agent(sandbox_service=None, app_default_sandbox_service=None)

        provider = resolve_provider(agent)

        assert isinstance(provider, E2BProvider)

    def test_none_agent_falls_back_to_env_default(self, monkeypatch):
        """resolve_provider(None) — used in tests/contexts without an agent."""
        monkeypatch.setenv("SANDBOX_DEFAULT_PROVIDER", "opensandbox")
        from tools.sandbox.factory import resolve_provider
        from tools.sandbox.opensandbox_provider import OpenSandboxProvider

        provider = resolve_provider(None)

        assert isinstance(provider, OpenSandboxProvider)

    def test_unknown_provider_name_on_sandbox_service_raises(self, monkeypatch):
        """An unresolvable provider name on a resolved SandboxService still raises,
        rather than silently falling back to the system default."""
        monkeypatch.setenv("SANDBOX_DEFAULT_PROVIDER", "opensandbox")
        from tools.sandbox.factory import resolve_provider, SandboxProviderUnavailableError

        agent_service = _make_sandbox_service("nonexistent-provider")
        agent = _make_agent(sandbox_service=agent_service)

        with pytest.raises(SandboxProviderUnavailableError) as exc_info:
            resolve_provider(agent)
        assert "nonexistent-provider" in str(exc_info.value)

    def test_unknown_env_default_provider_raises(self, monkeypatch):
        """Unknown SANDBOX_DEFAULT_PROVIDER (no SandboxService configured at all) raises."""
        monkeypatch.setenv("SANDBOX_DEFAULT_PROVIDER", "nonexistent-provider")
        from tools.sandbox.factory import resolve_provider, SandboxProviderUnavailableError

        agent = _make_agent(sandbox_service=None, app_default_sandbox_service=None)

        with pytest.raises(SandboxProviderUnavailableError) as exc_info:
            resolve_provider(agent)
        assert "nonexistent-provider" in str(exc_info.value)

    def test_agent_relationship_error_falls_through_to_env_default(self, monkeypatch):
        """A broken/detached relationship access must not blow up resolution."""
        monkeypatch.setenv("SANDBOX_DEFAULT_PROVIDER", "opensandbox")
        from tools.sandbox.factory import resolve_provider
        from tools.sandbox.opensandbox_provider import OpenSandboxProvider

        class ExplodingAgent:
            @property
            def sandbox_service(self):
                raise RuntimeError("detached instance")

        provider = resolve_provider(ExplodingAgent())

        assert isinstance(provider, OpenSandboxProvider)


class TestCredentialInjection:
    """A resolved SandboxService's credentials must reach the provider constructor."""

    def test_opensandbox_credentials_shape(self, monkeypatch):
        from tools.sandbox import factory

        service = _make_sandbox_service(
            "opensandbox",
            endpoint="opensandbox.example:8080",
            api_key="service-api-key",
            extra_config='{"image": "custom/image:v1"}',
        )
        agent = _make_agent(sandbox_service=service)

        with patch.object(
            factory._PROVIDER_REGISTRY["opensandbox"], "__init__", return_value=None
        ) as mock_init:
            factory.resolve_provider(agent)

        mock_init.assert_called_once_with(
            credentials={
                "domain": "opensandbox.example:8080",
                "api_key": "service-api-key",
                "image": "custom/image:v1",
            },
        )

    def test_daytona_credentials_shape(self, monkeypatch):
        from tools.sandbox import factory

        service = _make_sandbox_service(
            "daytona",
            endpoint="https://daytona.example/api",
            api_key="service-api-key",
            extra_config='{"target": "eu"}',
        )
        agent = _make_agent(sandbox_service=service)

        with patch.object(
            factory._PROVIDER_REGISTRY["daytona"], "__init__", return_value=None
        ) as mock_init:
            factory.resolve_provider(agent)

        mock_init.assert_called_once_with(
            credentials={
                "api_key": "service-api-key",
                "api_url": "https://daytona.example/api",
                "target": "eu",
            },
        )

    def test_e2b_credentials_shape(self, monkeypatch):
        from tools.sandbox import factory

        service = _make_sandbox_service(
            "e2b",
            api_key="service-api-key",
            extra_config='{"template": "custom-template"}',
        )
        agent = _make_agent(sandbox_service=service)

        with patch.object(
            factory._PROVIDER_REGISTRY["e2b"], "__init__", return_value=None
        ) as mock_init:
            factory.resolve_provider(agent)

        mock_init.assert_called_once_with(
            credentials={
                "api_key": "service-api-key",
                "template": "custom-template",
            },
        )

    def test_credentials_missing_extra_config_fields_are_none(self, monkeypatch):
        """Fields absent from extra_config resolve to None, not KeyError."""
        from tools.sandbox import factory

        service = _make_sandbox_service("e2b", api_key="service-api-key", extra_config=None)
        agent = _make_agent(sandbox_service=service)

        with patch.object(
            factory._PROVIDER_REGISTRY["e2b"], "__init__", return_value=None
        ) as mock_init:
            factory.resolve_provider(agent)

        mock_init.assert_called_once_with(
            credentials={"api_key": "service-api-key", "template": None},
        )


class TestAllowedProvidersEnforcement:
    """``SANDBOX_ALLOWED_PROVIDERS`` gates which registered providers may resolve."""

    def test_allows_everything_when_allowlist_unset(self, monkeypatch):
        monkeypatch.setattr("config.SANDBOX_ALLOWED_PROVIDERS", [], raising=False)
        from tools.sandbox.factory import resolve_provider
        from tools.sandbox.daytona_provider import DaytonaProvider

        service = _make_sandbox_service("daytona")
        agent = _make_agent(sandbox_service=service)

        provider = resolve_provider(agent)

        assert isinstance(provider, DaytonaProvider)

    def test_allows_provider_present_in_allowlist(self, monkeypatch):
        monkeypatch.setattr("config.SANDBOX_ALLOWED_PROVIDERS", ["opensandbox", "daytona"], raising=False)
        from tools.sandbox.factory import resolve_provider
        from tools.sandbox.daytona_provider import DaytonaProvider

        service = _make_sandbox_service("daytona")
        agent = _make_agent(sandbox_service=service)

        provider = resolve_provider(agent)

        assert isinstance(provider, DaytonaProvider)

    def test_rejects_registered_provider_excluded_from_allowlist(self, monkeypatch):
        monkeypatch.setattr("config.SANDBOX_ALLOWED_PROVIDERS", ["opensandbox"], raising=False)
        from tools.sandbox.factory import resolve_provider, SandboxProviderUnavailableError

        service = _make_sandbox_service("daytona")
        agent = _make_agent(sandbox_service=service)

        with pytest.raises(SandboxProviderUnavailableError) as exc_info:
            resolve_provider(agent)
        assert "daytona" in str(exc_info.value)
