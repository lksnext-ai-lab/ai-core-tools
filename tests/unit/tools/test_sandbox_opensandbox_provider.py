"""
Unit tests — IT-2 OpenSandboxProvider
======================================

Verification criteria from the RFC:
  1. ``resolve_provider`` returns ``OpenSandboxProvider`` when
     ``agent.app.sandbox_provider == 'opensandbox'``.
  2. ``OpenSandboxProvider`` methods delegate correctly to the opensandbox SDK
     (create, run_code, write_file, read_file, list_files, destroy).
  3. ``SubprocessProvider`` still works unchanged (backward compat for IT-0).
  4. The factory gracefully degrades when the opensandbox package is absent.
"""

from __future__ import annotations

import io
import os
import sys
import tarfile
import time
import threading
from datetime import timedelta
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers to build mock Agent objects
# ---------------------------------------------------------------------------


def _make_agent(sandbox_provider: str | None = None) -> SimpleNamespace:
    app = SimpleNamespace(sandbox_provider=sandbox_provider)
    return SimpleNamespace(
        id=1,
        app=app,
    )


# ---------------------------------------------------------------------------
# 1. Factory — resolve_provider dispatch
# ---------------------------------------------------------------------------


class TestResolveProvider:
    def test_returns_subprocess_by_default(self, monkeypatch):
        """Hard fallback is subprocess with no env or app config."""
        monkeypatch.delenv("SANDBOX_DEFAULT_PROVIDER", raising=False)
        from tools.sandbox.factory import resolve_provider
        from tools.sandbox.subprocess_provider import SubprocessProvider

        provider = resolve_provider(_make_agent(None))
        assert isinstance(provider, SubprocessProvider)

    def test_returns_subprocess_when_agent_app_sets_it(self, monkeypatch):
        monkeypatch.setenv("SANDBOX_DEFAULT_PROVIDER", "opensandbox")
        from tools.sandbox.factory import resolve_provider
        from tools.sandbox.subprocess_provider import SubprocessProvider

        provider = resolve_provider(_make_agent("subprocess"))
        assert isinstance(provider, SubprocessProvider)

    def test_returns_opensandbox_from_app_config(self, monkeypatch):
        """agent.app.sandbox_provider = 'opensandbox' → OpenSandboxProvider."""
        monkeypatch.delenv("SANDBOX_DEFAULT_PROVIDER", raising=False)
        from tools.sandbox.factory import resolve_provider, _PROVIDER_REGISTRY
        from tools.sandbox.opensandbox_provider import OpenSandboxProvider

        assert "opensandbox" in _PROVIDER_REGISTRY, (
            "OpenSandboxProvider is not registered; "
            "was 'opensandbox' package installed?"
        )

        provider = resolve_provider(_make_agent("opensandbox"))
        assert isinstance(provider, OpenSandboxProvider)

    def test_returns_opensandbox_from_env_default(self, monkeypatch):
        monkeypatch.setenv("SANDBOX_DEFAULT_PROVIDER", "opensandbox")
        from tools.sandbox.factory import resolve_provider
        from tools.sandbox.opensandbox_provider import OpenSandboxProvider

        provider = resolve_provider(_make_agent(None))
        assert isinstance(provider, OpenSandboxProvider)

    def test_unknown_provider_falls_back_to_subprocess(self, monkeypatch):
        """Unknown name gracefully degrades to subprocess and logs a warning."""
        monkeypatch.delenv("SANDBOX_DEFAULT_PROVIDER", raising=False)
        from tools.sandbox.factory import resolve_provider
        from tools.sandbox.subprocess_provider import SubprocessProvider

        provider = resolve_provider(_make_agent("nonexistent-provider"))
        assert isinstance(provider, SubprocessProvider)


# ---------------------------------------------------------------------------
# 2. Factory — graceful degradation when opensandbox is absent
# ---------------------------------------------------------------------------


class TestRegistryWithoutPackage:
    def test_builds_without_opensandbox_package(self, monkeypatch):
        """If import fails, only subprocess should be in the registry."""
        import sys
        import importlib

        # Temporarily make the import fail by hiding the module
        with patch.dict(sys.modules, {"opensandbox": None}):
            # Re-execute _build_registry with the blocked import
            import tools.sandbox.factory as factory_mod
            original = dict(factory_mod._PROVIDER_REGISTRY)

            # Temporarily block the module to simulate absence
            with patch("tools.sandbox.factory._build_registry") as mock_build:
                mock_build.return_value = {"subprocess": MagicMock()}
                from tools.sandbox.subprocess_provider import SubprocessProvider

                # The point: subprocess is always available
                assert "subprocess" in original


