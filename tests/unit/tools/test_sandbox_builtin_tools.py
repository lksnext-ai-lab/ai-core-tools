from __future__ import annotations

import json
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
        "Read",
        "Write",
        "Edit",
        "Glob",
        "Grep",
        "NotebookEdit",
        "Bash",
        "BashOutput",
        "KillShell",
    }


def test_file_search_and_edit_tools_operate_inside_sandbox(tmp_path, monkeypatch):
    tools, _handle = _make_tools(tmp_path, monkeypatch)
    target = tmp_path / "work" / "notes.txt"

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


def test_notebook_edit_replaces_and_inserts_cells(tmp_path, monkeypatch):
    tools, _handle = _make_tools(tmp_path, monkeypatch)
    notebook = tmp_path / "work" / "demo.ipynb"
    notebook.parent.mkdir(parents=True, exist_ok=True)
    notebook.write_text(
        json.dumps({
            "cells": [
                {
                    "cell_type": "markdown",
                    "id": "intro",
                    "metadata": {},
                    "source": ["old\n"],
                }
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5,
        }),
        encoding="utf-8",
    )

    replace_result = tools["NotebookEdit"].invoke({
        "notebook_path": str(notebook),
        "cell_id": "intro",
        "new_source": "new text\n",
    })
    assert "Replaced cell intro" in replace_result

    insert_result = tools["NotebookEdit"].invoke({
        "notebook_path": str(notebook),
        "cell_id": "intro",
        "new_source": "print('ok')\n",
        "cell_type": "code",
        "edit_mode": "insert",
    })
    assert "Inserted code cell" in insert_result

    data = json.loads(notebook.read_text(encoding="utf-8"))
    assert data["cells"][0]["source"] == ["new text\n"]
    assert data["cells"][1]["cell_type"] == "code"
    assert data["cells"][1]["source"] == ["print('ok')\n"]


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
