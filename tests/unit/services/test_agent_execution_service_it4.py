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

    def test_anon_sessions_are_scoped_per_caller_identity(self, tmp_path, monkeypatch):
        """Without a conversation_id (has_memory=False agents, public embeds,
        marketplace), the sandbox session key must be scoped by caller
        identity (user_id/app_id) — not collapse every caller for a given
        agent onto the same shared "anon_{agent_id}" session, which let
        unrelated users share one remote sandbox container/workspace."""
        agent = _make_agent(enable_code_interpreter=True)
        svc = _make_service(agent)

        mock_provider = MagicMock()
        mock_provider.PROVIDER_NAME = "opensandbox"
        mock_provider.get_supported_languages.return_value = []

        with (
            patch("services.agent_execution_service.get_app_config", return_value={"TMP_BASE_FOLDER": str(tmp_path)}),
            patch("services.agent_execution_service.AgentExecutionService._validate_agent_access", new=AsyncMock()),
            patch("tools.sandbox.factory.resolve_provider_and_service_id", return_value=(mock_provider, None)),
            patch("services.sandbox_session_service.sandbox_session_service", MagicMock()),
        ):
            import asyncio
            ctx_user_a = asyncio.get_event_loop().run_until_complete(
                svc._prepare_turn(
                    agent_id=7,
                    message="run code",
                    file_references=[],
                    db=MagicMock(),
                    user_context={"user_id": "user-a", "app_id": "1"},
                )
            )
            ctx_user_b = asyncio.get_event_loop().run_until_complete(
                svc._prepare_turn(
                    agent_id=7,
                    message="run code",
                    file_references=[],
                    db=MagicMock(),
                    user_context={"user_id": "user-b", "app_id": "1"},
                )
            )

        assert ctx_user_a.sandbox_session_key != "anon_7"
        assert ctx_user_b.sandbox_session_key != "anon_7"
        assert ctx_user_a.sandbox_session_key != ctx_user_b.sandbox_session_key

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


class TestLazySandboxHandleInvalidate:
    """`_LazySandboxHandle.invalidate()` must actually reset the proxy so a
    subsequent `get()` rebuilds a fresh sandbox, instead of leaving retries
    from tools/skill_tools.py's SandboxExpiredError handler doomed to fail
    forever against the same cached dead handle."""

    def test_invalidate_clears_cached_handle_and_evicts_session(self, tmp_path):
        from services.agent_execution_service import _LazySandboxHandle

        mock_provider = MagicMock()
        mock_provider.PROVIDER_NAME = "opensandbox"
        mock_provider.requires_file_sync = False

        lazy = _LazySandboxHandle(
            session_key="sk-expired",
            provider=mock_provider,
            working_dir=str(tmp_path),
        )

        stale_handle = SandboxHandle(
            sandbox_id="stale-001",
            working_dir=str(tmp_path),
            provider_name="opensandbox",
            metadata={},
        )
        fresh_handle = SandboxHandle(
            sandbox_id="fresh-002",
            working_dir=str(tmp_path),
            provider_name="opensandbox",
            metadata={},
        )

        mock_sss = MagicMock()
        mock_sss.get_or_create.side_effect = [stale_handle, fresh_handle]

        with patch("services.sandbox_session_service.sandbox_session_service", mock_sss):
            assert lazy.get() is stale_handle
            assert lazy.is_materialized()

            lazy.invalidate()

            assert not lazy.is_materialized()
            mock_sss.evict.assert_called_once_with("sk-expired")

            # The next get() must rebuild rather than return the stale handle.
            assert lazy.get() is fresh_handle

    def test_invalidate_is_safe_when_evict_raises(self, tmp_path):
        """An eviction failure must not crash the caller — degrade quietly so
        the SandboxExpiredError handler can still fall back to its no-retry
        message."""
        from services.agent_execution_service import _LazySandboxHandle

        mock_provider = MagicMock()
        mock_provider.PROVIDER_NAME = "opensandbox"

        lazy = _LazySandboxHandle(
            session_key="sk-expired",
            provider=mock_provider,
            working_dir=str(tmp_path),
        )

        mock_sss = MagicMock()
        mock_sss.evict.side_effect = RuntimeError("boom")

        with patch("services.sandbox_session_service.sandbox_session_service", mock_sss):
            lazy.invalidate()  # must not raise

        assert not lazy.is_materialized()