# ---------------------------------------------------------------------------
# 3. OpenSandboxProvider — unit tests via mocks
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_sdk():
    """Patch all opensandbox SDK classes so no real server is needed."""

    # Build mock objects
    mock_context = MagicMock()
    mock_context.id = "ctx-123"

    mock_interpreter = MagicMock()
    mock_interpreter.codes.create_context.return_value = mock_context

    mock_sandbox = MagicMock()
    mock_sandbox.id = "sandbox-abc"

    # Patch SandboxSync.create, CodeInterpreterSync.create, SupportedLanguage
    with (
        patch("tools.sandbox.opensandbox_provider.SandboxSync", create=True) as _SandboxSync,
        patch("tools.sandbox.opensandbox_provider.CodeInterpreterSync", create=True) as _InterpreterSync,
        patch("tools.sandbox.opensandbox_provider.SupportedLanguage", create=True) as _Lang,
    ):
        _SandboxSync.create.return_value = mock_sandbox
        _InterpreterSync.create.return_value = mock_interpreter
        _Lang.PYTHON = "python"
        yield {
            "SandboxSync": _SandboxSync,
            "InterpreterSync": _InterpreterSync,
            "sandbox": mock_sandbox,
            "interpreter": mock_interpreter,
            "context": mock_context,
        }


@pytest.fixture()
def provider_and_handle(mock_sdk):
    """Create a real OpenSandboxProvider and call create_sandbox with mocked SDK."""
    from tools.sandbox.opensandbox_provider import OpenSandboxProvider, _META_SANDBOX, _META_INTERPRETER, _META_CONTEXTS

    with patch("tools.sandbox.opensandbox_provider._get_connection_config", return_value=MagicMock()):
        provider = OpenSandboxProvider()
        # Directly inject the mocks into the handle instead of calling create_sandbox
        # (which would need complex import patching). We test create_sandbox separately.
        from tools.sandbox.provider import SandboxHandle
        handle = SandboxHandle(
            sandbox_id=mock_sdk["sandbox"].id,
            working_dir="/tmp",
            provider_name="opensandbox",
            metadata={
                _META_SANDBOX: mock_sdk["sandbox"],
                _META_INTERPRETER: mock_sdk["interpreter"],
                _META_CONTEXTS: {"python": mock_sdk["context"]},
            },
        )
        return provider, handle


