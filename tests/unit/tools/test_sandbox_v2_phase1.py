"""
Unit tests — sandbox v2 Phase 1 API contracts
==============================================

Validates the following RFC v2 / sandbox-v2-migration Phase 1 changes:

  1. ``SandboxExpiredError`` is importable from the provider module.
  2. ``SandboxHandle`` has a ``session_key`` field.
  3. ``SubprocessProvider._safe_env`` filters secret-looking env vars.
  4. ``SubprocessProvider.run_code`` honours ``max_output_chars`` and appends
     the truncation marker.
  5. ``SubprocessProvider.run_code`` honours ``timeout`` param.
  6. ``SubprocessProvider.run_code`` forwards ``on_stderr`` lines.
  7. ``SubprocessProvider.list_files`` returns workspace-relative paths.
  8. ``config`` module exposes the new sandbox settings.
"""

from __future__ import annotations

import os
import threading
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. SandboxExpiredError importability
# ---------------------------------------------------------------------------


def test_sandbox_expired_error_is_importable():
    from backend.tools.sandbox.provider import SandboxExpiredError

    err = SandboxExpiredError("test")
    assert isinstance(err, RuntimeError)
    assert str(err) == "test"


# ---------------------------------------------------------------------------
# 2. SandboxHandle fields
# ---------------------------------------------------------------------------


def test_sandbox_handle_defaults():
    from backend.tools.sandbox.provider import SandboxHandle

    h = SandboxHandle(
        sandbox_id="abc",
        working_dir="/tmp",
        provider_name="test",
    )
    assert h.session_key is None
    assert h.metadata == {}


def test_sandbox_handle_session_key_stored():
    from backend.tools.sandbox.provider import SandboxHandle

    h = SandboxHandle(
        sandbox_id="abc",
        working_dir="/tmp",
        provider_name="test",
        session_key="conv_1_2",
    )
    assert h.session_key == "conv_1_2"


# ---------------------------------------------------------------------------
# 3. _safe_env filters secrets
# ---------------------------------------------------------------------------


def test_safe_env_filters_blocked_keys(monkeypatch):
    from backend.tools.sandbox.subprocess_provider import _safe_env, BLOCKED_ENV_PATTERNS

    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    monkeypatch.setenv("DATABASE_URI", "postgresql://u:pass@host/db")
    monkeypatch.setenv("MY_SAFE_VAR", "hello")
    monkeypatch.setenv("HOME", "/home/user")

    result = _safe_env()

    assert "OPENAI_API_KEY" not in result
    assert "DATABASE_URI" not in result
    assert result.get("MY_SAFE_VAR") == "hello"
    assert result.get("HOME") == "/home/user"


def test_safe_env_allows_extra_via_env_var(monkeypatch):
    from backend.tools.sandbox.subprocess_provider import _safe_env

    monkeypatch.setenv("MY_SECRET_KEY", "very-secret")
    monkeypatch.setenv("SANDBOX_SUBPROCESS_ALLOW_ENV", "MY_SECRET_KEY")

    result = _safe_env()
    # Even though name contains SECRET (which is in BLOCKED_ENV_PATTERNS),
    # explicit allow-list overrides the block.
    assert result.get("MY_SECRET_KEY") == "very-secret"


# ---------------------------------------------------------------------------
# 4. run_code honours max_output_chars and appends truncation marker
# ---------------------------------------------------------------------------


def test_run_code_truncation_marker():
    from backend.tools.sandbox.subprocess_provider import SubprocessProvider

    provider = SubprocessProvider()

    with tempfile.TemporaryDirectory() as tmpdir:
        handle = provider.create_sandbox(tmpdir, session_key="s")
        # Generate output that exceeds the tiny limit.
        code = "print('A' * 200)"
        output = provider.run_code(handle, code, max_output_chars=50)

    assert len(output) > 50  # includes the marker
    assert "[Output truncated at 50 characters]" in output


def test_run_code_no_truncation_when_within_limit():
    from backend.tools.sandbox.subprocess_provider import SubprocessProvider

    provider = SubprocessProvider()

    with tempfile.TemporaryDirectory() as tmpdir:
        handle = provider.create_sandbox(tmpdir)
        output = provider.run_code(handle, "print('hi')", max_output_chars=1000)

    assert "[Output truncated" not in output
    assert "hi" in output


