"""Regression tests for backend/tools/sandbox/tool_factory.py's REPL tool
error handling — specifically that provider errors raised during lazy
sandbox materialization (SandboxCapacityError, SandboxExpiredError) are
translated into clean tool-error strings instead of propagating uncaught
and crashing the whole agent turn.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from services.sandbox_session_service import SandboxCapacityError
from tools.sandbox.provider import SandboxHandle, SandboxExpiredError
from tools.sandbox.tool_factory import create_sandbox_repl_tool


def _handle() -> SandboxHandle:
    return SandboxHandle(
        sandbox_id="sbx-1",
        working_dir="/tmp",
        provider_name="opensandbox",
        session_key="conv_1_1",
        metadata={},
    )


def test_repl_tool_returns_clean_error_on_capacity_error():
    """SandboxCapacityError (raised by lazy handle materialization when the
    process-wide concurrent-sandbox cap is reached) must not propagate
    uncaught out of the REPL tool."""
    handle = _handle()
    provider = MagicMock()
    provider.get_supported_languages.return_value = ["python"]
    provider.run_code.side_effect = SandboxCapacityError("cap reached")

    tool = create_sandbox_repl_tool(handle, provider, "python")
    result = tool.invoke({"code": "print(1)"})

    assert "capacity" in result.lower()
    assert "error" in result.lower()


def test_repl_tool_recovers_from_expired_sandbox():
    """Sanity check the existing expiry-recovery path still works after the
    new except clause was added alongside it."""
    handle = _handle()
    provider = MagicMock()
    provider.get_supported_languages.return_value = ["python"]
    provider.run_code.side_effect = [SandboxExpiredError("gone"), "OK"]

    session_service = MagicMock()
    session_service.begin_use.return_value = True
    session_service.get_or_create.return_value = _handle()

    tool = create_sandbox_repl_tool(
        handle,
        provider,
        "python",
        session_key="conv_1_1",
        session_service=session_service,
    )
    result = tool.invoke({"code": "print(1)"})

    assert result == "OK"
    session_service.evict.assert_called_once_with("conv_1_1")
