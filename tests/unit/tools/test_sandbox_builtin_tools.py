from __future__ import annotations

import subprocess
import time
from collections.abc import Callable


def _local_bash_run_code(
    handle,
    code: str,
    *,
    language: str = "python",
    timeout: int | None = None,
    max_output_chars: int | None = None,
    on_stdout: Callable[[str], None] | None = None,
    on_stderr: Callable[[str], None] | None = None,
) -> str:
    """Stand-in for the OpenSandbox SDK boundary used by builtin-tool tests.

    ``builtin_tools.py`` always invokes ``run_code`` with ``language="bash"``
    in blocking mode (no streaming callbacks). Rather than requiring a real
    OpenSandbox server, this fake executes the command locally against
    ``handle.working_dir`` — mirroring exactly what the removed
    ``SubprocessProvider`` used to do — so these tests exercise real file
    I/O without needing real sandbox infrastructure.
    """
    result = subprocess.run(
        ["bash", "-lc", code],
        capture_output=True,
        text=True,
        timeout=timeout or 30,
        cwd=handle.working_dir,
    )
    output = result.stdout or ""
    if result.stderr:
        output += f"\n[stderr]\n{result.stderr}"
    if max_output_chars is not None and len(output) > max_output_chars:
        output = output[:max_output_chars] + f"\n[Output truncated at {max_output_chars} characters]"
    return output


def _make_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("LANGSMITH_TRACING", "false")

    from tools.sandbox.builtin_tools import create_sandbox_builtin_tools
    from tools.sandbox.opensandbox_provider import OpenSandboxProvider

    provider = OpenSandboxProvider()
    # Mock the SDK boundary: run_code is replaced with a local bash executor
    # so tests don't need a real OpenSandbox server (create_sandbox is never
    # called here — builtin tools only need a handle carrying working_dir).
    monkeypatch.setattr(provider, "run_code", _local_bash_run_code)

    from tools.sandbox.provider import SandboxHandle
    import uuid as _uuid

    handle = SandboxHandle(
        sandbox_id=str(_uuid.uuid4()),
        working_dir=str(tmp_path),
        provider_name=provider.PROVIDER_NAME,
    )
    return {
        tool.name: tool
        for tool in create_sandbox_builtin_tools(handle, provider)
    }, handle


def test_create_sandbox_builtin_tools_exposes_claude_style_tools(tmp_path, monkeypatch):
    tools, _handle = _make_tools(tmp_path, monkeypatch)

    assert set(tools) == {
        "SandboxInfo",
        "PWD",
        "Read",
        "Write",
        "Edit",
        "LS",
        "Glob",
        "Grep",
        "Stat",
        "Bash",
        "BashOutput",
        "KillShell",
    }
    for tool in tools.values():
        assert "Sandbox-only operation" in tool.description


def test_file_search_and_edit_tools_operate_inside_sandbox(tmp_path, monkeypatch):
    tools, _handle = _make_tools(tmp_path, monkeypatch)
    target = tmp_path / "work" / "notes.txt"

    pwd_result = tools["PWD"].invoke({})
    assert pwd_result.strip() == str(tmp_path)

    sandbox_info = tools["SandboxInfo"].invoke({})
    assert "sandbox\tlinux" in sandbox_info
    assert f"cwd\t{tmp_path}" in sandbox_info
    assert "builtin_tools\tSandboxInfo, PWD, Read" in sandbox_info
    assert "Read\tdefault=2000_lines" in sandbox_info
    assert "provider" not in sandbox_info.lower()

    write_result = tools["Write"].invoke({
        "file_path": str(target),
        "content": "alpha\nbeta\nalphabet\n",
    })
    assert "Wrote" in write_result

    read_result = tools["Read"].invoke({
        "file_path": str(target),
        "offset": 2,
        "limit": 1,
    })
    assert "2\tbeta" in read_result

    edit_result = tools["Edit"].invoke({
        "file_path": str(target),
        "old_string": "beta",
        "new_string": "bravo",
    })
    assert "Replaced 1 occurrence" in edit_result

    grep_result = tools["Grep"].invoke({
        "pattern": "bravo",
        "path": str(tmp_path),
        "output_mode": "content",
        "-n": True,
    })
    assert "notes.txt" in grep_result
    assert "bravo" in grep_result

    glob_result = tools["Glob"].invoke({
        "pattern": "**/*.txt",
        "path": str(tmp_path),
    })
    assert str(target) in glob_result

    (target.parent / ".secret").write_text("hidden\n", encoding="utf-8")
    ls_result = tools["LS"].invoke({"path": str(target.parent)})
    assert f"f\t" in ls_result
    assert "notes.txt" in ls_result
    assert ".secret" not in ls_result

    stat_result = tools["Stat"].invoke({"path": str(target)})
    assert f"path\t{target}" in stat_result
    assert "type\tfile" in stat_result
    assert "size\t" in stat_result


