"""
Unit tests — IT-4 File Round-Trip
====================================

Verification criteria from the RFC:
  1. ``_prepare_turn`` obtains a sandbox handle via SandboxSessionService when
     ``enable_code_interpreter`` is True.
  2. For non-subprocess providers, ``_prepare_turn`` pushes each processed_file
     into the sandbox via ``provider.write_file``.
  3. For SubprocessProvider (provider_name == 'subprocess'), no push/pull occurs.
  4. ``_finalize_turn`` pulls new remote files (not in pre_existing_remote_files)
     into ``working_dir`` before ``sync_output_files``.
  5. Files under ``/workspace/.skills/`` are never pulled.
  6. Unsafe basenames (path traversal) are skipped during pull.
  7. Push/pull errors are logged but do not crash the turn.
"""
from __future__ import annotations

import os
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from services.agent_execution_context import AgentExecutionContext
from services.agent_execution_service import AgentExecutionService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _base_ctx(working_dir, provider_name="subprocess", processed_files=None, remote_files_pre=None):
    """Build a minimal context with sandbox fields populated."""
    from tools.sandbox.provider import SandboxHandle

    handle = SandboxHandle(
        sandbox_id="s1",
        working_dir=working_dir,
        provider_name=provider_name,
        metadata={},
    )
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
# 1. _prepare_turn calls SandboxSessionService.get_or_create
# ---------------------------------------------------------------------------