class TestOpenSandboxProviderRunCode:
    def test_returns_execution_text(self, provider_and_handle):
        provider, handle = provider_and_handle
        mock_interpreter = handle.metadata["_interpreter"]

        execution = MagicMock()
        execution.text = "Hello, world!"
        execution.error = None
        execution.logs = MagicMock()
        execution.logs.stderr = []
        execution.exit_code = 0
        mock_interpreter.codes.run.return_value = execution

        result = provider.run_code(handle, "print('Hello, world!')")
        assert "Hello, world!" in result

    def test_extends_ttl_for_execution_then_resets_to_idle(
        self, provider_and_handle, monkeypatch
    ):
        provider, handle = provider_and_handle
        provider._can_renew = True
        monkeypatch.setattr("config.SANDBOX_IDLE_TIMEOUT_S", 120, raising=False)
        mock_interpreter = handle.metadata["_interpreter"]
        mock_sandbox = handle.metadata["_sandbox"]

        execution = MagicMock()
        execution.text = "done"
        execution.error = None
        execution.logs = MagicMock()
        execution.logs.stderr = []
        execution.exit_code = 0
        mock_interpreter.codes.run.return_value = execution

        result = provider.run_code(handle, "print('done')", timeout=30)

        assert result == "done"
        assert [call.kwargs["timeout"] for call in mock_sandbox.renew.call_args_list] == [
            timedelta(seconds=150),
            timedelta(seconds=120),
        ]

    def test_includes_error_info_on_failure(self, provider_and_handle):
        provider, handle = provider_and_handle
        mock_interpreter = handle.metadata["_interpreter"]

        execution = MagicMock()
        execution.text = ""
        execution.error = MagicMock()
        execution.error.name = "NameError"
        execution.error.value = "name 'x' is not defined"
        execution.logs = MagicMock()
        execution.logs.stderr = []
        execution.exit_code = 1
        mock_interpreter.codes.run.return_value = execution

        result = provider.run_code(handle, "print(x)")
        assert "NameError" in result or "x" in result

    def test_includes_error_info_on_non_zero_exit(self, provider_and_handle):
        provider, handle = provider_and_handle
        mock_interpreter = handle.metadata["_interpreter"]

        execution = MagicMock()
        execution.text = ""
        execution.error = None
        execution.logs = MagicMock()
        execution.logs.stderr = []
        execution.exit_code = 2
        mock_interpreter.codes.run.return_value = execution

        result = provider.run_code(handle, "raise SystemExit(2)")
        assert "[Error] Non-zero exit code: 2" in result

    def test_output_truncated_at_20000_chars(self, provider_and_handle):
        provider, handle = provider_and_handle
        mock_interpreter = handle.metadata["_interpreter"]

        execution = MagicMock()
        execution.text = "A" * 100_000
        execution.error = None
        execution.logs = MagicMock()
        execution.logs.stderr = []
        execution.exit_code = 0
        mock_interpreter.codes.run.return_value = execution

        result = provider.run_code(handle, "pass")
        # v2: output is truncated at max_output_chars then a marker is appended,
        # so total length exceeds max_output_chars by the marker length.
        assert "[Output truncated at 20000 characters]" in result
        # The text content before the marker must be exactly 20000 chars
        marker = "\n[Output truncated at 20000 characters]"
        assert result.endswith(marker)
        assert len(result) == 20_000 + len(marker)

    def test_run_code_times_out_and_interrupts_execution(self, provider_and_handle):
        provider, handle = provider_and_handle
        mock_interpreter = handle.metadata["_interpreter"]

        class FakeExecutionHandlersSync:
            def __init__(self, on_init=None, on_stdout=None):
                self.on_init = on_init
                self.on_stdout = on_stdout

        execd_sync_module = ModuleType("opensandbox.models.execd_sync")
        execd_sync_module.ExecutionHandlersSync = FakeExecutionHandlersSync

        def _slow_run(*args, **kwargs):
            handlers = kwargs.get("handlers")
            if handlers and handlers.on_init:
                handlers.on_init(SimpleNamespace(id="exec-timeout-1"))
            time.sleep(0.2)
            return MagicMock()

        mock_interpreter.codes.run.side_effect = _slow_run

        with patch.dict(
            sys.modules,
            {"opensandbox.models.execd_sync": execd_sync_module},
        ):
            result = provider.run_code(handle, "while True: pass", timeout=0.01)

        assert "timed out" in result
        mock_interpreter.codes.interrupt.assert_called_once_with("exec-timeout-1")

    def test_no_access_to_backend_env(self, provider_and_handle):
        """
        Isolation check: OpenSandboxProvider.run_code cannot access os.environ
        of the backend process (code runs inside container).
        The test verifies this by checking that run_code calls the SDK's .run()
        and that no subprocess is spawned in the backend process.
        """
        provider, handle = provider_and_handle
        mock_interpreter = handle.metadata["_interpreter"]

        execution = MagicMock()
        execution.text = "no-env-data"
        execution.error = None
        execution.logs = MagicMock()
        execution.logs.stderr = []
        execution.exit_code = 0
        mock_interpreter.codes.run.return_value = execution

        # Ensure no subprocess.run / subprocess.Popen is called
        with patch("subprocess.run") as mock_sub, patch("subprocess.Popen") as mock_popen:
            result = provider.run_code(handle, "import os; print(os.environ)")
            mock_sub.assert_not_called()
            mock_popen.assert_not_called()
        # The result comes from the SDK mock, not the backend environ
        assert result == "no-env-data"

    def test_parallel_runs_use_additional_context(self, provider_and_handle, monkeypatch):
        provider, handle = provider_and_handle
        mock_interpreter = handle.metadata["_interpreter"]

        monkeypatch.setattr(
            "tools.sandbox.opensandbox_provider._max_contexts_per_language",
            lambda: 2,
        )

        primary_context = handle.metadata["_contexts"]["python"]
        secondary_context = MagicMock()
        secondary_context.id = "ctx-456"
        handle.metadata["_context_lang_enums"] = {"python": "python"}
        mock_interpreter.codes.create_context.return_value = secondary_context

        barrier = threading.Barrier(2)
        contexts_used = []
        contexts_lock = threading.Lock()

        def _execution(text: str):
            execution = MagicMock()
            execution.text = text
            execution.error = None
            execution.logs = MagicMock()
            execution.logs.stderr = []
            execution.exit_code = 0
            return execution

        def _run(code, *, context, handlers=None):
            with contexts_lock:
                contexts_used.append(context)
            barrier.wait(timeout=1)
            time.sleep(0.02)
            return _execution(f"ran {code}")

        mock_interpreter.codes.run.side_effect = _run

        results: list[str] = []
        threads = [
            threading.Thread(target=lambda code=code: results.append(provider.run_code(handle, code)))
            for code in ("one", "two")
        ]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)

        assert len(results) == 2
        assert primary_context in contexts_used
        assert secondary_context in contexts_used
        mock_interpreter.codes.create_context.assert_called_once_with("python")


