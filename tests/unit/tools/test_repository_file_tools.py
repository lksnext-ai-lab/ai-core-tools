"""Unit tests for ``tools.repository_file_tools`` (``get_repository_file``) and the sandbox staging it uses.

No DB: the repository listing is patched; the repository folder and the workspace are ``tmp_path`` dirs.
"""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from services.agent_execution_service import _LazySandboxHandle
from tools.repository_file_tools import (
    RepositoryFile,
    _match,
    create_repository_file_tool,
    repository_id_for_silo,
)

REPO_ID = 12

FILES = [
    RepositoryFile(resource_id=1, name="Plantilla acta", path="templates/acta.txt"),
    RepositoryFile(resource_id=2, name="notes.md", path="notes.md"),
    RepositoryFile(resource_id=3, name="dup.txt", path="a/dup.txt"),
    RepositoryFile(resource_id=4, name="dup.txt", path="b/dup.txt"),
]


@pytest.fixture
def env(tmp_path):
    repo_base = tmp_path / "repos"
    (repo_base / str(REPO_ID) / "templates").mkdir(parents=True)
    (repo_base / str(REPO_ID) / "templates" / "acta.txt").write_text("ACTA\nAsistentes: ___", encoding="utf-8")
    (repo_base / str(REPO_ID) / "notes.md").write_text("# notes", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    with patch("tools.repository_file_tools._list_repository_files", return_value=list(FILES)), \
         patch("services.repository_service.REPO_BASE_FOLDER", str(repo_base)):
        yield SimpleNamespace(repo_base=repo_base, work=work)


def _invoke(tool, **kwargs):
    return tool.invoke(kwargs)


# ── matching ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "12/templates/acta.txt",      # metadata `ref`
    "templates/acta.txt",          # repository path
    "/TEMPLATES/Acta.txt",         # case-insensitive path
    "acta.txt",                    # bare file name
    "Plantilla acta",              # resource display name
])
def test_match_resolves_one_file(query):
    found, candidates = _match(FILES, query, REPO_ID)
    assert found is FILES[0]
    assert candidates == []


def test_match_ambiguous_returns_candidates():
    found, candidates = _match(FILES, "dup.txt", REPO_ID)
    assert found is None
    assert {f.path for f in candidates} == {"a/dup.txt", "b/dup.txt"}


def test_match_full_path_disambiguates():
    found, _ = _match(FILES, "b/dup.txt", REPO_ID)
    assert found is FILES[3]


def test_match_unknown_and_empty():
    assert _match(FILES, "missing.docx", REPO_ID) == (None, [])
    assert _match(FILES, "   ", REPO_ID) == (None, [])


def test_repository_id_for_silo():
    assert repository_id_for_silo(None) is None
    assert repository_id_for_silo(SimpleNamespace(repository=[SimpleNamespace(repository_id=7)])) == 7
    assert repository_id_for_silo(SimpleNamespace(repository=SimpleNamespace(repository_id=8))) == 8
    assert repository_id_for_silo(SimpleNamespace(repository=[])) is None


# ── tool ─────────────────────────────────────────────────────────────────────

def test_default_destination_is_hidden_input_and_returns_text(env):
    tool = create_repository_file_tool(REPO_ID, str(env.work))

    result = _invoke(tool, file="12/templates/acta.txt")

    assert (env.work / "input" / "acta.txt").read_text(encoding="utf-8") == "ACTA\nAsistentes: ___"
    assert not (env.work / "output").exists()
    assert "input/acta.txt" in result
    assert "not shown to the user" in result
    assert "Asistentes: ___" in result


def test_output_destination_goes_to_output(env):
    tool = create_repository_file_tool(REPO_ID, str(env.work))

    result = _invoke(tool, file="notes.md", destination="output")

    assert (env.work / "output" / "notes.md").read_text(encoding="utf-8") == "# notes"
    assert not (env.work / "input").exists()
    assert "files panel" in result


def test_input_is_staged_on_sandbox(env):
    handle = MagicMock()
    handle.stage_input_file.return_value = True
    tool = create_repository_file_tool(REPO_ID, str(env.work), sandbox_handle=handle)

    result = _invoke(tool, file="acta.txt")

    handle.stage_input_file.assert_called_once_with("acta.txt", str(env.work / "input" / "acta.txt"))
    assert "Code interpreter path: input/acta.txt" in result


def test_output_is_not_staged_on_sandbox(env):
    handle = MagicMock()
    tool = create_repository_file_tool(REPO_ID, str(env.work), sandbox_handle=handle)

    _invoke(tool, file="acta.txt", destination="output")

    handle.stage_input_file.assert_not_called()


def test_not_found_lists_available_files(env):
    tool = create_repository_file_tool(REPO_ID, str(env.work))

    result = _invoke(tool, file="missing.docx")

    assert result.startswith("[Error] No file 'missing.docx'")
    assert "templates/acta.txt" in result


def test_ambiguous_name_is_an_error(env):
    tool = create_repository_file_tool(REPO_ID, str(env.work))

    result = _invoke(tool, file="dup.txt")

    assert "matches several files" in result
    assert "a/dup.txt" in result and "b/dup.txt" in result


