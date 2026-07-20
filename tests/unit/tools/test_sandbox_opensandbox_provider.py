"""
Unit tests — IT-2 OpenSandboxProvider
======================================

Verification criteria from the RFC:
  1. ``OpenSandboxProvider`` methods delegate correctly to the opensandbox SDK
     (create, run_code, write_file, read_file, list_files, destroy).
  2. The factory gracefully degrades when the opensandbox package is absent.
  3. ``OpenSandboxProvider(credentials=...)`` overrides the equivalent
     ``OPENSANDBOX_*`` environment variables.

``resolve_provider`` dispatch/precedence coverage (agent-level and app-level
``SandboxService`` resolution, env-var fallback, unknown-provider errors)
lives in ``tests/unit/tools/test_sandbox_factory_resolution.py``.
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
# 2. Factory — graceful degradation when opensandbox is absent
# ---------------------------------------------------------------------------


class TestRegistryWithoutPackage:
    def test_builds_without_opensandbox_package(self):
        """If the opensandbox import fails, it is simply excluded from the
        registry (graceful degradation) rather than the whole factory failing."""
        import tools.sandbox.factory as factory_mod

        with patch.dict(sys.modules, {"tools.sandbox.opensandbox_provider": None}):
            registry = factory_mod._build_registry()

        assert "opensandbox" not in registry
        assert "subprocess" not in registry
        # Other providers are unaffected by opensandbox's absence.
        assert set(registry.keys()) <= {"daytona", "e2b"}


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


class TestOpenSandboxProviderCreate:
    def test_create_sandbox_falls_back_to_fresh_when_resume_fails(
        self,
        tmp_path,
        monkeypatch,
    ):
        import tools.sandbox.opensandbox_provider as provider_mod
        from tools.sandbox.opensandbox_provider import OpenSandboxProvider

        resume_calls: list[str] = []
        create_calls: list[tuple] = []
        fresh_sandbox = SimpleNamespace(id="sandbox-fresh")

        class FakeSandboxSync:
            @classmethod
            def resume(cls, sandbox_id, **kwargs):
                resume_calls.append(sandbox_id)
                raise RuntimeError("404 sandbox not found")

            @classmethod
            def create(cls, *args, **kwargs):
                create_calls.append((args, kwargs))
                return fresh_sandbox

        mock_context = MagicMock()
        mock_context.id = "ctx-fresh"
        mock_interpreter = MagicMock()
        mock_interpreter.codes.create_context.return_value = mock_context

        class FakeCodeInterpreterSync:
            @classmethod
            def create(cls, *, sandbox):
                assert sandbox is fresh_sandbox
                return mock_interpreter

        fake_code_interpreter_module = ModuleType("code_interpreter.sync.code_interpreter")
        fake_code_interpreter_module.CodeInterpreterSync = FakeCodeInterpreterSync
        fake_code_module = ModuleType("code_interpreter.models.code")
        fake_code_module.SupportedLanguage = SimpleNamespace(PYTHON="python")

        monkeypatch.setattr(provider_mod, "SandboxSync", FakeSandboxSync)
        monkeypatch.setattr(provider_mod, "_supported_languages", lambda: ["python"])

        with (
            patch.dict(
                sys.modules,
                {
                    "code_interpreter.sync.code_interpreter": fake_code_interpreter_module,
                    "code_interpreter.models.code": fake_code_module,
                },
            ),
            patch.object(provider_mod, "_get_connection_config", return_value=MagicMock()),
        ):
            provider = OpenSandboxProvider()
            handle = provider.create_sandbox(
                str(tmp_path),
                session_key="conv_1_1",
                existing_sandbox_id="sandbox-gone",
            )

        assert resume_calls == ["sandbox-gone"]
        assert create_calls
        assert handle.sandbox_id == "sandbox-fresh"
        assert handle.session_key == "conv_1_1"


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

    def test_destroy_by_id_prefers_static_kill(self, provider_and_handle):
        provider, _handle = provider_and_handle
        sandbox_sync = provider_and_handle[0].__class__.__module__

        with patch(f"{sandbox_sync}.SandboxSync", create=True) as MockSandboxSync:
            MockSandboxSync.kill = MagicMock()
            MockSandboxSync.resume = MagicMock()

            with patch.object(provider, "_get_config", return_value=MagicMock()):
                provider.destroy_sandbox_id("sandbox-abc")

            MockSandboxSync.kill.assert_called_once()
            MockSandboxSync.resume.assert_not_called()

    def test_destroy_by_id_falls_back_to_resume_when_static_kill_missing(
        self,
        provider_and_handle,
    ):
        provider, _handle = provider_and_handle
        sandbox_sync = provider_and_handle[0].__class__.__module__
        resumed = MagicMock()

        class LegacySandboxSync:
            @classmethod
            def resume(cls, *args, **kwargs):
                return resumed

        with (
            patch(f"{sandbox_sync}.SandboxSync", LegacySandboxSync),
            patch.object(provider, "_get_config", return_value=MagicMock()),
        ):
            provider.destroy_sandbox_id("sandbox-abc")

        resumed.kill.assert_called_once()
        resumed.close.assert_called_once()


class TestOpenSandboxProviderCredentials:
    """Per-instance ``credentials`` override the ``OPENSANDBOX_*`` env vars."""

    @staticmethod
    def _fake_connection_config_module():
        """Build a fake ``opensandbox.config.connection_sync`` module.

        ``_get_connection_config`` performs a local ``from
        opensandbox.config.connection_sync import ConnectionConfigSync``
        import — injecting a fake module via ``sys.modules`` lets these tests
        run without the real (optional, not installed in this environment)
        ``opensandbox`` package while still exercising the real provider code.
        """
        module = ModuleType("opensandbox.config.connection_sync")
        module.ConnectionConfigSync = MagicMock()
        return module

    def test_zero_arg_construction_uses_env_vars(self, monkeypatch):
        """Unchanged behaviour: no credentials → env vars used verbatim."""
        monkeypatch.setenv("OPENSANDBOX_DOMAIN", "env-domain:8080")
        monkeypatch.setenv("OPENSANDBOX_API_KEY", "env-api-key")
        from tools.sandbox.opensandbox_provider import OpenSandboxProvider

        fake_module = self._fake_connection_config_module()
        with patch.dict(sys.modules, {"opensandbox.config.connection_sync": fake_module}):
            provider = OpenSandboxProvider()
            provider._get_config()

        _, kwargs = fake_module.ConnectionConfigSync.call_args
        assert kwargs["domain"] == "env-domain:8080"
        assert kwargs["api_key"] == "env-api-key"

    def test_credentials_override_env_vars(self, monkeypatch):
        """``credentials`` passed to __init__ win over env vars for domain/api_key."""
        monkeypatch.setenv("OPENSANDBOX_DOMAIN", "env-domain:8080")
        monkeypatch.setenv("OPENSANDBOX_API_KEY", "env-api-key")
        from tools.sandbox.opensandbox_provider import OpenSandboxProvider

        fake_module = self._fake_connection_config_module()
        with patch.dict(sys.modules, {"opensandbox.config.connection_sync": fake_module}):
            provider = OpenSandboxProvider(
                credentials={"domain": "service-domain:9090", "api_key": "service-api-key"}
            )
            provider._get_config()

        _, kwargs = fake_module.ConnectionConfigSync.call_args
        assert kwargs["domain"] == "service-domain:9090"
        assert kwargs["api_key"] == "service-api-key"

    def test_credentials_image_overrides_env_var(self, monkeypatch):
        """``credentials["image"]`` wins over ``OPENSANDBOX_CODE_INTERPRETER_IMAGE``."""
        monkeypatch.setenv("OPENSANDBOX_CODE_INTERPRETER_IMAGE", "env/image:v1")
        from tools.sandbox.opensandbox_provider import _sandbox_image

        assert _sandbox_image({"image": "service/image:v2"}) == "service/image:v2"
        assert _sandbox_image(None) == "env/image:v1"
        assert _sandbox_image({}) == "env/image:v1"
