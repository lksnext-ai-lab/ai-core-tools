from __future__ import annotations

import time
from datetime import datetime, timedelta
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from services.sandbox_session_service import SandboxSessionService, _Entry
from tools.sandbox.provider import SandboxHandle


def _handle(sandbox_id: str = "sbx-1") -> SandboxHandle:
    return SandboxHandle(
        sandbox_id=sandbox_id,
        working_dir="/tmp",
        provider_name="mock",
        session_key="conv_1_1",
    )


def test_reap_stale_uses_global_idle_timeout(monkeypatch):
    monkeypatch.setattr("config.SANDBOX_IDLE_TIMEOUT_S", 120, raising=False)
    service = SandboxSessionService()
    provider = MagicMock()
    handle = _handle()
    entry = _Entry(handle=handle, provider=provider)
    entry.last_used = time.monotonic() - 121
    service._sessions["conv_1_1"] = entry

    service._reap_stale()

    assert "conv_1_1" not in service._sessions
    provider.destroy_sandbox.assert_called_once_with(handle)


def test_reap_stale_keeps_recent_sessions(monkeypatch):
    monkeypatch.setattr("config.SANDBOX_IDLE_TIMEOUT_S", 120, raising=False)
    service = SandboxSessionService()
    provider = MagicMock()
    handle = _handle()
    entry = _Entry(handle=handle, provider=provider)
    entry.last_used = time.monotonic() - 30
    service._sessions["conv_1_1"] = entry

    service._reap_stale()

    assert "conv_1_1" in service._sessions
    provider.destroy_sandbox.assert_not_called()


def test_reap_stale_skips_active_session(monkeypatch):
    monkeypatch.setattr("config.SANDBOX_IDLE_TIMEOUT_S", 120, raising=False)
    service = SandboxSessionService()
    provider = MagicMock()
    handle = _handle()
    entry = _Entry(handle=handle, provider=provider)
    entry.last_used = time.monotonic() - 121
    entry.active_uses = 1
    service._sessions["conv_1_1"] = entry

    service._reap_stale()

    assert "conv_1_1" in service._sessions
    provider.destroy_sandbox.assert_not_called()


def test_begin_end_use_refreshes_idle_timestamp():
    service = SandboxSessionService()
    provider = MagicMock()
    handle = _handle()
    entry = _Entry(handle=handle, provider=provider)
    entry.last_used = time.monotonic() - 121
    service._sessions["conv_1_1"] = entry

    assert service.begin_use("conv_1_1") is True
    assert entry.active_uses == 1
    used_at = entry.last_used
    assert service.begin_use("missing") is False

    service.end_use("conv_1_1")

    assert entry.active_uses == 0
    assert entry.last_used >= used_at


def test_get_or_create_does_not_resume_idle_expired_persisted_state(monkeypatch):
    monkeypatch.setattr("config.SANDBOX_IDLE_TIMEOUT_S", 120, raising=False)
    service = SandboxSessionService()
    provider = MagicMock()
    provider.PROVIDER_NAME = "mock"
    provider.create_sandbox.return_value = _handle("fresh")
    stale_updated_at = (datetime.utcnow() - timedelta(seconds=121)).isoformat() + "Z"
    conversation = SimpleNamespace(
        sandbox_session_id="old",
        sandbox_state=json.dumps(
            {
                "provider": "mock",
                "session_key": "conv_1_1",
                "sandbox_id": "old",
                "active_skills": {},
                "updated_at": stale_updated_at,
            }
        ),
    )
    db = MagicMock()

    service.get_or_create(
        session_key="conv_1_1",
        provider=provider,
        working_dir="/tmp",
        conversation=conversation,
        db=db,
    )

    assert provider.create_sandbox.call_args.kwargs["existing_sandbox_id"] is None
    assert conversation.sandbox_session_id == "fresh"


def test_get_or_create_cache_hit_persists_last_used(monkeypatch):
    monkeypatch.setattr("config.SANDBOX_IDLE_TIMEOUT_S", 120, raising=False)
    service = SandboxSessionService()
    provider = MagicMock()
    provider.PROVIDER_NAME = "mock"
    handle = _handle()
    service._sessions["conv_1_1"] = _Entry(handle=handle, provider=provider)
    conversation = SimpleNamespace(sandbox_session_id=None, sandbox_state=None)
    db = MagicMock()

    service.get_or_create(
        session_key="conv_1_1",
        provider=provider,
        working_dir="/tmp",
        conversation=conversation,
        db=db,
    )

    assert conversation.sandbox_session_id == handle.sandbox_id
    assert conversation.sandbox_state is not None
    db.commit.assert_called_once()