def test_listed_but_missing_on_disk(env):
    tool = create_repository_file_tool(REPO_ID, str(env.work))

    result = _invoke(tool, file="a/dup.txt")

    assert "missing from storage" in result


def test_path_escaping_the_repository_is_refused(env):
    (env.repo_base / "secret.txt").write_text("nope", encoding="utf-8")
    evil = [RepositoryFile(resource_id=9, name="secret.txt", path="../secret.txt")]
    with patch("tools.repository_file_tools._list_repository_files", return_value=evil):
        tool = create_repository_file_tool(REPO_ID, str(env.work))
        result = _invoke(tool, file="../secret.txt")

    assert result == "[Error] The file could not be read."
    assert not (env.work / "input").exists()


def test_file_without_text_extraction_is_still_copied(env):
    (env.repo_base / str(REPO_ID) / "sheet.xlsx").write_bytes(b"PK\x03\x04")
    files = [RepositoryFile(resource_id=5, name="sheet.xlsx", path="sheet.xlsx")]
    with patch("tools.repository_file_tools._list_repository_files", return_value=files):
        tool = create_repository_file_tool(REPO_ID, str(env.work))
        result = _invoke(tool, file="sheet.xlsx")

    assert (env.work / "input" / "sheet.xlsx").read_bytes() == b"PK\x03\x04"
    assert "no text extraction" in result
    assert "--- Content" not in result


# ── _LazySandboxHandle.stage_input_file ─────────────────────────────────────

def _lazy(tmp_path, *, file_sync=True):
    provider = MagicMock(PROVIDER_NAME="fake", requires_file_sync=file_sync)
    return _LazySandboxHandle(session_key="s1", provider=provider, working_dir=str(tmp_path)), provider


def test_stage_before_sandbox_exists_only_queues(tmp_path):
    lazy, provider = _lazy(tmp_path)
    src = tmp_path / "a.txt"
    src.write_bytes(b"x")

    assert lazy.stage_input_file("a.txt", str(src)) is True

    provider.write_file.assert_not_called()
    assert lazy._staged_inputs == [("a.txt", str(src))]


def test_staged_file_is_pushed_when_workspace_is_prepared(tmp_path):
    lazy, provider = _lazy(tmp_path)
    provider.list_files.return_value = []
    src = tmp_path / "a.txt"
    src.write_bytes(b"data")
    lazy.stage_input_file("a.txt", str(src))
    lazy._handle = MagicMock()
    sss = MagicMock()

    lazy._prepare_remote_workspace(sss)

    provider.write_file.assert_any_call(lazy._handle, "input/a.txt", b"data")


def test_stage_after_prepare_pushes_now(tmp_path):
    lazy, provider = _lazy(tmp_path)
    lazy._handle = MagicMock()
    lazy._remote_inputs_prepared = True
    src = tmp_path / "a.txt"
    src.write_bytes(b"now")

    with patch("services.sandbox_session_service.sandbox_session_service") as sss:
        assert lazy.stage_input_file("a.txt", str(src)) is True

    sss.use.assert_called_once()
    provider.write_file.assert_called_once_with(lazy._handle, "input/a.txt", b"now")


def test_stage_on_local_provider_never_pushes(tmp_path):
    lazy, provider = _lazy(tmp_path, file_sync=False)
    lazy._handle = MagicMock()
    lazy._remote_inputs_prepared = True
    src = tmp_path / "a.txt"
    src.write_bytes(b"x")

    assert lazy.stage_input_file("a.txt", str(src)) is True
    provider.write_file.assert_not_called()


def test_restaging_same_name_replaces_entry(tmp_path):
    lazy, _ = _lazy(tmp_path)
    lazy.stage_input_file("a.txt", os.path.join(str(tmp_path), "one"))
    lazy.stage_input_file("a.txt", os.path.join(str(tmp_path), "two"))

    assert lazy._staged_inputs == [("a.txt", os.path.join(str(tmp_path), "two"))]


# ── build_repository_file_tool (when the tool is offered) ───────────────────

def _run(coro):
    import asyncio
    return asyncio.run(coro)


def test_tool_offered_for_a_repository_silo(tmp_path):
    from tools.repository_file_tools import TOOL_NAME, build_repository_file_tool

    agent = SimpleNamespace(agent_id=1, silo_id=3, silo=SimpleNamespace(repository=[SimpleNamespace(repository_id=REPO_ID)]))
    tool = _run(build_repository_file_tool(agent, str(tmp_path)))
    assert tool is not None and tool.name == TOOL_NAME


@pytest.mark.parametrize("agent", [
    SimpleNamespace(agent_id=1, silo_id=None, silo=None),                         # no silo
    SimpleNamespace(agent_id=1, silo_id=3, silo=SimpleNamespace(repository=[])),  # custom/domain silo
])
def test_tool_not_offered_without_a_repository(tmp_path, agent):
    from tools.repository_file_tools import build_repository_file_tool

    assert _run(build_repository_file_tool(agent, str(tmp_path))) is None


def test_tool_lookup_failure_degrades_to_no_tool(tmp_path):
    from tools.repository_file_tools import build_repository_file_tool

    class Broken:
        agent_id, silo_id = 1, 3

        @property
        def silo(self):
            raise RuntimeError("detached")

    assert _run(build_repository_file_tool(Broken(), str(tmp_path))) is None
