from __future__ import annotations

import io
import tarfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tools.sandbox.provider import SandboxExpiredError


def _make_sandbox(sandbox_id: str = "daytona-sbx") -> MagicMock:
    sandbox = MagicMock()
    sandbox.id = sandbox_id
    sandbox.fs = MagicMock()
    sandbox.process = MagicMock()
    sandbox.code_interpreter = MagicMock()
    return sandbox


class TestDaytonaFactory:
    def test_registered_in_provider_registry(self):
        """``resolve_provider`` dispatch/precedence lives in
        ``test_sandbox_factory_resolution.py``; this only checks registration."""
        from tools.sandbox.daytona_provider import DaytonaProvider
        from tools.sandbox.factory import _PROVIDER_REGISTRY

        assert _PROVIDER_REGISTRY.get("daytona") is DaytonaProvider


class TestDaytonaCredentials:
    """Per-instance ``credentials`` override the ``DAYTONA_*`` env vars."""

    def test_zero_arg_construction_uses_env_vars(self, monkeypatch):
        monkeypatch.setenv("DAYTONA_API_KEY", "env-api-key")
        monkeypatch.setenv("DAYTONA_API_URL", "https://env.daytona.example/api")
        monkeypatch.setenv("DAYTONA_TARGET", "env-target")
        from tools.sandbox.daytona_provider import DaytonaProvider

        mock_config_cls = MagicMock()
        with monkeypatch.context() as m:
            m.setattr("tools.sandbox.daytona_provider.DaytonaConfig", mock_config_cls)
            m.setattr("tools.sandbox.daytona_provider.Daytona", MagicMock())
            provider = DaytonaProvider()
            provider._get_client()

        _, kwargs = mock_config_cls.call_args
        assert kwargs == {
            "api_key": "env-api-key",
            "api_url": "https://env.daytona.example/api",
            "target": "env-target",
        }

    def test_credentials_override_env_vars(self, monkeypatch):
        monkeypatch.setenv("DAYTONA_API_KEY", "env-api-key")
        monkeypatch.setenv("DAYTONA_API_URL", "https://env.daytona.example/api")
        monkeypatch.setenv("DAYTONA_TARGET", "env-target")
        from tools.sandbox.daytona_provider import DaytonaProvider

        mock_config_cls = MagicMock()
        with monkeypatch.context() as m:
            m.setattr("tools.sandbox.daytona_provider.DaytonaConfig", mock_config_cls)
            m.setattr("tools.sandbox.daytona_provider.Daytona", MagicMock())
            provider = DaytonaProvider(
                credentials={
                    "api_key": "service-api-key",
                    "api_url": "https://service.daytona.example/api",
                    "target": "service-target",
                }
            )
            provider._get_client()

        _, kwargs = mock_config_cls.call_args
        assert kwargs == {
            "api_key": "service-api-key",
            "api_url": "https://service.daytona.example/api",
            "target": "service-target",
        }


@pytest.fixture()
def provider_and_sandbox(monkeypatch):
    from tools.sandbox.daytona_provider import DaytonaProvider

    mock_client = MagicMock()
    sandbox = _make_sandbox()
    mock_client.create.return_value = sandbox
    mock_client.get.return_value = sandbox

    mock_daytona_class = MagicMock(return_value=mock_client)
    monkeypatch.setattr("tools.sandbox.daytona_provider.Daytona", mock_daytona_class)
    monkeypatch.setattr("tools.sandbox.daytona_provider.DaytonaConfig", MagicMock())

    provider = DaytonaProvider()
    return provider, mock_client, sandbox