class TestPrepareTurnSandboxHandleCreation:
    def test_get_or_create_called_when_code_interpreter_enabled(self, tmp_path, monkeypatch):
        agent = _make_agent(enable_code_interpreter=True)
        svc = _make_service(agent)

        mock_handle = _make_subprocess_handle(str(tmp_path))
        mock_provider = MagicMock()
        mock_provider.create_sandbox.return_value = mock_handle
        mock_provider.PROVIDER_NAME = "subprocess"

        mock_sss = MagicMock()
        mock_sss.get_or_create.return_value = mock_handle

        with (
            patch("services.agent_execution_service.get_app_config", return_value={"TMP_BASE_FOLDER": str(tmp_path)}),
            patch("services.agent_execution_service.AgentExecutionService._validate_agent_access", new=AsyncMock()),
            patch("tools.sandbox.factory.resolve_provider", return_value=mock_provider),
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
        mock_sss.get_or_create.assert_called_once()

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


# ---------------------------------------------------------------------------
# 2. File push — remote provider only
# ---------------------------------------------------------------------------


class TestPrepareTurnFilePush:
    """Push processed_files into non-subprocess sandbox."""

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
        mock_provider.list_files.return_value = []

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
            patch("tools.sandbox.factory.resolve_provider", return_value=mock_provider),
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

        mock_provider.write_file.assert_called_once_with(
            mock_handle, "data.xlsx", b"XLSX_CONTENT"
        )

    def test_no_push_for_subprocess_provider(self, tmp_path):
        agent = _make_agent(enable_code_interpreter=True)
        svc = _make_service(agent)

        src = tmp_path / "report.csv"
        src.write_bytes(b"CSV")

        mock_handle = _make_subprocess_handle(str(tmp_path))
        mock_provider = MagicMock()
        mock_provider.PROVIDER_NAME = "subprocess"
        mock_provider.create_sandbox.return_value = mock_handle

        mock_sss = MagicMock()
        mock_sss.get_or_create.return_value = mock_handle

        file_ref = MagicMock()
        file_ref.filename = "report.csv"
        file_ref.content = "data"
        file_ref.file_type = "text"
        file_ref.file_id = "fid2"
        file_ref.file_path = str(src)

        with (
            patch("services.agent_execution_service.get_app_config", return_value={"TMP_BASE_FOLDER": str(tmp_path)}),
            patch("services.agent_execution_service.AgentExecutionService._validate_agent_access", new=AsyncMock()),
            patch("tools.sandbox.factory.resolve_provider", return_value=mock_provider),
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

        # SubprocessProvider: no write_file called (files are in working_dir already)
        mock_provider.write_file.assert_not_called()

    def test_push_error_does_not_crash_turn(self, tmp_path):
        agent = _make_agent(enable_code_interpreter=True)
        svc = _make_service(agent)

        mock_handle = _make_remote_handle(str(tmp_path))
        mock_provider = MagicMock()
        mock_provider.PROVIDER_NAME = "opensandbox"
        mock_provider.create_sandbox.return_value = mock_handle
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
            patch("tools.sandbox.factory.resolve_provider", return_value=mock_provider),
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


# ---------------------------------------------------------------------------
# 3. _finalize_turn — pull remote files into working_dir
# ---------------------------------------------------------------------------


class TestFinalizeTurnFilePull:
    """Pull new remote files into working_dir before sync_output_files."""

    def _run_finalize(self, ctx, tmp_path):
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

    def test_pulls_new_remote_file(self, tmp_path):
        ctx = _base_ctx(str(tmp_path), provider_name="opensandbox")
        ctx.sandbox_provider.list_files.return_value = ["/workspace/report.docx"]
        ctx.sandbox_provider.read_file.return_value = b"DOCX_BYTES"
        ctx.pre_existing_remote_files = set()

        self._run_finalize(ctx, tmp_path)

        dest = tmp_path / "report.docx"
        assert dest.exists()
        assert dest.read_bytes() == b"DOCX_BYTES"

    def test_pulls_new_remote_file_from_bare_filename(self, tmp_path):
        ctx = _base_ctx(str(tmp_path), provider_name="opensandbox")
        ctx.sandbox_provider.list_files.return_value = ["report.docx"]
        ctx.sandbox_provider.read_file.return_value = b"DOCX_BYTES"
        ctx.pre_existing_remote_files = set()

        self._run_finalize(ctx, tmp_path)

        dest = tmp_path / "report.docx"
        assert dest.exists()
        assert dest.read_bytes() == b"DOCX_BYTES"
        ctx.sandbox_provider.read_file.assert_called_once_with(
            ctx.sandbox_handle, "report.docx"
        )

    def test_skips_pre_existing_remote_file(self, tmp_path):
        ctx = _base_ctx(str(tmp_path), provider_name="opensandbox")
        ctx.sandbox_provider.list_files.return_value = ["/workspace/old.txt"]
        ctx.sandbox_provider.read_file.return_value = b"OLD"
        ctx.pre_existing_remote_files = {"/workspace/old.txt"}

        self._run_finalize(ctx, tmp_path)

        assert not (tmp_path / "old.txt").exists()

    def test_skips_skill_resources(self, tmp_path):
        ctx = _base_ctx(str(tmp_path), provider_name="opensandbox")
        ctx.sandbox_provider.list_files.return_value = [
            "/workspace/.skills/word-generation/setup.py",
            "/workspace/output.xlsx",
        ]
        ctx.sandbox_provider.read_file.return_value = b"DATA"
        ctx.pre_existing_remote_files = set()

        self._run_finalize(ctx, tmp_path)

        # Skill resource skipped
        assert not (tmp_path / "setup.py").exists()
        # Regular file pulled
        assert (tmp_path / "output.xlsx").exists()

    def test_skips_path_traversal_filenames(self, tmp_path):
        ctx = _base_ctx(str(tmp_path), provider_name="opensandbox")
        ctx.sandbox_provider.list_files.return_value = [
            # Normalizes to /etc/passwd — outside /workspace/
            "/workspace/../../../etc/passwd",
            # Hidden file inside /workspace/ — basename starts with .
            "/workspace/.hidden",
        ]
        ctx.sandbox_provider.read_file.return_value = b"EVIL"
        ctx.pre_existing_remote_files = set()

        self._run_finalize(ctx, tmp_path)

        # read_file should never have been called for these unsafe paths
        ctx.sandbox_provider.read_file.assert_not_called()
        # No files written
        assert not (tmp_path / "passwd").exists()
        assert not (tmp_path / ".hidden").exists()

    def test_no_pull_for_subprocess_provider(self, tmp_path):
        ctx = _base_ctx(str(tmp_path), provider_name="subprocess")
        ctx.sandbox_provider.list_files.return_value = ["report.docx"]
        ctx.sandbox_provider.read_file.return_value = b"DATA"

        self._run_finalize(ctx, tmp_path)

        # SubprocessProvider: list_files should NOT be called for pull
        ctx.sandbox_provider.list_files.assert_not_called()

    def test_no_pull_when_no_sandbox_handle(self, tmp_path):
        ctx = _base_ctx(str(tmp_path), provider_name="opensandbox")
        ctx.sandbox_handle = None  # No sandbox

        self._run_finalize(ctx, tmp_path)

        ctx.sandbox_provider.list_files.assert_not_called()

    def test_pull_error_does_not_crash_turn(self, tmp_path):
        ctx = _base_ctx(str(tmp_path), provider_name="opensandbox")
        ctx.sandbox_provider.list_files.side_effect = RuntimeError("connection lost")

        # Should not raise
        self._run_finalize(ctx, tmp_path)

    def test_read_file_error_skips_file_gracefully(self, tmp_path):
        ctx = _base_ctx(str(tmp_path), provider_name="opensandbox")
        ctx.sandbox_provider.list_files.return_value = ["/workspace/good.txt", "/workspace/bad.bin"]
        ctx.sandbox_provider.read_file.side_effect = lambda handle, path: (
            b"GOOD" if "good" in path else (_ for _ in ()).throw(IOError("disk full"))
        )
        ctx.pre_existing_remote_files = set()

        self._run_finalize(ctx, tmp_path)

        assert (tmp_path / "good.txt").exists()
        assert not (tmp_path / "bad.bin").exists()


# ---------------------------------------------------------------------------
# 4. SubprocessProvider — existing snapshot diff is unchanged
# ---------------------------------------------------------------------------


class TestSubprocessRoundTripUnchanged:
    """Verify the existing working_dir snapshot diff still works end-to-end."""

    def test_pre_existing_files_snapshot_excludes_new_file(self, tmp_path):
        """Files written to working_dir during the turn appear in sync_output_files exclusion set."""
        svc = AgentExecutionService.__new__(AgentExecutionService)
        svc.agent_service = MagicMock()
        svc.session_service = MagicMock()
        svc.session_service.touch_session = AsyncMock()
        svc.agent_execution_repo = MagicMock()

        # Pre-existing file
        (tmp_path / "old.txt").write_text("old")
        pre_existing = {"old.txt"}

        # New file written during turn
        (tmp_path / "report.docx").write_bytes(b"DOCX")

        ctx = _base_ctx(str(tmp_path), provider_name="subprocess")
        ctx.pre_existing_files = pre_existing
        ctx.sandbox_handle = None  # Subprocess: no remote handle

        captured_exclude = []

        async def _mock_sync(*, working_dir, agent_id, user_context, conversation_id, exclude_filenames):
            captured_exclude.append(exclude_filenames)
            return []

        with (
            patch("services.agent_execution_service.FileManagementService") as MockFMS,
            patch("tools.agentTools.parse_agent_response", return_value="OK"),
            patch.object(svc, "_update_request_count"),
        ):
            MockFMS.return_value.sync_output_files = _mock_sync
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                svc._finalize_turn(ctx, "OK", MagicMock())
            )

        assert "old.txt" in captured_exclude[0]
        assert "report.docx" not in captured_exclude[0]
