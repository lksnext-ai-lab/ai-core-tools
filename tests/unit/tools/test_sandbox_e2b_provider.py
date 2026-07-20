from __future__ import annotations

import io
import tarfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tools.sandbox.provider import SandboxExpiredError


def _make_sandbox(sandbox_id: str = "e2b-sbx") -> MagicMock:
    sandbox = MagicMock()
    sandbox.sandbox_id = sandbox_id
    sandbox.files = MagicMock()
    sandbox.commands = MagicMock()
    sandbox.create_code_context.return_value = SimpleNamespace(id="ctx-python")
    return sandbox


class TestE2BFactory:
    def test_registered_in_provider_registry(self):
        """``resolve_provider`` dispatch/precedence lives in
        ``test_sandbox_factory_resolution.py``; this only checks registration."""
        from tools.sandbox.e2b_provider import E2BProvider
        from tools.sandbox.factory import _PROVIDER_REGISTRY

        assert _PROVIDER_REGISTRY.get("e2b") is E2BProvider


class TestE2BCredentials:
    """Per-instance ``credentials`` override the ``E2B_*`` env vars."""

    def test_zero_arg_construction_uses_env_vars(self, monkeypatch, tmp_path):
        monkeypatch.setenv("E2B_TEMPLATE", "env-template")
        from tools.sandbox.e2b_provider import E2BProvider

        sandbox = _make_sandbox()
        mock_sdk = MagicMock()
        mock_sdk.create.return_value = sandbox
        monkeypatch.setattr("tools.sandbox.e2b_provider.E2BSandbox", mock_sdk)
        monkeypatch.setattr("config.SANDBOX_IDLE_TIMEOUT_S", 120, raising=False)
        monkeypatch.setattr("config.SANDBOX_CREATE_TIMEOUT_S", 60, raising=False)

        provider = E2BProvider()
        provider.create_sandbox(str(tmp_path))

        assert mock_sdk.create.call_args.kwargs["template"] == "env-template"
        assert mock_sdk.create.call_args.kwargs["api_key"] is None

    def test_credentials_override_env_vars(self, monkeypatch, tmp_path):
        monkeypatch.setenv("E2B_TEMPLATE", "env-template")
        from tools.sandbox.e2b_provider import E2BProvider

        sandbox = _make_sandbox()
        mock_sdk = MagicMock()
        mock_sdk.create.return_value = sandbox
        monkeypatch.setattr("tools.sandbox.e2b_provider.E2BSandbox", mock_sdk)
        monkeypatch.setattr("config.SANDBOX_IDLE_TIMEOUT_S", 120, raising=False)
        monkeypatch.setattr("config.SANDBOX_CREATE_TIMEOUT_S", 60, raising=False)

        provider = E2BProvider(
            credentials={"api_key": "service-api-key", "template": "service-template"}
        )
        provider.create_sandbox(str(tmp_path))

        assert mock_sdk.create.call_args.kwargs["template"] == "service-template"
        assert mock_sdk.create.call_args.kwargs["api_key"] == "service-api-key"


@pytest.fixture()
def provider_and_sandbox(monkeypatch):
    from tools.sandbox.e2b_provider import E2BProvider

    sandbox = _make_sandbox()
    sandbox.commands.run.return_value = SimpleNamespace(stdout="", stderr="", exit_code=0)
    mock_sdk = MagicMock()
    mock_sdk.create.return_value = sandbox
    mock_sdk.connect.return_value = sandbox
    monkeypatch.setattr("tools.sandbox.e2b_provider.E2BSandbox", mock_sdk)
    monkeypatch.setattr("config.SANDBOX_IDLE_TIMEOUT_S", 120, raising=False)
    monkeypatch.setattr("config.SANDBOX_CREATE_TIMEOUT_S", 60, raising=False)
    monkeypatch.setattr("config.SANDBOX_DEFAULT_TIMEOUT_S", 120, raising=False)

    provider = E2BProvider()
    return provider, mock_sdk, sandbox


