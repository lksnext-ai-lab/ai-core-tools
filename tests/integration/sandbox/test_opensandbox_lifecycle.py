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


def test_resume_unexpected_error_raises_sandbox_expired_error(provider):
    """Non-expiry exception during resume → SandboxExpiredError is raised."""
    prov, mock_sdk = provider
    prov._sdk_expiry_exceptions = ()  # nothing maps to expiry
    mock_sdk.resume.side_effect = ValueError("unexpected")

    with pytest.raises(SandboxExpiredError):
        prov.create_sandbox("/workspace", existing_sandbox_id="sbx_old")


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


# ---------------------------------------------------------------------------
# ensure_skill
# ---------------------------------------------------------------------------


def test_ensure_skill_file_write_success(provider, mock_skill_with_files):
    """ensure_skill writes all SkillFile records → phases['files'] == 'ok'."""
    prov, _ = provider
    handle = MagicMock()
    handle.sandbox_id = "sbx_1"
    handle.active_skills = {}

    with patch.object(prov, "write_file") as mock_write:
        result = prov.ensure_skill(handle, mock_skill_with_files)

    assert result["phases"]["files"] == "ok"
    assert mock_write.call_count == len(mock_skill_with_files.files)


def test_ensure_skill_skips_directory_placeholders(provider):
    """Directory entries from ZIP packages must not be uploaded as files."""
    prov, _ = provider
    handle = MagicMock()
    handle.sandbox_id = "sbx_1"
    handle.active_skills = {}
    skill = SimpleNamespace(
        skill_id=103,
        name="pptx",
        bootstrap_script_path=None,
        files=[
            SimpleNamespace(path="scripts/", content_text="", content_bytes=None),
            SimpleNamespace(path="scripts/__init__.py", content_text="", content_bytes=None),
        ],
    )

    with patch.object(prov, "write_file") as mock_write:
        result = prov.ensure_skill(handle, skill)

    assert result["phases"]["files"] == "ok"
    mock_write.assert_called_once()
    assert mock_write.call_args.args[1] == "/workspace/.skills/pptx/scripts/__init__.py"


def test_ensure_skill_no_bootstrap_skips_phase(provider, mock_skill_with_files):
    """ensure_skill with no bootstrap_script_path sets bootstrap == 'skipped'."""
    prov, _ = provider
    handle = MagicMock()
    handle.sandbox_id = "sbx_1"
    handle.active_skills = {}

    with patch.object(prov, "write_file"):
        result = prov.ensure_skill(handle, mock_skill_with_files)

    assert result["phases"]["bootstrap"] == "skipped"


def test_ensure_skill_bootstrap_success(provider, mock_skill_with_bootstrap):
    """ensure_skill runs bootstrap script → phases['bootstrap'] == 'ok'."""
    prov, _ = provider
    handle = MagicMock()
    handle.sandbox_id = "sbx_1"
    handle.active_skills = {}

    with patch.object(prov, "write_file"):
        with patch.object(prov, "run_code", return_value="") as mock_run:
            result = prov.ensure_skill(handle, mock_skill_with_bootstrap)

    assert result["phases"]["bootstrap"] == "ok"
    mock_run.assert_called_once()


def test_ensure_skill_bootstrap_uses_bash_for_shell_script(provider):
    """A .sh bootstrap must run in the Bash sandbox context, not Python."""
    prov, _ = provider
    handle = MagicMock()
    handle.sandbox_id = "sbx_1"
    handle.active_skills = {}
    skill = SimpleNamespace(
        skill_id=104,
        name="shell_bootstrap",
        bootstrap_script_path="scripts/bootstrap.sh",
        files=[
            SimpleNamespace(
                path="scripts/bootstrap.sh",
                content_text="#!/usr/bin/env bash\necho ok\n",
                content_bytes=None,
            ),
        ],
    )

    with patch.object(prov, "write_file"):
        with patch.object(prov, "run_code", return_value="") as mock_run:
            result = prov.ensure_skill(handle, skill)

    assert result["phases"]["bootstrap"] == "ok"
    assert mock_run.call_args.kwargs["language"] == "bash"
    script = mock_run.call_args.args[1]
    assert "source /opt/opensandbox/code-interpreter-env.sh python" in script
    assert "source /opt/opensandbox/code-interpreter-env.sh node" in script
    assert "sudo() { \"$@\"; }" in script
    assert "export NODE_PATH=\"$(npm root -g)" in script
    assert ") 2>&1" in script
    assert "__AICT_BOOTSTRAP_EXIT_CODE__=" in script


def test_ensure_skill_bootstrap_failure(provider, mock_skill_with_bootstrap):
    """ensure_skill with bootstrap exception → phases['bootstrap'] starts with 'failed:'."""
    prov, _ = provider
    handle = MagicMock()
    handle.sandbox_id = "sbx_1"
    handle.active_skills = {}

    with patch.object(prov, "write_file"):
        with patch.object(prov, "run_code", side_effect=RuntimeError("script error")):
            result = prov.ensure_skill(handle, mock_skill_with_bootstrap)

    assert result["phases"]["bootstrap"].startswith("failed:")


@pytest.mark.parametrize(
    "output",
    [
        "[Error] SyntaxError: unmatched ')'",
        "[stderr]\nboom",
        "__AICT_BOOTSTRAP_EXIT_CODE__=1",
    ],
)
def test_ensure_skill_bootstrap_failure_from_run_code_output(
    provider, mock_skill_with_bootstrap, output
):
    """run_code error/stderr text must not be treated as successful bootstrap."""
    prov, _ = provider
    handle = MagicMock()
    handle.sandbox_id = "sbx_1"
    handle.active_skills = {}

    with patch.object(prov, "write_file"):
        with patch.object(prov, "run_code", return_value=output):
            result = prov.ensure_skill(handle, mock_skill_with_bootstrap)

    assert result["phases"]["bootstrap"].startswith("failed:")
    assert output in result["phases"]["bootstrap"]


def test_ensure_skill_idempotent(provider, mock_skill_with_files):
    """Calling ensure_skill twice with same sandbox_id returns the cached state dict."""
    prov, _ = provider
    handle = MagicMock()
    handle.sandbox_id = "sbx_1"
    handle.active_skills = {}

    with patch.object(prov, "write_file"):
        first = prov.ensure_skill(handle, mock_skill_with_files)
        second = prov.ensure_skill(handle, mock_skill_with_files)

    assert first is second


def test_ensure_skill_retry_recomputes(provider, mock_skill_with_files):
    """ensure_skill with retry=True re-runs write_file even if cached result is healthy."""
    prov, _ = provider
    handle = MagicMock()
    handle.sandbox_id = "sbx_1"
    handle.active_skills = {}

    with patch.object(prov, "write_file") as mock_write:
        prov.ensure_skill(handle, mock_skill_with_files)
        write_count_first = mock_write.call_count
        prov.ensure_skill(handle, mock_skill_with_files, retry=True)
        assert mock_write.call_count == write_count_first * 2