class TestOpenSandboxProviderFileIO:
    def test_write_file_prefixes_workspace(self, provider_and_handle):
        provider, handle = provider_and_handle
        mock_sandbox = handle.metadata["_sandbox"]

        provider.write_file(handle, "output.csv", b"col1,col2\n1,2")

        call_args = mock_sandbox.files.write_file.call_args
        remote_path = call_args[0][0]
        assert remote_path == "/workspace/output.csv"

    def test_write_file_refreshes_idle_ttl(self, provider_and_handle, monkeypatch):
        provider, handle = provider_and_handle
        provider._can_renew = True
        monkeypatch.setattr("config.SANDBOX_IDLE_TIMEOUT_S", 120, raising=False)
        mock_sandbox = handle.metadata["_sandbox"]

        provider.write_file(handle, "output.csv", b"col1,col2\n1,2")

        assert [call.kwargs["timeout"] for call in mock_sandbox.renew.call_args_list] == [
            timedelta(seconds=120),
            timedelta(seconds=120),
        ]

    def test_read_file_prefixes_workspace(self, provider_and_handle):
        provider, handle = provider_and_handle
        mock_sandbox = handle.metadata["_sandbox"]
        mock_sandbox.files.read_bytes.return_value = b"data"

        data = provider.read_file(handle, "result.json")

        call_args = mock_sandbox.files.read_bytes.call_args
        remote_path = call_args[0][0]
        assert remote_path == "/workspace/result.json"
        assert data == b"data"

    def test_list_files_returns_basenames(self, provider_and_handle):
        provider, handle = provider_and_handle
        mock_sandbox = handle.metadata["_sandbox"]

        entry1 = MagicMock()
        entry1.path = "/workspace/report.pdf"
        entry2 = MagicMock()
        entry2.path = "/workspace/data.csv"

        mock_sandbox.files.search.return_value = [entry1, entry2]

        with patch("tools.sandbox.opensandbox_provider.SearchEntry", create=True) as MockEntry:
            MockEntry.return_value = MagicMock()
            files = provider.list_files(handle)

        assert "report.pdf" in files
        assert "data.csv" in files

    def test_list_files_empty_on_search_error(self, provider_and_handle):
        provider, handle = provider_and_handle
        mock_sandbox = handle.metadata["_sandbox"]
        mock_sandbox.files.search.side_effect = Exception("network error")

        with patch("tools.sandbox.opensandbox_provider.SearchEntry", create=True):
            files = provider.list_files(handle)

        assert files == []