class TestDaytonaLifecycle:
    def test_create_sandbox_params_are_ephemeral_and_auto_stop_after_two_minutes(
        self, provider_and_sandbox, monkeypatch, tmp_path
    ):
        provider, client, _ = provider_and_sandbox
        captured: dict = {}

        def _params(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(**kwargs)

        monkeypatch.setattr("tools.sandbox.daytona_provider.CreateSandboxFromSnapshotParams", _params)
        monkeypatch.setattr("config.SANDBOX_IDLE_TIMEOUT_S", 120, raising=False)
        monkeypatch.delenv("DAYTONA_AUTO_STOP_INTERVAL", raising=False)

        provider.create_sandbox(str(tmp_path))

        assert captured["ephemeral"] is True
        assert captured["auto_stop_interval"] == 2
        assert client.create.call_args.args[0].ephemeral is True

    def test_create_sandbox_uses_daytona_client(self, provider_and_sandbox, tmp_path):
        provider, client, sandbox = provider_and_sandbox

        handle = provider.create_sandbox(str(tmp_path), session_key="conv_1_1")

        client.create.assert_called_once()
        sandbox.fs.create_folder.assert_called_once_with("workspace", "755")
        assert handle.sandbox_id == "daytona-sbx"
        assert handle.provider_name == "daytona"
        assert handle.session_key == "conv_1_1"

    def test_resume_uses_client_get(self, provider_and_sandbox, tmp_path):
        provider, client, _ = provider_and_sandbox

        handle = provider.create_sandbox(
            str(tmp_path),
            session_key="conv_1_1",
            existing_sandbox_id="existing",
        )

        client.get.assert_called_once_with("existing")
        client.create.assert_not_called()
        assert handle.sandbox_id == "daytona-sbx"

    def test_resume_failure_falls_back_to_create(self, provider_and_sandbox, tmp_path):
        provider, client, sandbox = provider_and_sandbox
        client.get.side_effect = RuntimeError("gone")
        client.create.return_value = sandbox

        handle = provider.create_sandbox(str(tmp_path), existing_sandbox_id="old")

        client.create.assert_called_once()
        assert handle.sandbox_id == "daytona-sbx"

    def test_destroy_calls_client_delete(self, provider_and_sandbox, tmp_path):
        provider, client, _ = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))

        provider.destroy_sandbox(handle)

        client.delete.assert_called_once()


