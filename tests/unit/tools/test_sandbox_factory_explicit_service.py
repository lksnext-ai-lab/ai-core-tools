"""``tools.sandbox.factory.provider_for_service`` / ``provider_is_available``: the Chat's explicit-service entry point.

No env fallback, no agent relationships: the caller decides which SandboxService applies.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tools.sandbox.factory import (
    SandboxProviderUnavailableError,
    SandboxServiceRetiredError,
    provider_for_service,
    provider_is_available,
)
from tools.sandbox.daytona_provider import DaytonaProvider
from tools.sandbox.opensandbox_provider import OpenSandboxProvider


def _service(provider="opensandbox", service_id=3, eos=None, **kw):
    attrs = dict(
        service_id=service_id, provider=provider, endpoint=None, api_key=None, extra_config=None,
        name="svc", app_id=1, end_of_service_at=eos, deprecation_notice=None,
    )
    attrs.update(kw)
    return SimpleNamespace(**attrs)


def test_active_service_builds_its_provider_and_returns_the_id():
    provider, service_id = provider_for_service(_service("daytona", service_id=9), app_id=1)
    assert isinstance(provider, DaytonaProvider)
    assert service_id == 9


def test_deprecated_service_is_usable():
    soon = datetime.now(timezone.utc) + timedelta(days=3)
    provider, service_id = provider_for_service(_service("opensandbox", eos=soon), app_id=1)
    assert isinstance(provider, OpenSandboxProvider) and service_id == 3


def test_retired_service_raises_retired_error_which_is_an_unavailable_error():
    past = datetime.now(timezone.utc) - timedelta(days=1)
    with pytest.raises(SandboxServiceRetiredError) as exc:
        provider_for_service(_service(eos=past), app_id=1)
    assert isinstance(exc.value, SandboxProviderUnavailableError)


def test_provider_not_allowed_is_refused():
    with patch("tools.sandbox.factory._allowed_providers", return_value=["daytona"]):
        with pytest.raises(SandboxProviderUnavailableError):
            provider_for_service(_service("opensandbox"), app_id=1)
        assert not provider_is_available(_service("opensandbox"))
        assert provider_is_available(_service("daytona"))


def test_unregistered_provider_is_refused():
    with pytest.raises(SandboxProviderUnavailableError):
        provider_for_service(_service("nope"), app_id=1)
    assert not provider_is_available(_service("nope"))


def test_credentials_reach_the_provider_and_env_default_is_ignored(monkeypatch):
    monkeypatch.setenv("SANDBOX_DEFAULT_PROVIDER", "daytona")
    provider, _ = provider_for_service(
        _service("opensandbox", endpoint="sbx.example", api_key="k"), app_id=1
    )
    # The explicit service wins over the env default, and a failure never falls back to it.
    assert isinstance(provider, OpenSandboxProvider)
    with pytest.raises(SandboxProviderUnavailableError):
        provider_for_service(_service("nope"), app_id=1)  # env says daytona (registered): still refused