class TestE2BLifecycle:
    def test_create_sandbox_uses_e2b_sdk_with_idle_timeout(self, provider_and_sandbox, tmp_path):
        provider, sdk, sandbox = provider_and_sandbox

        handle = provider.create_sandbox(str(tmp_path), session_key="conv_1_1")

        sdk.create.assert_called_once()
        assert sdk.create.call_args.kwargs["timeout"] == 120
        assert sdk.create.call_args.kwargs["metadata"]["session_key"] == "conv_1_1"
        sandbox.commands.run.assert_called_with(
            "mkdir -p /home/user/workspace",
            timeout=120,
            request_timeout=60,
        )
        assert handle.sandbox_id == "e2b-sbx"
        assert handle.provider_name == "e2b"

    def test_resume_uses_connect(self, provider_and_sandbox, tmp_path):
        provider, sdk, _ = provider_and_sandbox

        handle = provider.create_sandbox(
            str(tmp_path),
            existing_sandbox_id="existing",
            session_key="conv_1_1",
        )

        sdk.connect.assert_called_once_with("existing", timeout=120, request_timeout=60, api_key=None)
        sdk.create.assert_not_called()
        assert handle.sandbox_id == "e2b-sbx"

    def test_resume_failure_falls_back_to_create(self, provider_and_sandbox, tmp_path):
        provider, sdk, sandbox = provider_and_sandbox
        sdk.connect.side_effect = RuntimeError("gone")
        sdk.create.return_value = sandbox

        handle = provider.create_sandbox(str(tmp_path), existing_sandbox_id="old")

        sdk.create.assert_called_once()
        assert handle.sandbox_id == "e2b-sbx"

    def test_renew_sets_timeout_to_idle_timeout(self, provider_and_sandbox, tmp_path):
        provider, _, sandbox = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))

        provider.renew_sandbox(handle, MagicMock())

        sandbox.set_timeout.assert_called_once_with(120)

    def test_destroy_calls_kill(self, provider_and_sandbox, tmp_path):
        provider, _, sandbox = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))

        provider.destroy_sandbox(handle)

        sandbox.kill.assert_called_once()


