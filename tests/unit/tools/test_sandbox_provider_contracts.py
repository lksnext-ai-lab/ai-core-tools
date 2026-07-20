"""
Unit tests — provider-agnostic SandboxProvider contracts
==========================================================

Salvaged from the retired ``test_sandbox_v2_phase1.py`` (which was written
almost entirely against the now-removed ``SubprocessProvider``). Only the
provider-agnostic assertions survive here:

  1. ``SandboxExpiredError`` is importable from the provider module.
  2. ``SandboxHandle`` has a ``session_key`` field (defaults / storage).
  3. The ``config`` module exposes the sandbox settings, with the
     ``opensandbox``-based defaults now that ``subprocess`` was removed.
  4. ``SandboxProvider.requires_file_sync`` defaults to ``True`` on the ABC,
     and every remaining concrete provider either inherits it or explicitly
     sets it.
"""

from __future__ import annotations

import os

import pytest


# ---------------------------------------------------------------------------
# 1. SandboxExpiredError importability
# ---------------------------------------------------------------------------


def test_sandbox_expired_error_is_importable():
    from tools.sandbox.provider import SandboxExpiredError

    err = SandboxExpiredError("test")
    assert isinstance(err, RuntimeError)
    assert str(err) == "test"


# ---------------------------------------------------------------------------
# 2. SandboxHandle fields
# ---------------------------------------------------------------------------


def test_sandbox_handle_defaults():
    from tools.sandbox.provider import SandboxHandle

    h = SandboxHandle(
        sandbox_id="abc",
        working_dir="/tmp",
        provider_name="test",
    )
    assert h.session_key is None
    assert h.metadata == {}


def test_sandbox_handle_session_key_stored():
    from tools.sandbox.provider import SandboxHandle

    h = SandboxHandle(
        sandbox_id="abc",
        working_dir="/tmp",
        provider_name="test",
        session_key="conv_1_2",
    )
    assert h.session_key == "conv_1_2"


# ---------------------------------------------------------------------------
# 3. config exposes sandbox settings — opensandbox-based defaults
# ---------------------------------------------------------------------------


def test_config_new_sandbox_settings():
    import config as settings

    assert hasattr(settings, "SANDBOX_MAX_OUTPUT_CHARS")
    assert hasattr(settings, "SANDBOX_MAX_EXECUTIONS_PER_TURN")
    assert hasattr(settings, "SANDBOX_RENEW_MINUTES")

    assert isinstance(settings.SANDBOX_MAX_OUTPUT_CHARS, int)
    assert isinstance(settings.SANDBOX_MAX_EXECUTIONS_PER_TURN, int)
    assert isinstance(settings.SANDBOX_RENEW_MINUTES, int)

    assert settings.SANDBOX_MAX_OUTPUT_CHARS == 20000
    assert settings.SANDBOX_MAX_EXECUTIONS_PER_TURN == int(
        os.getenv("SANDBOX_MAX_EXECUTIONS_PER_TURN", "5")
    )
    assert settings.SANDBOX_RENEW_MINUTES == 30


def test_config_no_install_timeout():
    import config as settings

    assert not hasattr(settings, "SANDBOX_SKILL_INSTALL_TIMEOUT_S")


def test_config_default_provider_is_opensandbox(monkeypatch):
    """``subprocess`` was removed — the process-wide default is now opensandbox."""
    monkeypatch.delenv("SANDBOX_DEFAULT_PROVIDER", raising=False)
    import importlib
    import config as settings

    importlib.reload(settings)
    try:
        assert settings.SANDBOX_DEFAULT_PROVIDER == "opensandbox"
        assert "subprocess" not in settings.SANDBOX_ALLOWED_PROVIDERS
        assert settings.SANDBOX_ALLOWED_PROVIDERS == ["opensandbox", "daytona", "e2b"]
    finally:
        importlib.reload(settings)


# ---------------------------------------------------------------------------
# 4. requires_file_sync capability flag
# ---------------------------------------------------------------------------


def test_requires_file_sync_defaults_true_on_abc():
    from tools.sandbox.provider import SandboxProvider

    assert SandboxProvider.requires_file_sync is True


@pytest.mark.parametrize(
    "module_path,class_name",
    [
        ("tools.sandbox.opensandbox_provider", "OpenSandboxProvider"),
        ("tools.sandbox.daytona_provider", "DaytonaProvider"),
        ("tools.sandbox.e2b_provider", "E2BProvider"),
    ],
)
def test_concrete_providers_declare_requires_file_sync(module_path, class_name):
    """Every remaining concrete provider either inherits the ABC default
    (True) or explicitly sets its own value — never leaves it undefined."""
    import importlib

    module = importlib.import_module(module_path)
    provider_class = getattr(module, class_name)

    assert isinstance(provider_class.requires_file_sync, bool)
