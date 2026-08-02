"""
Unit tests — IT-4 File Round-Trip
====================================

Verification criteria from the RFC:
  1. ``_prepare_turn`` binds a lazy sandbox handle when
     ``enable_code_interpreter`` is True, without creating the sandbox yet.
  2. For providers with ``requires_file_sync=True``, the first sandbox use
     pushes each processed_file into the sandbox via ``provider.write_file``.
  3. For providers with ``requires_file_sync=False``, no push/pull occurs
     (files already live directly on the shared local ``working_dir``).
  4. ``_finalize_turn`` pulls new remote output/ files (not in
     pre_existing_remote_files) into local output/ before ``sync_output_files``.
  5. Files outside ``output/`` are never pulled.
  6. Unsafe basenames (path traversal) are skipped during pull.
  7. Push/pull errors are logged but do not crash the turn.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from services.agent_execution_context import AgentExecutionContext
from services.agent_execution_service import AgentExecutionService
from tools.sandbox.provider import SandboxHandle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeProvider:
    """Minimal SandboxProvider test double exposing requires_file_sync.

    No remaining real provider has ``requires_file_sync=False`` (that was
    ``SubprocessProvider``'s distinguishing trait before it was removed), so
    this fake is used to exercise both branches of the capability-flag check
    directly.
    """

    PROVIDER_NAME = "fake"

    def __init__(self, requires_file_sync: bool = True):
        self.requires_file_sync = requires_file_sync
        self.create_sandbox = MagicMock()
        self.write_file = MagicMock()
        self.read_file = MagicMock(return_value=b"DATA")
        self.list_files = MagicMock(return_value=[])
        self.run_code = MagicMock(return_value="OK")
        self.get_supported_languages = MagicMock(return_value=[])


def _make_agent(enable_code_interpreter: bool = True, has_memory: bool = False):
    agent = MagicMock()
    agent.agent_id = 7
    agent.name = "TestAgent"
    agent.type = "agent"
    agent.has_memory = has_memory
    agent.silo_id = None
    agent.output_parser_id = None
    agent.request_count = 0
    agent.is_frozen = False
    agent.ai_service = None
    agent.enable_code_interpreter = enable_code_interpreter
    agent.skill_associations = []
    agent.prompt_template = MagicMock()
    agent.prompt_template.format.return_value = "msg"
    return agent


def _make_subprocess_handle(working_dir):
    from tools.sandbox.provider import SandboxHandle
    return SandboxHandle(
        sandbox_id="sub-001",
        working_dir=working_dir,
        provider_name="subprocess",
        metadata={},
    )


def _make_remote_handle(working_dir):
    from tools.sandbox.provider import SandboxHandle
    return SandboxHandle(
        sandbox_id="remote-001",
        working_dir=working_dir,
        provider_name="opensandbox",
        metadata={},
    )


def _make_service(agent, fresh_agent=None) -> AgentExecutionService:
    svc = AgentExecutionService.__new__(AgentExecutionService)
    svc.agent_service = MagicMock()
    svc.agent_service.get_agent.return_value = agent
    svc.session_service = MagicMock()
    svc.session_service.get_user_session = AsyncMock(return_value=None)
    svc.session_service.touch_session = AsyncMock()
    svc.agent_execution_repo = MagicMock()
    svc.agent_execution_repo.get_agent_with_relationships.return_value = (
        fresh_agent if fresh_agent is not None else agent
    )
    return svc


def _base_ctx(
    working_dir,
    provider_name="opensandbox",
    processed_files=None,
    remote_files_pre=None,
    provider=None,
):
    """Build a minimal context with sandbox fields populated.

    Pass an explicit ``provider`` (e.g. a ``_FakeProvider``) to control
    ``requires_file_sync``; otherwise a generic ``MagicMock`` is used, whose
    truthy ``requires_file_sync`` matches the real-world remote-provider path.
    """
    from tools.sandbox.provider import SandboxHandle

    handle = SandboxHandle(
        sandbox_id="s1",
        working_dir=working_dir,
        provider_name=provider_name,
        metadata={},
    )
    if provider is None:
        provider = MagicMock()
    return AgentExecutionContext(
        agent_id=7,
        agent=_make_agent(),
        fresh_agent=_make_agent(),
        enhanced_message="hello",
        image_files=[],
        working_dir=working_dir,
        pre_existing_files=set(),
        sandbox_handle=handle,
        sandbox_provider=provider,
        sandbox_session_key="conv_7_1",
        pre_existing_remote_files=remote_files_pre or set(),
        processed_files=processed_files or [],
        user_context={"user_id": "u1", "app_id": "1"},
    )


# ---------------------------------------------------------------------------
# 1. _prepare_turn binds a lazy sandbox without creating it
# ---------------------------------------------------------------------------


class TestPrepareTurnSandboxHandleCreation:
    def test_get_or_create_deferred_until_code_execution(self, tmp_path, monkeypatch):
        agent = _make_agent(enable_code_interpreter=True)
        svc = _make_service(agent)

        mock_handle = _make_subprocess_handle(str(tmp_path))
        mock_provider = MagicMock()
        mock_provider.create_sandbox.return_value = mock_handle
        mock_provider.PROVIDER_NAME = "subprocess"
        mock_provider.get_supported_languages.return_value = []
        mock_provider.run_code.return_value = "OK"

        mock_sss = MagicMock()
        mock_sss.get_or_create.return_value = mock_handle

        with (
            patch("services.agent_execution_service.get_app_config", return_value={"TMP_BASE_FOLDER": str(tmp_path)}),
            patch("services.agent_execution_service.AgentExecutionService._validate_agent_access", new=AsyncMock()),
            patch("tools.sandbox.factory.resolve_provider_and_service_id", return_value=(mock_provider, None)),
            patch("services.sandbox_session_service.sandbox_session_service", mock_sss),
        ):
            import asyncio
            ctx = asyncio.get_event_loop().run_until_complete(
                svc._prepare_turn(
                    agent_id=7,
                    message="run code",
                    file_references=[],
                    db=MagicMock(),
                    user_context={"user_id": "u1", "app_id": "1"},
                )
            )

            assert ctx.sandbox_handle is not None
            assert ctx.sandbox_provider is not None
            assert ctx.sandbox_session_key is not None
            mock_sss.get_or_create.assert_not_called()

            ctx.sandbox_provider.run_code(ctx.sandbox_handle, "print('hi')", language="python")
        mock_sss.get_or_create.assert_called_once()

    def test_resolved_sandbox_service_id_reaches_session_service(self, tmp_path, monkeypatch):
        """The SandboxService.service_id resolved for this agent must flow all
        the way through to SandboxSessionService.get_or_create() — this is
        what lets the cleanup/reaper paths later rebuild a provider with the
        *same* tenant credentials instead of falling back to zero-credential
        env defaults. A prior version of this wiring resolved the id via
        `resolve_provider()` (which discards it) instead of
        `resolve_provider_and_service_id()`, so the id was silently always
        None in production despite the session-service plumbing existing.
        """
        agent = _make_agent(enable_code_interpreter=True)
        svc = _make_service(agent)

        mock_handle = _make_subprocess_handle(str(tmp_path))
        mock_provider = MagicMock()
        mock_provider.create_sandbox.return_value = mock_handle
        mock_provider.PROVIDER_NAME = "opensandbox"
        mock_provider.get_supported_languages.return_value = []
        mock_provider.run_code.return_value = "OK"

        mock_sss = MagicMock()
        mock_sss.get_or_create.return_value = mock_handle

        with (
            patch("services.agent_execution_service.get_app_config", return_value={"TMP_BASE_FOLDER": str(tmp_path)}),
            patch("services.agent_execution_service.AgentExecutionService._validate_agent_access", new=AsyncMock()),
            patch(
                "tools.sandbox.factory.resolve_provider_and_service_id",
                return_value=(mock_provider, 42),
            ),
            patch("services.sandbox_session_service.sandbox_session_service", mock_sss),
        ):
            import asyncio
            ctx = asyncio.get_event_loop().run_until_complete(
                svc._prepare_turn(
                    agent_id=7,
                    message="run code",
                    file_references=[],
                    db=MagicMock(),
                    user_context={"user_id": "u1", "app_id": "1"},
                )
            )

            assert ctx.sandbox_handle.sandbox_service_id == 42

            ctx.sandbox_provider.run_code(ctx.sandbox_handle, "print('hi')", language="python")

        _, kwargs = mock_sss.get_or_create.call_args
        assert kwargs.get("sandbox_service_id") == 42

    def test_no_sandbox_when_code_interpreter_disabled(self, tmp_path, monkeypatch):
        agent = _make_agent(enable_code_interpreter=False)
        svc = _make_service(agent)

        mock_sss = MagicMock()

        with (
            patch("services.agent_execution_service.get_app_config", return_value={"TMP_BASE_FOLDER": str(tmp_path)}),
            patch("services.agent_execution_service.AgentExecutionService._validate_agent_access", new=AsyncMock()),
            patch("services.sandbox_session_service.sandbox_session_service", mock_sss),
        ):
            import asyncio
            ctx = asyncio.get_event_loop().run_until_complete(
                svc._prepare_turn(
                    agent_id=7,
                    message="hello",
                    file_references=[],
                    db=MagicMock(),
                    user_context={"user_id": "u1", "app_id": "1"},
                )
            )

        assert ctx.sandbox_handle is None
        mock_sss.get_or_create.assert_not_called()

    def test_prepare_turn_survives_unavailable_sandbox_provider(self, tmp_path):
        """`_prepare_turn` must not crash the whole turn when `resolve_provider`
        raises `SandboxProviderUnavailableError` (e.g. a misconfigured
        `SANDBOX_DEFAULT_PROVIDER`). It should degrade gracefully: the context
        is still returned, with the sandbox fields left unset.
        """
        from tools.sandbox.factory import SandboxProviderUnavailableError

        agent = _make_agent(enable_code_interpreter=True)
        svc = _make_service(agent)

        mock_sss = MagicMock()

        with (
            patch("services.agent_execution_service.get_app_config", return_value={"TMP_BASE_FOLDER": str(tmp_path)}),
            patch("services.agent_execution_service.AgentExecutionService._validate_agent_access", new=AsyncMock()),
            patch(
                "tools.sandbox.factory.resolve_provider_and_service_id",
                side_effect=SandboxProviderUnavailableError("provider 'bogus' not registered"),
            ),
            patch("services.sandbox_session_service.sandbox_session_service", mock_sss),
        ):
            import asyncio
            ctx = asyncio.get_event_loop().run_until_complete(
                svc._prepare_turn(
                    agent_id=7,
                    message="run code",
                    file_references=[],
                    db=MagicMock(),
                    user_context={"user_id": "u1", "app_id": "1"},
                )
            )

        assert ctx.sandbox_handle is None
        assert ctx.sandbox_provider is None
        assert ctx.sandbox_session_key is None
        mock_sss.get_or_create.assert_not_called()


# ---------------------------------------------------------------------------
# 2. File push — remote provider only
# ---------------------------------------------------------------------------


class TestPrepareTurnFilePush:
    """Push processed_files into non-subprocess sandbox on first use."""

    def test_writes_file_to_remote_sandbox(self, tmp_path):
        agent = _make_agent(enable_code_interpreter=True)
        svc = _make_service(agent)

        # Create a real temp file to push
        src = tmp_path / "data.xlsx"
        src.write_bytes(b"XLSX_CONTENT")

        mock_handle = _make_remote_handle(str(tmp_path))
        mock_provider = MagicMock()
        mock_provider.PROVIDER_NAME = "opensandbox"
        mock_provider.create_sandbox.return_value = mock_handle
        mock_provider.get_supported_languages.return_value = []
        mock_provider.list_files.return_value = []
        mock_provider.run_code.return_value = "OK"

        mock_sss = MagicMock()
        mock_sss.get_or_create.return_value = mock_handle
        # patch handle.provider_name (it's a dataclass field set in handle)

        # FileReference-like dict
        file_ref = MagicMock()
        file_ref.filename = "data.xlsx"
        file_ref.content = ""
        file_ref.file_type = "document"
        file_ref.file_id = "fid1"
        file_ref.file_path = str(src)

        with (
            patch("services.agent_execution_service.get_app_config", return_value={"TMP_BASE_FOLDER": str(tmp_path)}),
            patch("services.agent_execution_service.AgentExecutionService._validate_agent_access", new=AsyncMock()),
            patch("tools.sandbox.factory.resolve_provider_and_service_id", return_value=(mock_provider, None)),
            patch("services.sandbox_session_service.sandbox_session_service", mock_sss),
        ):
            import asyncio
            ctx = asyncio.get_event_loop().run_until_complete(
                svc._prepare_turn(
                    agent_id=7,
                    message="analyze",
                    file_references=[file_ref],
                    db=MagicMock(),
                    user_context={"user_id": "u1", "app_id": "1"},
                )
            )

            mock_provider.write_file.assert_not_called()

            ctx.sandbox_provider.run_code(ctx.sandbox_handle, "print('hi')", language="python")

        mock_provider.write_file.assert_called_once_with(
            mock_handle, "input/data.xlsx", b"XLSX_CONTENT"
        )

    def test_no_push_when_requires_file_sync_false(self, tmp_path):
        """Providers with requires_file_sync=False skip the remote push entirely
        (files already live directly on the shared local working_dir)."""
        agent = _make_agent(enable_code_interpreter=True)
        svc = _make_service(agent)

        src = tmp_path / "report.csv"
        src.write_bytes(b"CSV")

        fake_provider = _FakeProvider(requires_file_sync=False)
        handle = SandboxHandle(
            sandbox_id="local-001",
            working_dir=str(tmp_path),
            provider_name=_FakeProvider.PROVIDER_NAME,
            metadata={},
        )
        fake_provider.create_sandbox.return_value = handle

        mock_sss = MagicMock()
        mock_sss.get_or_create.return_value = handle

        file_ref = MagicMock()
        file_ref.filename = "report.csv"
        file_ref.content = "data"
        file_ref.file_type = "text"
        file_ref.file_id = "fid2"
        file_ref.file_path = str(src)

        with (
            patch("services.agent_execution_service.get_app_config", return_value={"TMP_BASE_FOLDER": str(tmp_path)}),
            patch("services.agent_execution_service.AgentExecutionService._validate_agent_access", new=AsyncMock()),
            patch("tools.sandbox.factory.resolve_provider_and_service_id", return_value=(fake_provider, None)),
            patch("services.sandbox_session_service.sandbox_session_service", mock_sss),
        ):
            import asyncio
            ctx = asyncio.get_event_loop().run_until_complete(
                svc._prepare_turn(
                    agent_id=7,
                    message="analyze",
                    file_references=[file_ref],
                    db=MagicMock(),
                    user_context={"user_id": "u1", "app_id": "1"},
                )
            )
            # Materialize the lazy handle to trigger the requires_file_sync check.
            ctx.sandbox_provider.run_code(ctx.sandbox_handle, "print('hi')", language="python")

        # requires_file_sync=False: no write_file called (files are in working_dir already)
        fake_provider.write_file.assert_not_called()
        assert os.path.exists(os.path.join(ctx.working_dir, "input", "report.csv"))

    def test_push_error_does_not_crash_turn(self, tmp_path):
        agent = _make_agent(enable_code_interpreter=True)
        svc = _make_service(agent)

        mock_handle = _make_remote_handle(str(tmp_path))
        mock_provider = MagicMock()
        mock_provider.PROVIDER_NAME = "opensandbox"
        mock_provider.create_sandbox.return_value = mock_handle
        mock_provider.get_supported_languages.return_value = []
        mock_provider.list_files.return_value = []
        mock_provider.write_file.side_effect = RuntimeError("network error")

        mock_sss = MagicMock()
        mock_sss.get_or_create.return_value = mock_handle

        file_ref = MagicMock()
        file_ref.filename = "file.txt"
        file_ref.content = "hello"
        file_ref.file_type = "text"
        file_ref.file_id = "fid3"
        file_ref.file_path = None  # no path — use content bytes

        with (
            patch("services.agent_execution_service.get_app_config", return_value={"TMP_BASE_FOLDER": str(tmp_path)}),
            patch("services.agent_execution_service.AgentExecutionService._validate_agent_access", new=AsyncMock()),
            patch("tools.sandbox.factory.resolve_provider_and_service_id", return_value=(mock_provider, None)),
            patch("services.sandbox_session_service.sandbox_session_service", mock_sss),
        ):
            import asyncio
            # Should not raise
            ctx = asyncio.get_event_loop().run_until_complete(
                svc._prepare_turn(
                    agent_id=7,
                    message="go",
                    file_references=[file_ref],
                    db=MagicMock(),
                    user_context={"user_id": "u1", "app_id": "1"},
                )
            )

            assert ctx.sandbox_handle is not None  # Turn still completes
            ctx.sandbox_provider.run_code(ctx.sandbox_handle, "print('hi')", language="python")


# ---------------------------------------------------------------------------
# 3. _finalize_turn — pull remote files into working_dir
# ---------------------------------------------------------------------------


def _run_finalize(ctx, tmp_path):
    svc = AgentExecutionService.__new__(AgentExecutionService)
    svc.agent_service = MagicMock()
    svc.session_service = MagicMock()
    svc.session_service.touch_session = AsyncMock()
    svc.agent_execution_repo = MagicMock()

    with (
        patch("services.agent_execution_service.FileManagementService") as MockFMS,
        patch("tools.agentTools.parse_agent_response", return_value="OK"),
        patch.object(svc, "_update_request_count"),
    ):
        mock_fms = MockFMS.return_value
        mock_fms.sync_output_files = AsyncMock(return_value=[])

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            svc._finalize_turn(ctx, "OK", MagicMock())
        )
    return result


class TestFinalizeTurnFilePull:
    """Pull new remote files into working_dir before sync_output_files."""

    def test_pulls_new_remote_file(self, tmp_path):
        ctx = _base_ctx(str(tmp_path), provider_name="opensandbox")
        ctx.sandbox_provider.list_files.return_value = ["/workspace/output/report.docx"]
        ctx.sandbox_provider.read_file.return_value = b"DOCX_BYTES"
        ctx.pre_existing_remote_files = set()

        _run_finalize(ctx, tmp_path)

        dest = tmp_path / "output" / "report.docx"
        assert dest.exists()
        assert dest.read_bytes() == b"DOCX_BYTES"

    def test_pulls_new_remote_file_from_bare_filename(self, tmp_path):
        ctx = _base_ctx(str(tmp_path), provider_name="opensandbox")
        ctx.sandbox_provider.list_files.return_value = ["output/report.docx"]
        ctx.sandbox_provider.read_file.return_value = b"DOCX_BYTES"
        ctx.pre_existing_remote_files = set()

        _run_finalize(ctx, tmp_path)

        dest = tmp_path / "output" / "report.docx"
        assert dest.exists()
        assert dest.read_bytes() == b"DOCX_BYTES"
        ctx.sandbox_provider.read_file.assert_called_once_with(
            ctx.sandbox_handle, "output/report.docx"
        )

    def test_pulls_new_remote_file_with_daytona_workspace_prefix(self, tmp_path):
        """Daytona's default sandbox user is `daytona`, so its absolute
        workspace root is /home/daytona/workspace — NOT /workspace or
        /home/user/workspace (confirmed against a live sandbox). Without
        this prefix recognized, a file the agent wrote to output/ is never
        detected as an output file, never pulled, and the model is left
        with no real download link to give the user."""
        ctx = _base_ctx(str(tmp_path), provider_name="daytona")
        ctx.sandbox_provider.list_files.return_value = [
            "/home/daytona/workspace/output/animal_names.csv"
        ]
        ctx.sandbox_provider.read_file.return_value = b"CSV_BYTES"
        ctx.pre_existing_remote_files = set()

        _run_finalize(ctx, tmp_path)

        dest = tmp_path / "output" / "animal_names.csv"
        assert dest.exists()
        assert dest.read_bytes() == b"CSV_BYTES"

    def test_skips_pre_existing_remote_file(self, tmp_path):
        ctx = _base_ctx(str(tmp_path), provider_name="opensandbox")
        ctx.sandbox_provider.list_files.return_value = ["/workspace/output/old.txt"]
        ctx.sandbox_provider.read_file.return_value = b"OLD"
        ctx.pre_existing_remote_files = {"output/old.txt"}

        _run_finalize(ctx, tmp_path)

        assert not (tmp_path / "output" / "old.txt").exists()

    def test_skips_non_output_workspace_resources(self, tmp_path):
        ctx = _base_ctx(str(tmp_path), provider_name="opensandbox")
        ctx.sandbox_provider.list_files.return_value = [
            "/workspace/work/scratch.tmp",
            "/workspace/work/package.json",
            "/workspace/output/output.xlsx",
        ]
        ctx.sandbox_provider.read_file.return_value = b"DATA"
        ctx.pre_existing_remote_files = set()

        _run_finalize(ctx, tmp_path)

        # Non-published (work/) resources skipped
        assert not (tmp_path / "output" / "scratch.tmp").exists()
        assert not (tmp_path / "output" / "package.json").exists()
        # Published output file pulled
        assert (tmp_path / "output" / "output.xlsx").exists()

    def test_skips_path_traversal_filenames(self, tmp_path):
        ctx = _base_ctx(str(tmp_path), provider_name="opensandbox")
        ctx.sandbox_provider.list_files.return_value = [
            # Normalizes to /etc/passwd — outside /workspace/
            "/workspace/../../../etc/passwd",
            # Hidden file inside /workspace/ — basename starts with .
            "/workspace/output/.hidden",
        ]
        ctx.sandbox_provider.read_file.return_value = b"EVIL"
        ctx.pre_existing_remote_files = set()

        _run_finalize(ctx, tmp_path)

        # read_file should never have been called for these unsafe paths
        ctx.sandbox_provider.read_file.assert_not_called()
        # No files written
        assert not (tmp_path / "output" / "passwd").exists()
        assert not (tmp_path / "output" / ".hidden").exists()

    def test_no_pull_when_requires_file_sync_false(self, tmp_path):
        """Providers with requires_file_sync=False skip the remote pull entirely
        (files already live directly on the shared local working_dir)."""
        fake_provider = _FakeProvider(requires_file_sync=False)
        fake_provider.list_files.return_value = ["report.docx"]
        fake_provider.read_file.return_value = b"DATA"
        ctx = _base_ctx(str(tmp_path), provider_name=_FakeProvider.PROVIDER_NAME, provider=fake_provider)

        _run_finalize(ctx, tmp_path)

        # requires_file_sync=False: list_files should NOT be called for pull
        fake_provider.list_files.assert_not_called()

    def test_no_pull_when_no_sandbox_handle(self, tmp_path):
        ctx = _base_ctx(str(tmp_path), provider_name="opensandbox")
        ctx.sandbox_handle = None  # No sandbox

        _run_finalize(ctx, tmp_path)

        ctx.sandbox_provider.list_files.assert_not_called()

    def test_pull_error_does_not_crash_turn(self, tmp_path):
        ctx = _base_ctx(str(tmp_path), provider_name="opensandbox")
        ctx.sandbox_provider.list_files.side_effect = RuntimeError("connection lost")

        # Should not raise
        _run_finalize(ctx, tmp_path)

    def test_read_file_error_skips_file_gracefully(self, tmp_path):
        ctx = _base_ctx(str(tmp_path), provider_name="opensandbox")
        ctx.sandbox_provider.list_files.return_value = [
            "/workspace/output/good.txt",
            "/workspace/output/bad.bin",
        ]
        ctx.sandbox_provider.read_file.side_effect = lambda handle, path: (
            b"GOOD" if "good" in path else (_ for _ in ()).throw(IOError("disk full"))
        )
        ctx.pre_existing_remote_files = set()

        _run_finalize(ctx, tmp_path)

        assert (tmp_path / "output" / "good.txt").exists()
        assert not (tmp_path / "output" / "bad.bin").exists()


# ---------------------------------------------------------------------------
# 4. requires_file_sync=True — the now-only-real-world path (push AND pull)
# ---------------------------------------------------------------------------


class TestRequiresFileSyncTruePath:
    """Explicitly cover the requires_file_sync=True path end-to-end.

    Every remaining real provider (OpenSandbox, Daytona, E2B) defaults to
    ``requires_file_sync=True``; this was previously only implicitly covered
    by the provider-specific ("opensandbox") tests above. This test exercises
    both the push (via ``_prepare_turn``) and pull (via ``_finalize_turn``)
    halves of the round trip against the same fake provider instance.
    """

    def test_push_and_pull_when_requires_file_sync_true(self, tmp_path):
        agent = _make_agent(enable_code_interpreter=True)
        svc = _make_service(agent)

        src = tmp_path / "data.xlsx"
        src.write_bytes(b"XLSX_CONTENT")

        fake_provider = _FakeProvider(requires_file_sync=True)
        handle = SandboxHandle(
            sandbox_id="remote-001",
            working_dir=str(tmp_path),
            provider_name=_FakeProvider.PROVIDER_NAME,
            metadata={},
        )
        fake_provider.create_sandbox.return_value = handle
        fake_provider.list_files.return_value = []

        mock_sss = MagicMock()
        mock_sss.get_or_create.return_value = handle

        file_ref = MagicMock()
        file_ref.filename = "data.xlsx"
        file_ref.content = ""
        file_ref.file_type = "document"
        file_ref.file_id = "fid1"
        file_ref.file_path = str(src)

        with (
            patch("services.agent_execution_service.get_app_config", return_value={"TMP_BASE_FOLDER": str(tmp_path)}),
            patch("services.agent_execution_service.AgentExecutionService._validate_agent_access", new=AsyncMock()),
            patch("tools.sandbox.factory.resolve_provider_and_service_id", return_value=(fake_provider, None)),
            patch("services.sandbox_session_service.sandbox_session_service", mock_sss),
        ):
            import asyncio
            ctx = asyncio.get_event_loop().run_until_complete(
                svc._prepare_turn(
                    agent_id=7,
                    message="analyze",
                    file_references=[file_ref],
                    db=MagicMock(),
                    user_context={"user_id": "u1", "app_id": "1"},
                )
            )

            fake_provider.write_file.assert_not_called()
            # Materialize the lazy handle to trigger the requires_file_sync push.
            ctx.sandbox_provider.run_code(ctx.sandbox_handle, "print('hi')", language="python")

        fake_provider.write_file.assert_called_once_with(
            handle, "input/data.xlsx", b"XLSX_CONTENT"
        )

        # Pull half: a new remote output file should be pulled into working_dir.
        fake_provider.list_files.return_value = ["/workspace/output/report.docx"]
        fake_provider.read_file.return_value = b"DOCX_BYTES"
        ctx.pre_existing_remote_files = set()

        _run_finalize(ctx, tmp_path)

        # Note: _prepare_turn computes its own working_dir under tmp_base
        # (e.g. persistent/<session_key>), distinct from the fixture's tmp_path.
        dest = Path(ctx.working_dir) / "output" / "report.docx"
        assert dest.exists()
        assert dest.read_bytes() == b"DOCX_BYTES"