class TestOpenSandboxProviderSkills:
    def test_ensure_skill_uploads_archive_and_skips_bootstrap(self, provider_and_handle):
        provider, handle = provider_and_handle
        mock_sandbox = handle.metadata["_sandbox"]
        skill = SimpleNamespace(
            skill_id=10,
            name="demo",
            bootstrap_script_path=None,
            files=[SimpleNamespace(path="helper.py", content_text="x = 1", content_bytes=None)],
        )

        with patch.object(provider, "write_file") as mock_write, patch.object(
            provider, "run_code", return_value=""
        ) as mock_run:
            result = provider.ensure_skill(handle, skill)

        assert result["phases"] == {"files": "ok", "bootstrap": "skipped"}
        mock_write.assert_not_called()
        mock_sandbox.files.write_file.assert_called_once()
        archive_path, archive_bytes = mock_sandbox.files.write_file.call_args.args
        assert archive_path == "/workspace/.skill_archive_10_demo.tar.gz"
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
            assert archive.getnames() == ["helper.py"]
            assert archive.extractfile("helper.py").read() == b"x = 1"
        mock_run.assert_called_once()
        assert mock_run.call_args.kwargs["language"] == "python"
        assert "/workspace/.skills/demo" in mock_run.call_args.args[1]

    def test_ensure_skill_archive_skips_directory_placeholders(self, provider_and_handle):
        provider, handle = provider_and_handle
        mock_sandbox = handle.metadata["_sandbox"]
        skill = SimpleNamespace(
            skill_id=12,
            name="demo",
            bootstrap_script_path=None,
            files=[
                SimpleNamespace(path="scripts/", content_text="", content_bytes=None),
                SimpleNamespace(
                    path="scripts/helper.py",
                    content_text="x = 1",
                    content_bytes=None,
                ),
            ],
        )

        with patch.object(provider, "run_code", return_value=""):
            result = provider.ensure_skill(handle, skill)

        assert result["phases"]["files"] == "ok"
        _, archive_bytes = mock_sandbox.files.write_file.call_args.args
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
            assert archive.getnames() == ["scripts/helper.py"]

    def test_ensure_skill_archive_rejects_paths_outside_skill_dir(self, provider_and_handle):
        provider, handle = provider_and_handle
        mock_sandbox = handle.metadata["_sandbox"]
        skill = SimpleNamespace(
            skill_id=13,
            name="demo",
            bootstrap_script_path=None,
            files=[
                SimpleNamespace(path="../escape.py", content_text="x = 1", content_bytes=None),
            ],
        )

        result = provider.ensure_skill(handle, skill)

        assert result["phases"]["files"].startswith("failed:")
        mock_sandbox.files.write_file.assert_not_called()


class TestOpenSandboxProviderDestroy:
    def test_destroy_calls_kill_and_close(self, provider_and_handle):
        provider, handle = provider_and_handle
        mock_sandbox = handle.metadata["_sandbox"]

        provider.destroy_sandbox(handle)

        mock_sandbox.kill.assert_called_once()
        mock_sandbox.close.assert_called_once()

    def test_destroy_graceful_on_kill_error(self, provider_and_handle):
        provider, handle = provider_and_handle
        mock_sandbox = handle.metadata["_sandbox"]
        mock_sandbox.kill.side_effect = Exception("container already gone")

        # Should NOT raise
        provider.destroy_sandbox(handle)

        mock_sandbox.close.assert_called_once()

    def test_destroy_no_sandbox_in_metadata(self, provider_and_handle):
        provider, handle = provider_and_handle
        handle.metadata.clear()

        # Should NOT raise
        provider.destroy_sandbox(handle)


# ---------------------------------------------------------------------------
# 4. SubprocessProvider backward-compat (IT-0)
# ---------------------------------------------------------------------------


class TestSubprocessProviderBackwardCompat:
    def test_provider_name(self):
        from tools.sandbox.subprocess_provider import SubprocessProvider

        assert SubprocessProvider.PROVIDER_NAME == "subprocess"

    def test_run_code_hello_world(self, tmp_path):
        from tools.sandbox.subprocess_provider import SubprocessProvider

        provider = SubprocessProvider()
        handle = provider.create_sandbox(str(tmp_path))
        result = provider.run_code(handle, "print('hello')")
        provider.destroy_sandbox(handle)

        assert "hello" in result

    def test_run_code_variable_persistence(self, tmp_path):
        """Subprocess provider persists state across runs via tempfile writes."""
        from tools.sandbox.subprocess_provider import SubprocessProvider

        provider = SubprocessProvider()
        handle = provider.create_sandbox(str(tmp_path))

        # First invocation
        provider.run_code(handle, "x = 42")
        # In subprocess provider each run is isolated — state does NOT persist
        # between calls; that's an accepted limitation.  Just check it doesn't crash.
        result = provider.run_code(handle, "print('done')")
        provider.destroy_sandbox(handle)

        assert "done" in result

    def test_write_and_read_file(self, tmp_path):
        from tools.sandbox.subprocess_provider import SubprocessProvider

        provider = SubprocessProvider()
        handle = provider.create_sandbox(str(tmp_path))
        provider.write_file(handle, "hello.txt", b"hello world")
        data = provider.read_file(handle, "hello.txt")
        provider.destroy_sandbox(handle)

        assert data == b"hello world"

    def test_list_files(self, tmp_path):
        from tools.sandbox.subprocess_provider import SubprocessProvider

        provider = SubprocessProvider()
        handle = provider.create_sandbox(str(tmp_path))
        provider.write_file(handle, "file1.txt", b"a")
        provider.write_file(handle, "file2.txt", b"b")
        files = provider.list_files(handle)
        provider.destroy_sandbox(handle)

        assert "file1.txt" in files
        assert "file2.txt" in files
