"""
Unit tests — step_017/018 fix round 1 (review board H1/H2/H3/MEDIUM).

Covers ``OpenSandboxProvider._materialise_skill_files`` (the bulk
``sandbox.files.write_files`` override) in isolation, faking ``run_code`` at
the provider level (no real SDK, no network, no DB) so
``_run_verified_command``'s sentinel-wrapped shell commands can be steered
per-test without simulating OpenSandbox's real threaded execution path
(covered separately by ``test_sandbox_opensandbox_provider.py``).

- H1: a bulk ``write_files`` call that raises no exception but whose
  verification command fails must fall back to per-file writes, not be
  reported as ``status="ok"``.
- H2: a payload whose total byte size exceeds
  ``settings.SKILL_IMPORT_MAX_TOTAL_BYTES`` must be rejected as a terminal
  failure on the bulk path — no fallback, no SDK call at all.
- H3: a ``TypeError`` (not ``ValueError``) raised while constructing
  ``WriteEntry`` objects must fall through to the per-file fallback instead
  of propagating.
- MEDIUM: an empty-files (content-only) skill must still result in an
  actually-existing target directory (cleanup command recreates it).
"""

from __future__ import annotations

import re
import sys
import types
from unittest.mock import MagicMock

import pytest

from schemas.skill_package_payload import SkillPackagePayload
from tools.sandbox.opensandbox_provider import OpenSandboxProvider, _META_SANDBOX
from tools.sandbox.provider import SandboxHandle

_SENTINEL_RE = re.compile(r"__SKILL_CMD_OK_[0-9a-f]+__")


def _sentinel(command: str) -> str | None:
    match = _SENTINEL_RE.search(command)
    return match.group(0) if match else None


def _make_fake_run_code(fail_substrings: tuple[str, ...] = (), *, calls: list[str] | None = None):
    """Build a fake ``run_code`` that steers ``_run_verified_command`` results.

    Any command containing one of *fail_substrings* is reported as failed
    (sentinel omitted from the output); everything else "succeeds" (the
    sentinel echoed back), matching how ``_run_verified_command`` inspects
    its own sentinel to decide success/failure — see ``provider.py``.
    """

    def fake_run_code(handle, command, *, language="bash", timeout=None, max_output_chars=None, **kwargs):
        if calls is not None:
            calls.append(command)
        sentinel = _sentinel(command)
        should_fail = any(s in command for s in fail_substrings)
        if should_fail or sentinel is None:
            return "[Error] simulated command failure"
        return f"ok\n{sentinel}\n"

    return fake_run_code


def _make_provider_and_handle(monkeypatch) -> tuple[OpenSandboxProvider, SandboxHandle]:
    monkeypatch.setattr("config.SANDBOX_DEFAULT_TIMEOUT_S", 5, raising=False)
    monkeypatch.setattr("config.SANDBOX_SKILL_BOOTSTRAP_TIMEOUT_S", 30, raising=False)
    monkeypatch.setattr("config.SANDBOX_MAX_OUTPUT_CHARS", 20000, raising=False)
    monkeypatch.setattr("config.SKILL_IMPORT_MAX_TOTAL_BYTES", 50 * 1024 * 1024, raising=False)

    provider = OpenSandboxProvider()
    sandbox = MagicMock()
    sandbox.id = "sandbox-fix"
    sandbox.files = MagicMock()
    handle = SandboxHandle(
        sandbox_id=sandbox.id,
        working_dir="/tmp",
        provider_name="opensandbox",
        metadata={_META_SANDBOX: sandbox},
    )
    return provider, handle


def _install_fake_write_entry_module(monkeypatch, write_entry_cls) -> None:
    """Inject a fake ``opensandbox.models.filesystem`` module with a
    controllable ``WriteEntry`` — the real SDK isn't installed in the test
    environment, so ``_materialise_skill_files``'s inline
    ``from opensandbox.models.filesystem import WriteEntry`` must resolve
    against a stand-in."""
    fake_opensandbox = types.ModuleType("opensandbox")
    fake_models = types.ModuleType("opensandbox.models")
    fake_filesystem = types.ModuleType("opensandbox.models.filesystem")
    fake_filesystem.WriteEntry = write_entry_cls
    monkeypatch.setitem(sys.modules, "opensandbox", fake_opensandbox)
    monkeypatch.setitem(sys.modules, "opensandbox.models", fake_models)
    monkeypatch.setitem(sys.modules, "opensandbox.models.filesystem", fake_filesystem)


class _RecordingWriteEntry:
    """Stand-in for the SDK's ``WriteEntry`` that just records construction."""

    def __init__(self, path: str, data: bytes) -> None:
        self.path = path
        self.data = data


def _payload(files: tuple[tuple[str, bytes], ...] = (("a.txt", b"hello"),)) -> SkillPackagePayload:
    return SkillPackagePayload(skill_id=1, name="myskill", files=files)