class TestDaytonaRunCode:
    def test_python_uses_stateful_code_interpreter(self, provider_and_sandbox, tmp_path):
        provider, _, sandbox = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))
        response = SimpleNamespace(result="hello", exit_code=0)
        sandbox.code_interpreter.run_code.return_value = response

        result = provider.run_code(handle, "print('hello')", language="python")

        sandbox.code_interpreter.run_code.assert_called_once()
        assert result == "hello"

    def test_python_chdirs_into_workspace_root_before_user_code(self, provider_and_sandbox, tmp_path):
        """Daytona's stateful Python interpreter has no `cwd` param and its own
        default cwd is the sandbox user's home directory — one level ABOVE
        the workspace root that _run_bash/write_file/read_file/list_files all
        use. Without an explicit chdir, a relative path like output/foo.csv
        (the convention every agent is instructed to use) lands outside the
        workspace root and is never seen by list_files()/read_file() again —
        confirmed live against a real Daytona sandbox."""
        provider, _, sandbox = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))
        sandbox.code_interpreter.run_code.return_value = SimpleNamespace(result="ok", exit_code=0)

        provider.run_code(handle, "print('hello')", language="python")

        sent_code = sandbox.code_interpreter.run_code.call_args.args[0]
        assert "chdir('workspace')" in sent_code
        assert sent_code.rstrip().endswith("print('hello')")

    def test_python_extends_auto_stop_for_execution_then_resets_to_idle(
        self, provider_and_sandbox, monkeypatch, tmp_path
    ):
        provider, _, sandbox = provider_and_sandbox
        monkeypatch.setattr("config.SANDBOX_IDLE_TIMEOUT_S", 120, raising=False)
        monkeypatch.delenv("DAYTONA_AUTO_STOP_INTERVAL", raising=False)
        handle = provider.create_sandbox(str(tmp_path))
        sandbox.code_interpreter.run_code.return_value = SimpleNamespace(result="done", exit_code=0)

        result = provider.run_code(handle, "print('done')", language="python", timeout=30)

        assert result == "done"
        assert [call.args[0] for call in sandbox.set_autostop_interval.call_args_list] == [3, 2]
        sandbox.fs.list_files.assert_called_with("workspace")

    def test_idle_reset_falls_back_to_process_touch_when_filesystem_touch_fails(
        self, provider_and_sandbox, monkeypatch, tmp_path
    ):
        provider, _, sandbox = provider_and_sandbox
        monkeypatch.setattr("config.SANDBOX_IDLE_TIMEOUT_S", 120, raising=False)
        monkeypatch.delenv("DAYTONA_AUTO_STOP_INTERVAL", raising=False)
        handle = provider.create_sandbox(str(tmp_path))
        sandbox.fs.list_files.side_effect = RuntimeError("fs unavailable")
        sandbox.process.exec.return_value = SimpleNamespace(result="", exit_code=0)
        sandbox.code_interpreter.run_code.return_value = SimpleNamespace(result="done", exit_code=0)

        result = provider.run_code(handle, "print('done')", language="python", timeout=30)

        assert result == "done"
        sandbox.process.exec.assert_called_once_with("true", cwd="workspace", timeout=1)

    def test_python_forwards_stdout_callback(self, provider_and_sandbox, tmp_path):
        provider, _, sandbox = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))
        sandbox.code_interpreter.run_code.return_value = SimpleNamespace(result="", exit_code=0)
        seen: list[str] = []

        provider.run_code(handle, "print('x')", on_stdout=seen.append)

        callback = sandbox.code_interpreter.run_code.call_args.kwargs["on_stdout"]
        callback(SimpleNamespace(output="streamed"))
        assert seen == ["streamed"]

    def test_bash_uses_process_exec(self, provider_and_sandbox, tmp_path):
        provider, _, sandbox = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))
        sandbox.process.exec.return_value = SimpleNamespace(result="ok", exit_code=0)

        result = provider.run_code(handle, "echo ok", language="bash")

        assert result == "ok"
        command = sandbox.process.exec.call_args.args[0]
        assert command.startswith("bash -lc ")
        assert sandbox.process.exec.call_args.kwargs["cwd"] == "workspace"

    def test_bash_extends_auto_stop_for_execution_then_resets_to_idle(
        self, provider_and_sandbox, monkeypatch, tmp_path
    ):
        provider, _, sandbox = provider_and_sandbox
        monkeypatch.setattr("config.SANDBOX_IDLE_TIMEOUT_S", 120, raising=False)
        monkeypatch.delenv("DAYTONA_AUTO_STOP_INTERVAL", raising=False)
        handle = provider.create_sandbox(str(tmp_path))
        sandbox.process.exec.return_value = SimpleNamespace(result="ok", exit_code=0)

        provider.run_code(handle, "echo ok", language="bash", timeout=45)

        assert [call.args[0] for call in sandbox.set_autostop_interval.call_args_list] == [3, 2]

    def test_output_truncates(self, provider_and_sandbox, tmp_path):
        provider, _, sandbox = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))
        sandbox.code_interpreter.run_code.return_value = SimpleNamespace(
            result="A" * 100,
            exit_code=0,
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


class TestDaytonaFileIO:
    def test_write_file_uploads_to_workspace(self, provider_and_sandbox, monkeypatch, tmp_path):
        provider, _, sandbox = provider_and_sandbox
        monkeypatch.setattr("config.SANDBOX_IDLE_TIMEOUT_S", 120, raising=False)
        monkeypatch.delenv("DAYTONA_AUTO_STOP_INTERVAL", raising=False)
        handle = provider.create_sandbox(str(tmp_path))

        provider.write_file(handle, "nested/out.txt", b"data")

        sandbox.process.exec.assert_any_call("mkdir -p workspace/nested")
        sandbox.fs.upload_file.assert_called_once_with(b"data", "workspace/nested/out.txt")
        assert [call.args[0] for call in sandbox.set_autostop_interval.call_args_list] == [2, 2]

    def test_read_file_downloads_from_workspace(self, provider_and_sandbox, tmp_path):
        provider, _, sandbox = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))
        sandbox.fs.download_file.return_value = b"data"

        assert provider.read_file(handle, "out.txt") == b"data"
        sandbox.fs.download_file.assert_called_once_with("workspace/out.txt")

    def test_list_files_uses_search_files(self, provider_and_sandbox, tmp_path):
        provider, _, sandbox = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))
        sandbox.fs.search_files.return_value = SimpleNamespace(
            files=["workspace/report.pdf", "workspace/data.csv"]
        )

        assert provider.list_files(handle) == ["data.csv", "report.pdf"]