# ---------------------------------------------------------------------------
# 5. run_code honours timeout param
# ---------------------------------------------------------------------------


def test_run_code_respects_timeout():
    from backend.tools.sandbox.subprocess_provider import SubprocessProvider

    provider = SubprocessProvider()

    with tempfile.TemporaryDirectory() as tmpdir:
        handle = provider.create_sandbox(tmpdir)
        output = provider.run_code(
            handle,
            "import time; time.sleep(5)",
            timeout=1,
        )

    assert "[Error]" in output
    assert "timed out" in output.lower()


# ---------------------------------------------------------------------------
# 6. run_code forwards on_stderr
# ---------------------------------------------------------------------------


def test_run_code_on_stderr_callback():
    from backend.tools.sandbox.subprocess_provider import SubprocessProvider

    provider = SubprocessProvider()
    stderr_lines: list[str] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        handle = provider.create_sandbox(tmpdir)
        # Streaming path is triggered when on_stdout or on_stderr is provided.
        provider.run_code(
            handle,
            "import sys; sys.stderr.write('err_line\\n')",
            on_stdout=lambda _: None,
            on_stderr=stderr_lines.append,
        )

    assert any("err_line" in line for line in stderr_lines)


def test_repl_tool_streams_stdout_from_provider_thread():
    from backend.tools.sandbox.provider import SandboxHandle
    from backend.tools.sandbox.tool_factory import create_sandbox_repl_tool

    events: list[dict] = []

    def run_code(_handle, _code, **kwargs):
        def emit_from_thread():
            kwargs["on_stdout"]("hello\n")
            kwargs["on_stderr"]("warn\n")

        thread = threading.Thread(target=emit_from_thread)
        thread.start()
        thread.join()
        return "done"

    handle = SandboxHandle(
        sandbox_id="sandbox-1",
        working_dir="/tmp",
        provider_name="test",
    )
    provider = MagicMock()
    provider.run_code.side_effect = run_code

    with patch(
        "backend.tools.sandbox.tool_factory.get_stream_writer",
        return_value=events.append,
    ):
        repl_tool = create_sandbox_repl_tool(handle, provider, "python")
        result = repl_tool.invoke({"code": "print('hello')"})

    assert result == "done"
    assert events == [
        {
            "type": "code_output",
            "tool_name": "python_repl",
            "stream": "stdout",
            "line": "hello\n",
        },
        {
            "type": "code_output",
            "tool_name": "python_repl",
            "stream": "stderr",
            "line": "warn\n",
        },
    ]


def test_repl_tool_marks_sandbox_session_active_while_running():
    from backend.tools.sandbox.provider import SandboxHandle
    from backend.tools.sandbox.tool_factory import create_sandbox_repl_tool

    handle = SandboxHandle(
        sandbox_id="sandbox-1",
        working_dir="/tmp",
        provider_name="test",
    )
    provider = MagicMock()
    provider.run_code.return_value = "done"
    session_service = MagicMock()
    session_service.begin_use.return_value = True

    repl_tool = create_sandbox_repl_tool(
        handle,
        provider,
        "python",
        session_key="conv_1_1",
        session_service=session_service,
    )
    result = repl_tool.invoke({"code": "print('hello')"})

    assert result == "done"
    session_service.begin_use.assert_called_once_with("conv_1_1")
    session_service.end_use.assert_called_once_with("conv_1_1")
    provider.run_code.assert_called_once()


# ---------------------------------------------------------------------------
# 7. list_files returns workspace-relative paths
# ---------------------------------------------------------------------------


def test_list_files_relative_paths():
    from backend.tools.sandbox.subprocess_provider import SubprocessProvider

    provider = SubprocessProvider()

    with tempfile.TemporaryDirectory() as tmpdir:
        handle = provider.create_sandbox(tmpdir)

        with open(os.path.join(tmpdir, "output.csv"), "w") as f:
            f.write("data")
        os.makedirs(os.path.join(tmpdir, "subdir"), exist_ok=True)
        with open(os.path.join(tmpdir, "subdir", "result.txt"), "w") as f:
            f.write("ok")

        files = provider.list_files(handle)

    assert "output.csv" in files
    assert os.path.join("subdir", "result.txt") in files


# ---------------------------------------------------------------------------
# 8. config exposes new settings
# ---------------------------------------------------------------------------


def test_config_new_sandbox_settings():
    import os
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