def test_relative_path_error_tells_model_to_call_pwd_first(tmp_path, monkeypatch):
    """A relative path must not just be rejected — the absolute workspace
    root differs per provider (OpenSandbox mounts at /workspace, Daytona's
    default workspace lives relative to the sandbox user's home directory),
    so a bare rejection with no next step led models to guess several wrong
    absolute prefixes in a row instead of just calling PWD."""
    tools, _handle = _make_tools(tmp_path, monkeypatch)

    for tool_name, args in (
        ("Write", {"file_path": "output/animal_names.csv", "content": "x"}),
        ("Read", {"file_path": "output/animal_names.csv"}),
        ("Edit", {"file_path": "output/animal_names.csv", "old_string": "a", "new_string": "b"}),
    ):
        result = tools[tool_name].invoke(args)
        assert "must be absolute" in result
        assert "PWD" in result
        assert "guess" in result.lower()


def test_background_bash_output_and_kill(tmp_path, monkeypatch):
    tools, _handle = _make_tools(tmp_path, monkeypatch)

    start = tools["Bash"].invoke({
        "command": "printf 'ready\\n'; sleep 5; printf 'done\\n'",
        "run_in_background": True,
    })
    assert "Started background shell" in start
    shell_id = next(part for part in start.split() if part.startswith("bash-"))

    time.sleep(0.2)
    output = tools["BashOutput"].invoke({"bash_id": shell_id})
    assert "ready" in output
    assert "state=running" in output

    kill_result = tools["KillShell"].invoke({"shell_id": shell_id})
    assert "Killed background shell" in kill_result or "Shell is not running" in kill_result


def test_grep_schema_uses_claude_flag_aliases():
    from tools.sandbox.builtin_tools import GrepArgs

    properties = GrepArgs.model_json_schema(by_alias=True)["properties"]
    assert "-i" in properties
    assert "-n" in properties
    assert "-C" in properties


# ---------------------------------------------------------------------------
# SandboxExpiredError recovery (mid-turn expiry should never blow up the turn)
# ---------------------------------------------------------------------------


class _FakeSessionService:
    """Minimal stand-in for SandboxSessionService's evict/get_or_create pair."""

    def __init__(self, *, recreated_handle=None, fail_get_or_create=False):
        self.recreated_handle = recreated_handle
        self.fail_get_or_create = fail_get_or_create
        self.evict_calls: list[str] = []
        self.get_or_create_calls: list[tuple] = []

    def evict(self, session_key: str) -> None:
        self.evict_calls.append(session_key)

    def get_or_create(self, session_key: str, provider, working_dir: str):
        self.get_or_create_calls.append((session_key, provider, working_dir))
        if self.fail_get_or_create:
            raise RuntimeError("boom: cannot recreate sandbox")
        return self.recreated_handle


def _make_expiring_run_code(*, fail_times: int):
    """Return a run_code stand-in that raises SandboxExpiredError *fail_times*
    times before delegating to the local bash executor."""
    from tools.sandbox.provider import SandboxExpiredError

    calls = {"count": 0}

    def _run_code(handle, code: str, *, language: str = "bash", timeout=None,
                  max_output_chars=None, on_stdout=None, on_stderr=None) -> str:
        calls["count"] += 1
        if calls["count"] <= fail_times:
            raise SandboxExpiredError("sandbox is gone")
        return _local_bash_run_code(
            handle,
            code,
            language=language,
            timeout=timeout,
            max_output_chars=max_output_chars,
            on_stdout=on_stdout,
            on_stderr=on_stderr,
        )

    return _run_code, calls


def _make_provider_and_handle(tmp_path):
    from tools.sandbox.opensandbox_provider import OpenSandboxProvider
    from tools.sandbox.provider import SandboxHandle
    import uuid as _uuid

    provider = OpenSandboxProvider()
    handle = SandboxHandle(
        sandbox_id=str(_uuid.uuid4()),
        working_dir=str(tmp_path),
        provider_name=provider.PROVIDER_NAME,
    )
    return provider, handle


