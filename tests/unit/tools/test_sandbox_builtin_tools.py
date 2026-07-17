from __future__ import annotations

import time


def _make_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("LANGSMITH_TRACING", "false")

    from tools.sandbox.builtin_tools import create_sandbox_builtin_tools
    from tools.sandbox.subprocess_provider import SubprocessProvider

    provider = SubprocessProvider()
    handle = provider.create_sandbox(str(tmp_path))
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