class TestLazySandboxProviderEnsureSkill:
    """H2 fix (fix round 1): ``_LazySandboxProvider.ensure_skill`` is the
    actual production delegate that populates ``_active_skill_registry`` on
    the real ``tools/skill_tools.py`` call path (``handle.provider.ensure_skill(...)``,
    where ``handle`` is a ``_LazySandboxProvider``) — every existing test
    called either the raw ``SandboxProvider.ensure_skill`` ABC default or
    ``_reactivate_previous_skills`` directly, so this delegate itself had
    zero coverage: deleting it entirely would have left the whole suite
    green. This builds a REAL ``_LazySandboxProvider`` wrapping a fake raw
    provider and a real ``_LazySandboxHandle``, and calls
    ``lazy_provider.ensure_skill(lazy_handle, payload)`` exactly like the
    real call site does."""

    def _make_lazy_and_provider(self, tmp_path, raw_provider, session_key="sk-h2"):
        from services.agent_execution_service import _LazySandboxHandle, _LazySandboxProvider

        lazy_handle = _LazySandboxHandle(
            session_key=session_key,
            provider=raw_provider,
            working_dir=str(tmp_path),
        )
        lazy_provider = _LazySandboxProvider(raw_provider, lazy_handle)
        return lazy_handle, lazy_provider

    def test_delegate_resolves_handle_and_records_registry_from_payload_not_result(self, tmp_path):
        """(a) the raw provider receives the RESOLVED SandboxHandle, never the lazy
        proxy. (b) the registry is populated from the PAYLOAD's (name, skill_id) —
        not from whatever the result object claims (defense-in-depth: the result
        below deliberately lies with a different skill_id). (e) the session lease
        uses the skill-bootstrap budget, not the ~30s default used elsewhere."""
        from services.agent_execution_service import _skill_bootstrap_budget_seconds
        from tools.sandbox.provider import SandboxHandle, SkillActivationResult, SkillPhaseResult

        real_handle = SandboxHandle(
            sandbox_id="real-001", working_dir=str(tmp_path), provider_name="opensandbox", metadata={},
        )
        raw_provider = MagicMock()
        raw_provider.PROVIDER_NAME = "opensandbox"
        raw_provider.requires_file_sync = False
        # Deliberately a DIFFERENT skill_id than the payload — proves the
        # registry is derived from the payload, never trusted from the result.
        raw_provider.ensure_skill.return_value = SkillActivationResult(
            skill_name="alpha",
            skill_id=999,
            files_dir="/x/alpha",
            phases=(SkillPhaseResult(phase="files", status="ok", detail="materialised", duration_ms=1),),
            status="active",
        )

        mock_sss = MagicMock()
        mock_sss.get_or_create.return_value = real_handle

        lazy_handle, lazy_provider = self._make_lazy_and_provider(tmp_path, raw_provider)
        payload = SimpleNamespace(name="alpha", skill_id=1)

        with patch("services.sandbox_session_service.sandbox_session_service", mock_sss):
            result = lazy_provider.ensure_skill(lazy_handle, payload)

        assert result.status == "active"

        raw_provider.ensure_skill.assert_called_once()
        called_handle = raw_provider.ensure_skill.call_args.args[0]
        assert called_handle is real_handle, "raw provider must receive the resolved SandboxHandle, not the lazy proxy"

        assert dict(lazy_handle._snapshot_active_skills()) == {"alpha": 1}

        mock_sss.use.assert_called_once()
        assert mock_sss.use.call_args.kwargs["expected_seconds"] == _skill_bootstrap_budget_seconds()
        assert _skill_bootstrap_budget_seconds() != 30

    def test_stale_reactivation_failure_is_cleared_on_success(self, tmp_path):
        """(c) a stale reactivation failure recorded for this exact skill name
        must not survive a subsequent genuine success through this delegate."""
        from tools.sandbox.provider import SandboxHandle, SkillActivationResult, SkillPhaseResult

        real_handle = SandboxHandle(
            sandbox_id="real-002", working_dir=str(tmp_path), provider_name="opensandbox", metadata={},
        )
        raw_provider = MagicMock()
        raw_provider.PROVIDER_NAME = "opensandbox"
        raw_provider.requires_file_sync = False
        raw_provider.ensure_skill.return_value = SkillActivationResult(
            skill_name="alpha",
            skill_id=1,
            files_dir="/x/alpha",
            phases=(SkillPhaseResult(phase="files", status="ok", detail="materialised", duration_ms=1),),
            status="active",
        )

        mock_sss = MagicMock()
        mock_sss.get_or_create.return_value = real_handle

        lazy_handle, lazy_provider = self._make_lazy_and_provider(tmp_path, raw_provider)
        lazy_handle._record_reactivation_failure("alpha", "stale failure from an earlier recreation")
        payload = SimpleNamespace(name="alpha", skill_id=1)

        with patch("services.sandbox_session_service.sandbox_session_service", mock_sss):
            lazy_provider.ensure_skill(lazy_handle, payload)

        assert "alpha" not in lazy_handle.skill_reactivation_errors

    def test_failed_result_records_nothing_into_registry(self, tmp_path):
        """(d) a status="failed" result must not populate the registry at all —
        a name collision (OQ-4) or any other terminal failure is never treated
        as "this session now has this skill active"."""
        from tools.sandbox.provider import SandboxHandle, SkillActivationResult, SkillPhaseResult

        real_handle = SandboxHandle(
            sandbox_id="real-003", working_dir=str(tmp_path), provider_name="opensandbox", metadata={},
        )
        raw_provider = MagicMock()
        raw_provider.PROVIDER_NAME = "opensandbox"
        raw_provider.requires_file_sync = False
        raw_provider.ensure_skill.return_value = SkillActivationResult(
            skill_name="alpha",
            skill_id=1,
            files_dir="/x/alpha",
            phases=(SkillPhaseResult(phase="files", status="failed", detail="name collision", duration_ms=1),),
            status="failed",
        )

        mock_sss = MagicMock()
        mock_sss.get_or_create.return_value = real_handle

        lazy_handle, lazy_provider = self._make_lazy_and_provider(tmp_path, raw_provider)
        payload = SimpleNamespace(name="alpha", skill_id=1)

        with patch("services.sandbox_session_service.sandbox_session_service", mock_sss):
            result = lazy_provider.ensure_skill(lazy_handle, payload)

        assert result.status == "failed"
        assert lazy_handle._snapshot_active_skills() == []