class TestE2BRunCode:
    def test_python_uses_stateful_run_code(self, provider_and_sandbox, tmp_path):
        provider, _, sandbox = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))
        sandbox.run_code.return_value = SimpleNamespace(
            text="hello",
            results=[],
            logs=SimpleNamespace(stdout=[], stderr=[]),
            error=None,
        )

        result = provider.run_code(handle, "print('hello')", language="python")

        sandbox.run_code.assert_called_once()
        sandbox.create_code_context.assert_called_once_with(
            cwd="/home/user/workspace",
            language="python",
            request_timeout=60,
        )
        assert sandbox.run_code.call_args.kwargs["context"].id == "ctx-python"
        assert result == "hello"

    def test_python_extends_timeout_for_execution_then_resets_to_idle(
        self, provider_and_sandbox, tmp_path
    ):
        provider, _, sandbox = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))
        sandbox.run_code.return_value = SimpleNamespace(
            text="done",
            results=[],
            logs=SimpleNamespace(stdout=[], stderr=[]),
            error=None,
        )

        result = provider.run_code(handle, "print('done')", language="python", timeout=30)

        assert result == "done"
        assert [call.args[0] for call in sandbox.set_timeout.call_args_list] == [150, 120]

    def test_javascript_uses_stateful_run_code(self, provider_and_sandbox, tmp_path):
        provider, _, sandbox = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))
        sandbox.run_code.return_value = SimpleNamespace(
            text="hello-js",
            results=[],
            logs=SimpleNamespace(stdout=[], stderr=[]),
            error=None,
        )

        result = provider.run_code(handle, "console.log('hello-js')", language="javascript")

        assert result == "hello-js"
        sandbox.create_code_context.assert_called_once_with(
            cwd="/home/user/workspace",
            language="javascript",
            request_timeout=60,
        )
        assert sandbox.run_code.call_args.kwargs["context"].id == "ctx-python"

    def test_reuses_workspace_context_for_language(self, provider_and_sandbox, tmp_path):
        provider, _, sandbox = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))
        sandbox.run_code.return_value = SimpleNamespace(
            text="ok",
            results=[],
            logs=SimpleNamespace(stdout=[], stderr=[]),
            error=None,
        )

        provider.run_code(handle, "x = 1", language="python")
        provider.run_code(handle, "print(x)", language="python")

        sandbox.create_code_context.assert_called_once_with(
            cwd="/home/user/workspace",
            language="python",
            request_timeout=60,
        )

    def test_python_forwards_callbacks(self, provider_and_sandbox, tmp_path):
        provider, _, sandbox = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))
        sandbox.run_code.return_value = SimpleNamespace(
            text="",
            results=[],
            logs=SimpleNamespace(stdout=[], stderr=[]),
            error=None,
        )
        stdout_seen: list[str] = []
        stderr_seen: list[str] = []

        provider.run_code(
            handle,
            "print('x')",
            on_stdout=stdout_seen.append,
            on_stderr=stderr_seen.append,
        )

        stdout_cb = sandbox.run_code.call_args.kwargs["on_stdout"]
        stderr_cb = sandbox.run_code.call_args.kwargs["on_stderr"]
        stdout_cb(SimpleNamespace(text="out"))
        stderr_cb(SimpleNamespace(text="err"))
        assert stdout_seen == ["out"]
        assert stderr_seen == ["err"]

    def test_bash_uses_commands_run(self, provider_and_sandbox, tmp_path):
        provider, _, sandbox = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))
        sandbox.commands.run.return_value = SimpleNamespace(stdout="ok", stderr="", exit_code=0)

        result = provider.run_code(handle, "echo ok", language="bash")

        assert result == "ok"
        command = sandbox.commands.run.call_args.args[0]
        assert command.startswith("bash -lc ")
        assert sandbox.commands.run.call_args.kwargs["cwd"] == "/home/user/workspace"

    def test_bash_extends_timeout_for_execution_then_resets_to_idle(
        self, provider_and_sandbox, tmp_path
    ):
        provider, _, sandbox = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))
        sandbox.commands.run.return_value = SimpleNamespace(stdout="ok", stderr="", exit_code=0)

        provider.run_code(handle, "echo ok", language="bash", timeout=45)

        assert [call.args[0] for call in sandbox.set_timeout.call_args_list] == [165, 120]

    def test_output_truncates(self, provider_and_sandbox, tmp_path):
        provider, _, sandbox = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))
        sandbox.run_code.return_value = SimpleNamespace(
            text="A" * 100,
            results=[],
            logs=SimpleNamespace(stdout=[], stderr=[]),
            error=None,
        )

        result = provider.run_code(handle, "pass", max_output_chars=10)

        assert result.startswith("A" * 10)
        assert "[Output truncated at 10 characters]" in result

    def test_missing_sandbox_raises_expired(self, provider_and_sandbox, tmp_path):
        provider, _, _ = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))
        handle.metadata.clear()

        with pytest.raises(SandboxExpiredError):
            provider.run_code(handle, "pass")

    def test_sandbox_not_found_raises_expired(self, provider_and_sandbox, tmp_path):
        provider, _, sandbox = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))
        sandbox.set_timeout.side_effect = RuntimeError("Sandbox e2b-sbx not found")

        with pytest.raises(SandboxExpiredError):
            provider.run_code(handle, "pass")


class TestE2BFileIO:
    def test_write_file_writes_to_workspace(self, provider_and_sandbox, tmp_path):
        provider, _, sandbox = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))

        provider.write_file(handle, "nested/out.txt", b"data")

        sandbox.files.write.assert_called_once_with(
            "/home/user/workspace/nested/out.txt",
            b"data",
            request_timeout=120,
        )
        assert [call.args[0] for call in sandbox.set_timeout.call_args_list] == [120, 120]

    def test_read_file_reads_bytes_from_workspace(self, provider_and_sandbox, tmp_path):
        provider, _, sandbox = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))
        sandbox.files.read.return_value = bytearray(b"data")

        assert provider.read_file(handle, "out.txt") == b"data"
        sandbox.files.read.assert_called_once_with(
            "/home/user/workspace/out.txt",
            format="bytes",
            request_timeout=120,
        )

    def test_list_files_excludes_directories(self, provider_and_sandbox, tmp_path):
        provider, _, sandbox = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))
        sandbox.files.list.return_value = [
            SimpleNamespace(path="/home/user/workspace/report.pdf", type="file"),
            SimpleNamespace(path="/home/user/workspace/nested", type="dir"),
        ]

        assert provider.list_files(handle) == ["report.pdf"]