def test_builtin_tool_recovers_transparently_from_expired_sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("LANGSMITH_TRACING", "false")

    from tools.sandbox.builtin_tools import create_sandbox_builtin_tools
    from tools.sandbox.provider import SandboxHandle
    import uuid as _uuid

    provider, handle = _make_provider_and_handle(tmp_path)
    run_code, calls = _make_expiring_run_code(fail_times=1)
    monkeypatch.setattr(provider, "run_code", run_code)

    fresh_handle = SandboxHandle(
        sandbox_id=str(_uuid.uuid4()),
        working_dir=str(tmp_path),
        provider_name=provider.PROVIDER_NAME,
    )
    session_service = _FakeSessionService(recreated_handle=fresh_handle)

    tools = {
        tool.name: tool
        for tool in create_sandbox_builtin_tools(
            handle,
            provider,
            session_key="conv_1_1",
            session_service=session_service,
        )
    }

    result = tools["Bash"].invoke({"command": "echo hello"})

    assert "hello" in result
    assert "[Error]" not in result
    assert session_service.evict_calls == ["conv_1_1"]
    assert session_service.get_or_create_calls == [
        ("conv_1_1", provider, str(tmp_path))
    ]
    # Two run_code attempts: the expired one and the successful retry.
    assert calls["count"] == 2

    # The recovered handle should now be visible to every other tool too —
    # e.g. a subsequent Read call must not re-trigger recovery.
    write_result = tools["Write"].invoke({
        "file_path": str(tmp_path / "work" / "after_recovery.txt"),
        "content": "still alive\n",
    })
    assert "Wrote" in write_result
    # Write itself makes two run_code calls (existence check + the write
    # script); neither should hit expiry again since recovery already
    # happened above.
    assert calls["count"] == 4


def test_builtin_tool_returns_clean_error_when_no_session_service(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("LANGSMITH_TRACING", "false")

    from tools.sandbox.builtin_tools import create_sandbox_builtin_tools

    provider, handle = _make_provider_and_handle(tmp_path)
    run_code, calls = _make_expiring_run_code(fail_times=1)
    monkeypatch.setattr(provider, "run_code", run_code)

    # No session_key/session_service passed — recovery isn't possible.
    tools = {
        tool.name: tool
        for tool in create_sandbox_builtin_tools(handle, provider)
    }

    result = tools["Read"].invoke({"file_path": str(tmp_path / "missing.txt")})

    assert result == (
        "[Error] Sandbox session expired and was reset. "
        "Please retry the code execution."
    )
    assert calls["count"] == 1


def test_builtin_tool_returns_clean_error_when_recovery_also_expires(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("LANGSMITH_TRACING", "false")

    from tools.sandbox.builtin_tools import create_sandbox_builtin_tools

    provider, handle = _make_provider_and_handle(tmp_path)
    # Both the first attempt and the retried attempt raise SandboxExpiredError.
    run_code, calls = _make_expiring_run_code(fail_times=2)
    monkeypatch.setattr(provider, "run_code", run_code)

    session_service = _FakeSessionService(recreated_handle=handle)

    tools = {
        tool.name: tool
        for tool in create_sandbox_builtin_tools(
            handle,
            provider,
            session_key="conv_2_2",
            session_service=session_service,
        )
    }

    result = tools["PWD"].invoke({})

    assert result == (
        "[Error] Sandbox session expired and was reset. "
        "Please retry the code execution."
    )
    assert session_service.evict_calls == ["conv_2_2"]
    assert calls["count"] == 2


def test_builtin_tool_returns_clean_error_when_handle_recreation_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("LANGSMITH_TRACING", "false")

    from tools.sandbox.builtin_tools import create_sandbox_builtin_tools

    provider, handle = _make_provider_and_handle(tmp_path)
    run_code, calls = _make_expiring_run_code(fail_times=1)
    monkeypatch.setattr(provider, "run_code", run_code)

    session_service = _FakeSessionService(fail_get_or_create=True)

    tools = {
        tool.name: tool
        for tool in create_sandbox_builtin_tools(
            handle,
            provider,
            session_key="conv_3_3",
            session_service=session_service,
        )
    }

    result = tools["Stat"].invoke({"path": str(tmp_path)})

    assert result == (
        "[Error] Sandbox session expired and was reset. "
        "Please retry the code execution."
    )
    assert session_service.evict_calls == ["conv_3_3"]
    assert session_service.get_or_create_calls == [
        ("conv_3_3", provider, str(tmp_path))
    ]
    # Only the initial attempt runs — recreation failed, so no retry happens.
    assert calls["count"] == 1
