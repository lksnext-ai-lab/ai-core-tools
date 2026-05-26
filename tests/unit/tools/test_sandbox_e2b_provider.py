from __future__ import annotations

import io
import tarfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tools.sandbox.provider import SandboxExpiredError


def _make_agent(sandbox_provider: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(id=1, app=SimpleNamespace(sandbox_provider=sandbox_provider))


def _make_sandbox(sandbox_id: str = "e2b-sbx") -> MagicMock:
    sandbox = MagicMock()
    sandbox.sandbox_id = sandbox_id
    sandbox.files = MagicMock()
    sandbox.commands = MagicMock()
    sandbox.create_code_context.return_value = SimpleNamespace(id="ctx-python")
    return sandbox


class TestE2BFactory:
    def test_returns_e2b_from_app_config(self, monkeypatch):
        monkeypatch.delenv("SANDBOX_DEFAULT_PROVIDER", raising=False)

        from tools.sandbox.e2b_provider import E2BProvider
        from tools.sandbox.factory import _PROVIDER_REGISTRY, resolve_provider

        assert "e2b" in _PROVIDER_REGISTRY
        assert isinstance(resolve_provider(_make_agent("e2b")), E2BProvider)


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
    monkeypatch.setattr("config.SANDBOX_SKILL_BOOTSTRAP_TIMEOUT_S", 120, raising=False)

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

        sdk.connect.assert_called_once_with("existing", timeout=120, request_timeout=60)
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

    def test_list_files_excludes_skills(self, provider_and_sandbox, tmp_path):
        provider, _, sandbox = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))
        sandbox.files.list.return_value = [
            SimpleNamespace(path="/home/user/workspace/report.pdf", type="file"),
            SimpleNamespace(path="/home/user/workspace/.skills/helper.py", type="file"),
            SimpleNamespace(path="/home/user/workspace/nested", type="dir"),
        ]

        assert provider.list_files(handle) == ["report.pdf"]


class TestE2BSkills:
    def test_ensure_skill_writes_files_and_skips_bootstrap(self, provider_and_sandbox, tmp_path):
        provider, _, sandbox = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))
        skill = SimpleNamespace(
            skill_id=10,
            name="demo",
            bootstrap_script_path=None,
            files=[SimpleNamespace(path="helper.py", content_text="x = 1", content_bytes=None)],
        )

        with patch.object(provider, "write_file") as mock_write:
            result = provider.ensure_skill(handle, skill)

        assert result["phases"] == {"files": "ok", "bootstrap": "skipped"}
        mock_write.assert_not_called()
        sandbox.files.write.assert_called_once()
        archive_path, archive_bytes = sandbox.files.write.call_args.args
        assert archive_path == "/home/user/workspace/.skills/.archives/10_demo.tar.gz"
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
            assert archive.getnames() == ["helper.py"]
            assert archive.extractfile("helper.py").read() == b"x = 1"
        sandbox.commands.run.assert_any_call(
            "mkdir -p /home/user/workspace/.skills/demo "
            "/home/user/workspace/.skills/.archives",
            timeout=120,
            request_timeout=60,
        )
        sandbox.commands.run.assert_any_call(
            "tar -xzf /home/user/workspace/.skills/.archives/10_demo.tar.gz "
            "-C /home/user/workspace/.skills/demo "
            "&& rm -f /home/user/workspace/.skills/.archives/10_demo.tar.gz",
            timeout=120,
            request_timeout=120,
        )

    def test_ensure_skill_archive_skips_directory_placeholders(
        self, provider_and_sandbox, tmp_path
    ):
        provider, _, sandbox = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))
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

        result = provider.ensure_skill(handle, skill)

        assert result["phases"]["files"] == "ok"
        _, archive_bytes = sandbox.files.write.call_args.args
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
            assert archive.getnames() == ["scripts/helper.py"]

    def test_ensure_skill_archive_rejects_paths_outside_skill_dir(
        self, provider_and_sandbox, tmp_path
    ):
        provider, _, sandbox = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))
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
        sandbox.files.write.assert_not_called()

    def test_ensure_skill_runs_bash_bootstrap(self, provider_and_sandbox, tmp_path):
        provider, _, _ = provider_and_sandbox
        handle = provider.create_sandbox(str(tmp_path))
        skill = SimpleNamespace(
            skill_id=11,
            name="demo",
            bootstrap_script_path="bootstrap.sh",
            files=[SimpleNamespace(path="bootstrap.sh", content_text="echo ok", content_bytes=None)],
        )

        with patch.object(
            provider, "run_code", return_value="__AICT_BOOTSTRAP_EXIT_CODE__=0"
        ) as mock_run:
            result = provider.ensure_skill(handle, skill)

        assert result["phases"]["bootstrap"] == "ok"
        assert mock_run.call_args.kwargs["language"] == "bash"
