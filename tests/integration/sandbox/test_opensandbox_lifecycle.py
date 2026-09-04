"""
Integration tests for OpenSandboxProvider lifecycle (Phase 3).

All OpenSandbox SDK calls are mocked via unittest.mock.patch — no real
OpenSandbox connection is required.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tools.sandbox.provider import SandboxExpiredError
from tools.sandbox.opensandbox_provider import OpenSandboxProvider, _META_SANDBOX

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def provider():
    """OpenSandboxProvider with SandboxSync replaced by a controllable mock.

    Yields (prov, mock_sdk) where:
    - prov has _connection_config pre-set so _get_config() never calls _get_connection_config()
    - mock_sdk has .resume and .create attributes for SDK-level assertions
    """
    with patch("tools.sandbox.opensandbox_provider.SandboxSync") as mock_sdk:
        mock_sdk.resume = MagicMock()
        mock_sdk.create = MagicMock()
        prov = OpenSandboxProvider()
        prov._connection_config = {}
        yield prov, mock_sdk


def _make_sandbox_mock(sandbox_id: str) -> MagicMock:
    """Return a minimal SandboxSync-like mock with a given id."""
    sb = MagicMock()
    sb.id = sandbox_id
    # Prevent CodeInterpreterSync from needing real objects
    sb.files = MagicMock()
    return sb


# ---------------------------------------------------------------------------
# create_sandbox — resume path
# ---------------------------------------------------------------------------


def test_resume_succeeds(provider):
    """existing_sandbox_id is passed to SandboxSync.resume; handle has the same id."""
    prov, mock_sdk = provider
    fresh_sandbox = _make_sandbox_mock("sbx_existing")
    mock_sdk.resume.return_value = fresh_sandbox

    with patch.object(prov, "_setup_sandbox_handle") as mock_setup:
        mock_setup.return_value = MagicMock(sandbox_id="sbx_existing", session_key="conv_1_1")
        handle = prov.create_sandbox(
            "/workspace",
            existing_sandbox_id="sbx_existing",
            session_key="conv_1_1",
        )

    mock_sdk.resume.assert_called_once_with("sbx_existing", connection_config={})
    mock_sdk.create.assert_not_called()
    assert handle.sandbox_id == "sbx_existing"


def test_resume_fails_with_expiry_falls_back_to_create(provider):
    """SDK expiry exception on resume → SandboxSync.create is called instead."""
    prov, mock_sdk = provider
    SDKExpiredError = type("SDKExpiredError", (Exception,), {})
    mock_sdk.resume.side_effect = SDKExpiredError("gone")
    prov._sdk_expiry_exceptions = (SDKExpiredError,)

    fresh_sandbox = _make_sandbox_mock("sbx_new")
    mock_sdk.create.return_value = fresh_sandbox

    with patch.object(prov, "_setup_sandbox_handle") as mock_setup:
        mock_setup.return_value = MagicMock(sandbox_id="sbx_new")
        handle = prov.create_sandbox("/workspace", existing_sandbox_id="sbx_old")

    mock_sdk.create.assert_called_once()
    assert handle.sandbox_id == "sbx_new"


def test_resume_unexpected_error_falls_back_to_create(provider):
    """Non-expiry exception during resume falls back to a fresh sandbox."""
    prov, mock_sdk = provider
    prov._sdk_expiry_exceptions = ()  # nothing maps to expiry
    mock_sdk.resume.side_effect = ValueError("unexpected")

    fresh_sandbox = _make_sandbox_mock("sbx_new")
    mock_sdk.create.return_value = fresh_sandbox

    with patch.object(prov, "_setup_sandbox_handle") as mock_setup:
        mock_setup.return_value = MagicMock(sandbox_id="sbx_new")
        handle = prov.create_sandbox("/workspace", existing_sandbox_id="sbx_old")

    mock_sdk.create.assert_called_once()
    assert handle.sandbox_id == "sbx_new"


def test_no_resume_when_sdk_lacks_resume(provider):
    """When _can_resume is False, SandboxSync.resume is never called."""
    prov, mock_sdk = provider
    prov._can_resume = False

    fresh_sandbox = _make_sandbox_mock("sbx_fresh")
    mock_sdk.create.return_value = fresh_sandbox

    with patch.object(prov, "_setup_sandbox_handle") as mock_setup:
        mock_setup.return_value = MagicMock(sandbox_id="sbx_fresh")
        prov.create_sandbox("/workspace", existing_sandbox_id="sbx_old")

    mock_sdk.resume.assert_not_called()
    mock_sdk.create.assert_called_once()


# ---------------------------------------------------------------------------
# renew_sandbox
# ---------------------------------------------------------------------------


def test_renew_sandbox_refreshes_idle_ttl(provider, monkeypatch):
    """renew_sandbox refreshes sandbox.renew to the configured idle window."""
    prov, _ = provider
    prov._can_renew = True
    monkeypatch.setattr("config.SANDBOX_IDLE_TIMEOUT_S", 120, raising=False)
    mock_sandbox = MagicMock()
    handle = MagicMock()
    handle.metadata = {_META_SANDBOX: mock_sandbox}

    prov.renew_sandbox(handle, timedelta(minutes=30))

    mock_sandbox.renew.assert_called_once_with(timeout=timedelta(seconds=120))


def test_renew_sandbox_noop_when_cannot_renew(provider):
    """renew_sandbox does nothing when _can_renew is False."""
    prov, _ = provider
    prov._can_renew = False
    mock_sandbox = MagicMock()
    handle = MagicMock()
    handle.metadata = {_META_SANDBOX: mock_sandbox}

    prov.renew_sandbox(handle, timedelta(minutes=30))  # should not raise

    mock_sandbox.renew.assert_not_called()


def test_renew_sandbox_raises_expired_on_sdk_error(provider):
    """renew_sandbox raises SandboxExpiredError when SDK signals expiry."""
    prov, _ = provider
    prov._can_renew = True
    SDKExpiredError = type("SDKExpiredError", (Exception,), {})
    prov._sdk_expiry_exceptions = (SDKExpiredError,)
    mock_sandbox = MagicMock()
    mock_sandbox.renew.side_effect = SDKExpiredError("gone")
    handle = MagicMock()
    handle.sandbox_id = "sbx_1"
    handle.metadata = {_META_SANDBOX: mock_sandbox}

    with pytest.raises(SandboxExpiredError):
        prov.renew_sandbox(handle, timedelta(minutes=30))


def test_renew_sandbox_no_sdk_object_raises_expired(provider):
    """renew_sandbox raises SandboxExpiredError when sandbox object missing from metadata."""
    prov, _ = provider
    prov._can_renew = True
    handle = MagicMock()
    handle.sandbox_id = "sbx_ghost"
    handle.metadata = {}  # no _META_SANDBOX key

    with pytest.raises(SandboxExpiredError):
        prov.renew_sandbox(handle, timedelta(minutes=30))