class TestReactivatePreviousSkills:
    """step_020 fix round 3 (H1/H2) — regression tests pinning:

    1. A status="failed" reactivation result forgets the skill from the
       registry AND records the failure (F1 — never silently cleared).
    2. A SandboxExpiredError raised mid-loop propagates (raise, not break) so
       get()'s handler can fully invalidate the proxy instead of caching a
       confirmed-dead handle.
    3. After that SandboxExpiredError recovery, the NEXT get() call correctly
       re-pushes input files — i.e. invalidate() (not a manual
       `self._handle = None`) genuinely reset `_remote_inputs_prepared`.
    """

    def _make_lazy(self, tmp_path, provider, processed_files=None):
        from services.agent_execution_service import _LazySandboxHandle

        return _LazySandboxHandle(
            session_key="sk-reactivate",
            provider=provider,
            working_dir=str(tmp_path),
            processed_files=processed_files or [],
        )

    def test_failed_reactivation_forgets_skill_and_records_failure(self, tmp_path):
        from services.agent_execution_service import _reactivate_previous_skills
        from tools.sandbox.provider import SkillActivationResult, SkillPhaseResult

        mock_provider = MagicMock()
        mock_provider.PROVIDER_NAME = "opensandbox"
        lazy = self._make_lazy(tmp_path, mock_provider)
        lazy._record_active_skill("alpha", 1)

        failed_result = SkillActivationResult(
            skill_name="alpha",
            skill_id=1,
            files_dir="/x",
            phases=(
                SkillPhaseResult(phase="files", status="failed", detail="name collision", duration_ms=1),
            ),
            status="failed",
        )
        raw_provider = MagicMock()
        raw_provider.ensure_skill.return_value = failed_result

        real_handle = MagicMock()

        with patch("services.sandbox_session_service.sandbox_session_service", MagicMock()):
            _reactivate_previous_skills(
                lazy,
                raw_provider,
                lambda skill_id: SimpleNamespace(name="alpha", skill_id=skill_id),
                real_handle,
            )

        assert lazy._snapshot_active_skills() == []
        assert lazy.skill_reactivation_errors.get("alpha") == "files: name collision"

    @pytest.mark.parametrize("bogus_status", [None, "bogus", "", 42])
    def test_malformed_status_is_treated_conservatively_as_failure(self, tmp_path, bogus_status):
        """LOW fix (fix round 1): an unrecognised/malformed ``status`` value
        (not literally ``"failed"``, but not a recognised success value
        either) must hit the SAME conservative "treat as failure" branch as
        the literal ``"failed"`` case — never silently treated as success."""
        from services.agent_execution_service import _reactivate_previous_skills
        from tools.sandbox.provider import SkillActivationResult, SkillPhaseResult

        mock_provider = MagicMock()
        mock_provider.PROVIDER_NAME = "opensandbox"
        lazy = self._make_lazy(tmp_path, mock_provider)
        lazy._record_active_skill("alpha", 1)

        malformed_result = SkillActivationResult(
            skill_name="alpha",
            skill_id=1,
            files_dir="/x",
            phases=(SkillPhaseResult(phase="files", status="ok", detail="materialised", duration_ms=1),),
            status=bogus_status,
        )
        raw_provider = MagicMock()
        raw_provider.ensure_skill.return_value = malformed_result

        real_handle = MagicMock()

        with patch("services.sandbox_session_service.sandbox_session_service", MagicMock()):
            _reactivate_previous_skills(
                lazy,
                raw_provider,
                lambda skill_id: SimpleNamespace(name="alpha", skill_id=skill_id),
                real_handle,
            )

        assert lazy._snapshot_active_skills() == []
        assert "alpha" in lazy.skill_reactivation_errors
        assert f"unexpected activation status: {bogus_status!r}" in lazy.skill_reactivation_errors["alpha"]

    def test_degraded_result_clears_a_previously_recorded_reactivation_failure(self, tmp_path):
        """LOW fix (fix round 1): a stale reactivation failure must be cleared
        not just by a fresh "active" result, but by "degraded" too — degraded
        is still a usable outcome (files land, bootstrap failed), not a
        reason to keep surfacing an unrelated older failure."""
        from services.agent_execution_service import _reactivate_previous_skills
        from tools.sandbox.provider import SkillActivationResult, SkillPhaseResult

        mock_provider = MagicMock()
        mock_provider.PROVIDER_NAME = "opensandbox"
        lazy = self._make_lazy(tmp_path, mock_provider)
        lazy._record_active_skill("alpha", 1)
        lazy._record_reactivation_failure("alpha", "stale failure from an earlier recreation")

        degraded_result = SkillActivationResult(
            skill_name="alpha",
            skill_id=1,
            files_dir="/x",
            phases=(
                SkillPhaseResult(phase="files", status="ok", detail="materialised", duration_ms=1),
                SkillPhaseResult(phase="bootstrap", status="failed", detail="pip install failed", duration_ms=1),
            ),
            status="degraded",
        )
        raw_provider = MagicMock()
        raw_provider.ensure_skill.return_value = degraded_result

        real_handle = MagicMock()

        with patch("services.sandbox_session_service.sandbox_session_service", MagicMock()):
            _reactivate_previous_skills(
                lazy,
                raw_provider,
                lambda skill_id: SimpleNamespace(name="alpha", skill_id=skill_id),
                real_handle,
            )

        assert "alpha" not in lazy.skill_reactivation_errors
        assert dict(lazy._snapshot_active_skills()) == {"alpha": 1}

    def test_sandbox_expired_mid_loop_propagates_instead_of_swallowed(self, tmp_path):
        """H2: the previous round's `break` silently swallowed the exception,
        defeating recovery. It must now `raise`."""
        from services.agent_execution_service import _reactivate_previous_skills
        from tools.sandbox.provider import SandboxExpiredError

        mock_provider = MagicMock()
        mock_provider.PROVIDER_NAME = "opensandbox"
        lazy = self._make_lazy(tmp_path, mock_provider)
        lazy._record_active_skill("alpha", 1)

        raw_provider = MagicMock()
        raw_provider.ensure_skill.side_effect = SandboxExpiredError("sandbox gone")

        real_handle = MagicMock()

        with patch("services.sandbox_session_service.sandbox_session_service", MagicMock()):
            with pytest.raises(SandboxExpiredError):
                _reactivate_previous_skills(
                    lazy,
                    raw_provider,
                    lambda skill_id: SimpleNamespace(name="alpha", skill_id=skill_id),
                    real_handle,
                )

        # The specific per-skill failure must have been recorded before the raise.
        assert lazy.skill_reactivation_errors.get("alpha") == "sandbox gone"

    def test_get_invalidates_fully_when_skills_loader_raises_sandbox_expired(self, tmp_path):
        """H1: get()'s SandboxExpiredError handler must call invalidate() (not a
        manual `self._handle = None`), so _remote_inputs_prepared and
        _remote_pre_existing_files are reset too, and the session is evicted."""
        from services.agent_execution_service import _LazySandboxHandle
        from tools.sandbox.provider import SandboxExpiredError, SandboxHandle

        mock_provider = MagicMock()
        mock_provider.PROVIDER_NAME = "opensandbox"
        mock_provider.requires_file_sync = True
        mock_provider.list_files.return_value = []

        stale_handle = SandboxHandle(
            sandbox_id="stale-001", working_dir=str(tmp_path), provider_name="opensandbox", metadata={},
        )

        lazy = self._make_lazy(tmp_path, mock_provider)

        def _raising_loader(real_handle):
            raise SandboxExpiredError("sandbox gone mid re-activation")

        lazy._skills_loader = _raising_loader

        mock_sss = MagicMock()
        mock_sss.get_or_create.return_value = stale_handle

        with patch("services.sandbox_session_service.sandbox_session_service", mock_sss):
            with pytest.raises(SandboxExpiredError):
                lazy.get()

        assert not lazy.is_materialized()
        assert lazy._remote_inputs_prepared is False
        assert lazy._remote_pre_existing_files == set()
        mock_sss.evict.assert_called_once_with("sk-reactivate")

    def test_next_get_after_expiry_recovery_re_pushes_input_files(self, tmp_path):
        """After a SandboxExpiredError-triggered invalidate(), the following
        get() call must recreate the remote workspace AND re-push input files
        — i.e. _prepare_remote_workspace must not early-return because
        _remote_inputs_prepared was left stale True."""
        from services.agent_execution_service import _LazySandboxHandle
        from tools.sandbox.provider import SandboxExpiredError, SandboxHandle

        src = tmp_path / "notes.txt"
        src.write_bytes(b"NOTES")

        mock_provider = MagicMock()
        mock_provider.PROVIDER_NAME = "opensandbox"
        mock_provider.requires_file_sync = True
        mock_provider.list_files.return_value = []

        stale_handle = SandboxHandle(
            sandbox_id="stale-001", working_dir=str(tmp_path), provider_name="opensandbox", metadata={},
        )
        fresh_handle = SandboxHandle(
            sandbox_id="fresh-002", working_dir=str(tmp_path), provider_name="opensandbox", metadata={},
        )

        lazy = self._make_lazy(
            tmp_path,
            mock_provider,
            processed_files=[{"filename": "notes.txt", "file_path": str(src)}],
        )

        call_count = {"n": 0}

        def _loader(real_handle):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise SandboxExpiredError("sandbox gone mid re-activation")
            # Second call (against the fresh handle) succeeds — nothing to replay.

        lazy._skills_loader = _loader

        mock_sss = MagicMock()
        mock_sss.get_or_create.side_effect = [stale_handle, fresh_handle]

        with patch("services.sandbox_session_service.sandbox_session_service", mock_sss):
            with pytest.raises(SandboxExpiredError):
                lazy.get()

            assert lazy._remote_inputs_prepared is False

            result = lazy.get()

        assert result is fresh_handle
        assert lazy._remote_inputs_prepared is True
        # write_file is called once per get() attempt (workspace prep happens before
        # the skills_loader call, so the first — doomed — attempt against the stale
        # handle also pushes it); the key regression this pins is that the SECOND
        # call, against the recreated fresh_handle, genuinely happens too — i.e.
        # _remote_inputs_prepared was truly reset by invalidate(), not left stale
        # True (which would have made this second push silently never happen).
        mock_provider.write_file.assert_any_call(fresh_handle, "input/notes.txt", b"NOTES")
        assert mock_provider.write_file.call_count == 2

    def test_multiple_previously_active_skills_are_all_reactivated(self, tmp_path):
        """AC-20 core assertion: every skill this session previously activated must be
        re-activated against the fresh handle — not just the first, and not just one."""
        from services.agent_execution_service import _reactivate_previous_skills
        from tools.sandbox.provider import SkillActivationResult, SkillPhaseResult

        mock_provider = MagicMock()
        mock_provider.PROVIDER_NAME = "opensandbox"
        lazy = self._make_lazy(tmp_path, mock_provider)
        lazy._record_active_skill("alpha", 1)
        lazy._record_active_skill("beta", 2)
        lazy._record_active_skill("gamma", 3)

        def _ok_result(skill_id, name):
            return SkillActivationResult(
                skill_name=name,
                skill_id=skill_id,
                files_dir=f"/x/{name}",
                phases=(SkillPhaseResult(phase="files", status="ok", detail="materialised", duration_ms=1),),
                status="active",
            )

        raw_provider = MagicMock()
        raw_provider.ensure_skill.side_effect = lambda handle, payload: _ok_result(
            payload.skill_id, payload.name
        )

        real_handle = MagicMock()

        with patch("services.sandbox_session_service.sandbox_session_service", MagicMock()):
            _reactivate_previous_skills(
                lazy,
                raw_provider,
                lambda skill_id: SimpleNamespace(name={1: "alpha", 2: "beta", 3: "gamma"}[skill_id], skill_id=skill_id),
                real_handle,
            )

        # Every previously-active skill got its own ensure_skill call against the fresh handle.
        assert raw_provider.ensure_skill.call_count == 3
        reactivated_names = {
            call_args.args[1].name for call_args in raw_provider.ensure_skill.call_args_list
        }
        assert reactivated_names == {"alpha", "beta", "gamma"}
        # All three remain recorded active (none dropped, none recorded as a failure).
        assert dict(lazy._snapshot_active_skills()) == {"alpha": 1, "beta": 2, "gamma": 3}
        assert lazy.skill_reactivation_errors == {}

    def test_budget_exhausted_skips_remaining_skills_without_attempting_them(self, tmp_path, monkeypatch):
        """MEDIUM fix (fix round 1): the re-activation loop's wall-clock
        deadline was completely untested. Shrink the budget to a tiny value
        and make the FIRST skill's own ``ensure_skill`` call consume the
        whole thing via a controlled delay — the remaining skills must be
        recorded with a "not attempted, budget exceeded" detail (self-heals
        on the next explicit ``load_skill``), never silently dropped from the
        registry and never actually attempted against the sandbox."""
        import time as _time

        import services.agent_execution_service as aes
        from services.agent_execution_service import _reactivate_previous_skills
        from tools.sandbox.provider import SkillActivationResult, SkillPhaseResult

        monkeypatch.setattr(aes, "_skill_bootstrap_budget_seconds", lambda: 0.05)

        mock_provider = MagicMock()
        mock_provider.PROVIDER_NAME = "opensandbox"
        lazy = self._make_lazy(tmp_path, mock_provider)
        lazy._record_active_skill("alpha", 1)
        lazy._record_active_skill("beta", 2)
        lazy._record_active_skill("gamma", 3)

        def _ensure_skill(handle, payload):
            if payload.name == "alpha":
                _time.sleep(0.15)  # burns past the 0.05s budget
            return SkillActivationResult(
                skill_name=payload.name,
                skill_id=payload.skill_id,
                files_dir=f"/x/{payload.name}",
                phases=(SkillPhaseResult(phase="files", status="ok", detail="materialised", duration_ms=1),),
                status="active",
            )

        raw_provider = MagicMock()
        raw_provider.ensure_skill.side_effect = _ensure_skill
        real_handle = MagicMock()

        with patch("services.sandbox_session_service.sandbox_session_service", MagicMock()):
            _reactivate_previous_skills(
                lazy,
                raw_provider,
                lambda skill_id: SimpleNamespace(name={1: "alpha", 2: "beta", 3: "gamma"}[skill_id], skill_id=skill_id),
                real_handle,
            )

        # Only alpha was actually attempted against the sandbox.
        assert raw_provider.ensure_skill.call_count == 1
        assert raw_provider.ensure_skill.call_args.args[1].name == "alpha"

        # beta/gamma were never touched — not attempted, not forgotten from the
        # registry (they self-heal on the next explicit load_skill call).
        assert dict(lazy._snapshot_active_skills()) == {"alpha": 1, "beta": 2, "gamma": 3}
        assert "alpha" not in lazy.skill_reactivation_errors
        assert "budget exceeded" in lazy.skill_reactivation_errors.get("beta", "")
        assert "budget exceeded" in lazy.skill_reactivation_errors.get("gamma", "")

    def test_get_reactivates_every_previously_active_skill_before_returning(self, tmp_path):
        """End-to-end (via _LazySandboxHandle.get(), the real call site step_020 wires
        _reactivate_previous_skills into): after a sandbox recreation, every skill that
        was active before must be reactivated against the FRESH handle before get()
        hands it back to the caller — no tool call can observe a partially-recovered
        sandbox."""
        import functools

        from services.agent_execution_service import _LazySandboxHandle, _reactivate_previous_skills
        from tools.sandbox.provider import SandboxHandle, SkillActivationResult, SkillPhaseResult

        mock_provider = MagicMock()
        mock_provider.PROVIDER_NAME = "opensandbox"
        mock_provider.requires_file_sync = True
        mock_provider.list_files.return_value = []

        fresh_handle = SandboxHandle(
            sandbox_id="fresh-multi", working_dir=str(tmp_path), provider_name="opensandbox", metadata={},
        )

        lazy = self._make_lazy(tmp_path, mock_provider)
        lazy._record_active_skill("alpha", 1)
        lazy._record_active_skill("beta", 2)

        payload_provider = lambda skill_id: SimpleNamespace(
            name={1: "alpha", 2: "beta"}[skill_id], skill_id=skill_id
        )

        def _ok_result(handle, payload):
            return SkillActivationResult(
                skill_name=payload.name,
                skill_id=payload.skill_id,
                files_dir=f"/x/{payload.name}",
                phases=(SkillPhaseResult(phase="files", status="ok", detail="materialised", duration_ms=1),),
                status="active",
            )

        mock_provider.ensure_skill = MagicMock(side_effect=_ok_result)

        lazy._skills_loader = functools.partial(
            _reactivate_previous_skills, lazy, mock_provider, payload_provider
        )

        mock_sss = MagicMock()
        mock_sss.get_or_create.return_value = fresh_handle

        with patch("services.sandbox_session_service.sandbox_session_service", mock_sss):
            result = lazy.get()

        assert result is fresh_handle
        # Both previously-active skills were reactivated against the SAME fresh handle
        # get() is about to return — before it returns, per AC-20.
        assert mock_provider.ensure_skill.call_count == 2
        for call_args in mock_provider.ensure_skill.call_args_list:
            assert call_args.args[0] is fresh_handle
        reactivated_names = {c.args[1].name for c in mock_provider.ensure_skill.call_args_list}
        assert reactivated_names == {"alpha", "beta"}
        assert lazy.skill_reactivation_errors == {}
