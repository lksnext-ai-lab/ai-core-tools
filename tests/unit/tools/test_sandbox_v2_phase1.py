"""
Unit tests — sandbox v2 Phase 1 API contracts
==============================================

Validates the following RFC v2 / sandbox-v2-migration Phase 1 changes:

  1. ``SandboxExpiredError`` is importable from the provider module.
  2. ``SandboxHandle`` has ``session_key`` and ``active_skills`` fields.
  3. ``SubprocessProvider._safe_env`` filters secret-looking env vars.
  4. ``SubprocessProvider.run_code`` honours ``max_output_chars`` and appends
     the truncation marker.
  5. ``SubprocessProvider.run_code`` honours ``timeout`` param.
  6. ``SubprocessProvider.run_code`` forwards ``on_stderr`` lines.
  7. ``SubprocessProvider.list_files`` returns workspace-relative paths and
     excludes ``.skills/`` content.
  8. ``SubprocessProvider.ensure_skill`` returns a phaseful dict and stores it
     in ``handle.active_skills``; idempotent unless ``retry=True``.
  9. ``SubprocessProvider.list_active_skills`` returns a copy of
     ``handle.active_skills``.
  10. ``OpenSandboxProvider.list_active_skills`` returns ``handle.active_skills``.
  11. ``config`` module exposes the four new sandbox settings.
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
    assert h.active_skills == {}
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


# ---------------------------------------------------------------------------
# 7. list_files returns workspace-relative paths, excludes .skills/
# ---------------------------------------------------------------------------


def test_list_files_relative_paths_no_skills():
    from backend.tools.sandbox.subprocess_provider import SubprocessProvider

    provider = SubprocessProvider()

    with tempfile.TemporaryDirectory() as tmpdir:
        handle = provider.create_sandbox(tmpdir)

        # Create files: one normal, one inside .skills/
        os.makedirs(os.path.join(tmpdir, ".skills", "mypkg"), exist_ok=True)
        with open(os.path.join(tmpdir, "output.csv"), "w") as f:
            f.write("data")
        with open(os.path.join(tmpdir, ".skills", "mypkg", "setup.py"), "w") as f:
            f.write("# skill")
        os.makedirs(os.path.join(tmpdir, "subdir"), exist_ok=True)
        with open(os.path.join(tmpdir, "subdir", "result.txt"), "w") as f:
            f.write("ok")

        files = provider.list_files(handle)

    assert "output.csv" in files
    assert os.path.join("subdir", "result.txt") in files
    # .skills/ contents must be excluded
    assert not any(".skills" in f for f in files)


# ---------------------------------------------------------------------------
# 8. ensure_skill phaseful dict + idempotency
# ---------------------------------------------------------------------------


def test_ensure_skill_returns_phaseful_dict():
    from backend.tools.sandbox.subprocess_provider import SubprocessProvider

    provider = SubprocessProvider()
    skill = SimpleNamespace(name="my_skill", skill_id=42)

    with tempfile.TemporaryDirectory() as tmpdir:
        handle = provider.create_sandbox(tmpdir)
        state = provider.ensure_skill(handle, skill)

    assert state["skill_name"] == "my_skill"
    assert state["skill_id"] == 42
    assert "phases" in state
    assert "files" in state["phases"]
    assert "bootstrap" in state["phases"]
    assert handle.active_skills["my_skill"] == state


def test_ensure_skill_idempotent(monkeypatch):
    """Second call without retry=True returns the cached state."""
    from backend.tools.sandbox.subprocess_provider import SubprocessProvider

    provider = SubprocessProvider()
    skill = SimpleNamespace(name="idempotent_skill", skill_id=1)

    with tempfile.TemporaryDirectory() as tmpdir:
        handle = provider.create_sandbox(tmpdir)
        state1 = provider.ensure_skill(handle, skill)
        state2 = provider.ensure_skill(handle, skill)

    assert state1 is state2  # same object returned


def test_ensure_skill_retry_recomputes():
    """retry=True forces re-run of ensure_skill even if already active."""
    from backend.tools.sandbox.subprocess_provider import SubprocessProvider

    provider = SubprocessProvider()
    skill = SimpleNamespace(name="retry_skill", skill_id=2)

    with tempfile.TemporaryDirectory() as tmpdir:
        handle = provider.create_sandbox(tmpdir)
        state1 = provider.ensure_skill(handle, skill)
        state2 = provider.ensure_skill(handle, skill, retry=True)

    # Should produce equal content but be a different dict object
    assert state2["skill_name"] == "retry_skill"
    assert state1 is not state2


# ---------------------------------------------------------------------------
# 9. list_active_skills returns copy of active_skills
# ---------------------------------------------------------------------------


def test_list_active_skills_returns_copy():
    from backend.tools.sandbox.subprocess_provider import SubprocessProvider

    provider = SubprocessProvider()
    skill = SimpleNamespace(name="skill_a", skill_id=10)

    with tempfile.TemporaryDirectory() as tmpdir:
        handle = provider.create_sandbox(tmpdir)
        provider.ensure_skill(handle, skill)
        active = provider.list_active_skills(handle)

    assert "skill_a" in active
    # Mutating the returned dict must not affect the handle
    active["injected"] = {}
    assert "injected" not in handle.active_skills


# ---------------------------------------------------------------------------
# 10. OpenSandboxProvider.list_active_skills returns handle.active_skills
# ---------------------------------------------------------------------------


def test_opensandbox_list_active_skills():
    from backend.tools.sandbox.provider import SandboxHandle
    from backend.tools.sandbox.opensandbox_provider import OpenSandboxProvider

    provider = OpenSandboxProvider()
    handle = SandboxHandle(
        sandbox_id="x",
        working_dir="/tmp",
        provider_name="opensandbox",
        active_skills={"s1": {"skill_name": "s1"}},
    )
    active = provider.list_active_skills(handle)
    assert "s1" in active


# ---------------------------------------------------------------------------
# 11. config exposes new settings
# ---------------------------------------------------------------------------


def test_config_new_sandbox_settings():
    import config as settings

    assert hasattr(settings, "SANDBOX_MAX_OUTPUT_CHARS")
    assert hasattr(settings, "SANDBOX_MAX_EXECUTIONS_PER_TURN")
    assert hasattr(settings, "SANDBOX_RENEW_MINUTES")
    assert hasattr(settings, "SANDBOX_SKILL_BOOTSTRAP_TIMEOUT_S")

    assert isinstance(settings.SANDBOX_MAX_OUTPUT_CHARS, int)
    assert isinstance(settings.SANDBOX_MAX_EXECUTIONS_PER_TURN, int)
    assert isinstance(settings.SANDBOX_RENEW_MINUTES, int)
    assert isinstance(settings.SANDBOX_SKILL_BOOTSTRAP_TIMEOUT_S, int)

    assert settings.SANDBOX_MAX_OUTPUT_CHARS == 20000
    assert settings.SANDBOX_MAX_EXECUTIONS_PER_TURN == 5
    assert settings.SANDBOX_RENEW_MINUTES == 30
    assert settings.SANDBOX_SKILL_BOOTSTRAP_TIMEOUT_S == 60


def test_config_no_install_timeout():
    import config as settings

    assert not hasattr(settings, "SANDBOX_SKILL_INSTALL_TIMEOUT_S")