class TestH1BulkWriteVerification:
    def test_no_exception_but_verification_fails_falls_back_to_per_file(self, monkeypatch):
        provider, handle = _make_provider_and_handle(monkeypatch)
        _install_fake_write_entry_module(monkeypatch, _RecordingWriteEntry)

        calls: list[str] = []
        # Fail only the verification command (contains "-type f"); cleanup
        # and the per-file fallback's own mkdir both succeed.
        provider.run_code = _make_fake_run_code(fail_substrings=("-type f",), calls=calls)

        sandbox = handle.metadata[_META_SANDBOX]
        # write_files raises no exception at all — the exact bug class H1
        # targets: a 2xx/no-exception SDK response with no per-file proof.
        sandbox.files.write_files.return_value = None

        payload = _payload()
        result = provider._materialise_skill_files(handle, payload, payload.name, "/workspace/.skills")

        # Bulk call was attempted...
        assert sandbox.files.write_files.call_count == 1
        # ...but verification failed, so it must NOT be reported as ok, and
        # must fall back to per-file writes (sandbox.files.write_file, singular).
        assert result.status == "ok"  # the per-file fallback itself succeeds
        assert "per-file writes (fallback)" in result.detail
        assert sandbox.files.write_file.call_count == len(payload.files)

    def test_verified_success_reports_ok_via_bulk_path(self, monkeypatch):
        provider, handle = _make_provider_and_handle(monkeypatch)
        _install_fake_write_entry_module(monkeypatch, _RecordingWriteEntry)

        provider.run_code = _make_fake_run_code()  # everything succeeds
        sandbox = handle.metadata[_META_SANDBOX]
        sandbox.files.write_files.return_value = None

        payload = _payload()
        result = provider._materialise_skill_files(handle, payload, payload.name, "/workspace/.skills")

        assert result.status == "ok"
        assert "native bulk write_files" in result.detail
        # No fallback needed — the per-file writer must not have been used.
        assert sandbox.files.write_file.call_count == 0


class TestH2SizeCapEnforced:
    def test_oversized_payload_rejected_without_sdk_call(self, monkeypatch):
        provider, handle = _make_provider_and_handle(monkeypatch)
        monkeypatch.setattr("config.SKILL_IMPORT_MAX_TOTAL_BYTES", 10, raising=False)
        _install_fake_write_entry_module(monkeypatch, _RecordingWriteEntry)

        provider.run_code = _make_fake_run_code()  # cleanup would succeed
        sandbox = handle.metadata[_META_SANDBOX]

        payload = _payload(files=(("big.bin", b"x" * 1000),))
        result = provider._materialise_skill_files(handle, payload, payload.name, "/workspace/.skills")

        assert result.status == "failed"
        assert "too large" in result.detail
        # Terminal — must never reach the SDK bulk call nor the per-file fallback.
        assert sandbox.files.write_files.call_count == 0
        assert sandbox.files.write_file.call_count == 0


class TestH3WriteEntryConstructionException:
    def test_type_error_falls_back_to_per_file(self, monkeypatch):
        provider, handle = _make_provider_and_handle(monkeypatch)

        class ExplodingWriteEntry:
            def __init__(self, path: str, data: bytes) -> None:
                raise TypeError("simulated SDK signature mismatch")

        _install_fake_write_entry_module(monkeypatch, ExplodingWriteEntry)
        provider.run_code = _make_fake_run_code()
        sandbox = handle.metadata[_META_SANDBOX]

        payload = _payload()
        result = provider._materialise_skill_files(handle, payload, payload.name, "/workspace/.skills")

        # Must not propagate — falls through to the per-file fallback and
        # that fallback succeeds.
        assert result.status == "ok"
        assert "per-file writes (fallback)" in result.detail
        assert sandbox.files.write_files.call_count == 0
        assert sandbox.files.write_file.call_count == len(payload.files)

    def test_value_error_stays_terminal_no_fallback(self, monkeypatch):
        provider, handle = _make_provider_and_handle(monkeypatch)
        _install_fake_write_entry_module(monkeypatch, _RecordingWriteEntry)
        provider.run_code = _make_fake_run_code()
        sandbox = handle.metadata[_META_SANDBOX]

        payload = _payload(files=(("../escape.txt", b"x"),))
        result = provider._materialise_skill_files(handle, payload, payload.name, "/workspace/.skills")

        assert result.status == "failed"
        assert "unsafe file path" in result.detail
        assert sandbox.files.write_files.call_count == 0
        assert sandbox.files.write_file.call_count == 0


class TestMediumEmptyFilesDirectoryCreated:
    def test_content_only_skill_creates_target_dir(self, monkeypatch):
        provider, handle = _make_provider_and_handle(monkeypatch)
        _install_fake_write_entry_module(monkeypatch, _RecordingWriteEntry)

        calls: list[str] = []
        provider.run_code = _make_fake_run_code(calls=calls)
        sandbox = handle.metadata[_META_SANDBOX]
        sandbox.files.write_files.return_value = None

        payload = _payload(files=())
        result = provider._materialise_skill_files(handle, payload, payload.name, "/workspace/.skills")

        assert result.status == "ok"
        # The cleanup command must mkdir -p the target dir itself, not just
        # the sibling markers dir — otherwise a content-only skill (no
        # bundled files, write_files([]) is a no-op) reports "ok" for a
        # directory that was never created.
        cleanup_cmd = calls[0]
        assert "rm -rf" in cleanup_cmd
        assert "mkdir -p" in cleanup_cmd
        assert "/workspace/.skills/myskill" in cleanup_cmd
        assert "/workspace/.skills/.markers" in cleanup_cmd
        # write_files is still called (with an empty entries list) since the
        # bulk path is otherwise used.
        assert sandbox.files.write_files.call_count == 1
        assert sandbox.files.write_files.call_args.args[0] == []
