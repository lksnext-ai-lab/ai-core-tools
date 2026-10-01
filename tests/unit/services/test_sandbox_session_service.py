from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services.sandbox_session_service import (
    SandboxCapacityError,
    SandboxSessionService,
    SavedSandboxState,
    _Entry,
    _provider_from_saved_state,
)
from tools.sandbox.provider import SandboxExpiredError, SandboxHandle


def _handle(sandbox_id: str = "sbx-1") -> SandboxHandle:
    return SandboxHandle(
        sandbox_id=sandbox_id,
        working_dir="/tmp",
        provider_name="mock",
        session_key="conv_1_1",
    )


def _mock_session_local(monkeypatch, row):
    """Patch db.database.SessionLocal so query(...).filter(...).first() returns *row*."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row
    monkeypatch.setattr("db.database.SessionLocal", lambda: db)
    return db


@pytest.fixture(autouse=True)
def _no_real_db_by_default(monkeypatch):
    """Keep this module hermetic: block real DB access from persistence helpers.

    ``_persist_sandbox_state``/``_clear_persisted_sandbox_state`` always open
    their own ``SessionLocal()`` now (never the caller-supplied session), so
    without this default they would hit whatever real DB is configured via
    ``SQLALCHEMY_DATABASE_URI``. Individual tests override this via
    ``_mock_session_local`` when they need to observe persistence.
    """
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    monkeypatch.setattr("db.database.SessionLocal", lambda: db)
    return db


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


def test_begin_use_persists_lease_from_session_key(monkeypatch):
    service = SandboxSessionService()
    provider = MagicMock()
    handle = _handle()
    service._sessions["conv_1_1"] = _Entry(handle=handle, provider=provider)
    conversation = SimpleNamespace(
        conversation_id=1,
        sandbox_session_id=handle.sandbox_id,
        sandbox_state=json.dumps(
            {
                "provider": handle.provider_name,
                "session_key": "conv_1_1",
                "sandbox_id": handle.sandbox_id,
                "active_skills": {},
                "updated_at": datetime.utcnow().isoformat() + "Z",
            }
        ),
    )

    db = _mock_session_local(monkeypatch, conversation)

    assert service.begin_use("conv_1_1") is True

    state = json.loads(conversation.sandbox_state)
    assert state["lease_expires_at"] is not None
    assert state["last_activity_at"] is not None
    db.commit.assert_called_once()
    db.close.assert_called_once()


def test_get_or_create_does_not_resume_idle_expired_persisted_state(monkeypatch):
    monkeypatch.setattr("config.SANDBOX_IDLE_TIMEOUT_S", 120, raising=False)
    service = SandboxSessionService()
    provider = MagicMock()
    provider.PROVIDER_NAME = "mock"
    provider.create_sandbox.return_value = _handle("fresh")
    stale_updated_at = (datetime.utcnow() - timedelta(seconds=121)).isoformat() + "Z"
    conversation = SimpleNamespace(
        conversation_id=1,
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
    _mock_session_local(monkeypatch, conversation)
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


def test_get_or_create_retries_fresh_when_persisted_resume_fails(monkeypatch):
    monkeypatch.setattr("config.SANDBOX_IDLE_TIMEOUT_S", 120, raising=False)
    service = SandboxSessionService()
    provider = MagicMock()
    provider.PROVIDER_NAME = "mock"
    provider.create_sandbox.side_effect = [
        SandboxExpiredError("old sandbox not found"),
        _handle("fresh"),
    ]
    now = datetime.utcnow().isoformat() + "Z"
    conversation = SimpleNamespace(
        conversation_id=1,
        sandbox_session_id="old",
        sandbox_state=json.dumps(
            {
                "provider": "mock",
                "session_key": "conv_1_1",
                "sandbox_id": "old",
                "active_skills": {},
                "last_activity_at": now,
                "updated_at": now,
            }
        ),
    )
    _mock_session_local(monkeypatch, conversation)
    db = MagicMock()

    handle = service.get_or_create(
        session_key="conv_1_1",
        provider=provider,
        working_dir="/tmp",
        conversation=conversation,
        db=db,
    )

    assert handle.sandbox_id == "fresh"
    assert provider.create_sandbox.call_args_list[0].kwargs["existing_sandbox_id"] == "old"
    assert provider.create_sandbox.call_args_list[1].kwargs["existing_sandbox_id"] is None
    assert conversation.sandbox_session_id == "fresh"


def test_get_or_create_cache_hit_persists_last_used(monkeypatch):
    monkeypatch.setattr("config.SANDBOX_IDLE_TIMEOUT_S", 120, raising=False)
    service = SandboxSessionService()
    provider = MagicMock()
    provider.PROVIDER_NAME = "mock"
    handle = _handle()
    service._sessions["conv_1_1"] = _Entry(handle=handle, provider=provider)
    conversation = SimpleNamespace(
        conversation_id=1, sandbox_session_id=None, sandbox_state=None
    )
    fresh_db = _mock_session_local(monkeypatch, conversation)
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
    fresh_db.commit.assert_called_once()
    # The caller-supplied session must never be written through directly —
    # sandbox persistence always uses its own short-lived session (bug #3).
    db.commit.assert_not_called()
    db.add.assert_not_called()


def test_reap_stale_db_state_destroys_by_provider_id(monkeypatch):
    monkeypatch.setattr("config.SANDBOX_IDLE_TIMEOUT_S", 120, raising=False)
    service = SandboxSessionService()
    stale_updated_at = (datetime.utcnow() - timedelta(seconds=121)).isoformat() + "Z"
    conversation = SimpleNamespace(
        sandbox_session_id="old",
        sandbox_state=json.dumps(
            {
                "provider": "mock",
                "session_key": "conv_1_1",
                "sandbox_id": "old",
                "active_skills": {},
                "last_activity_at": stale_updated_at,
                "updated_at": stale_updated_at,
            }
        ),
    )
    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value.all.return_value = [conversation]
    provider = MagicMock()
    monkeypatch.setattr(
        "services.sandbox_session_service._get_provider_by_name",
        lambda name: provider,
    )

    service._reap_stale(db=db)

    provider.destroy_sandbox_id.assert_called_once_with("old")
    assert conversation.sandbox_session_id is None
    assert conversation.sandbox_state is None
    db.commit.assert_called_once()


def test_reap_stale_db_state_skips_active_in_memory_session(monkeypatch):
    monkeypatch.setattr("config.SANDBOX_IDLE_TIMEOUT_S", 120, raising=False)
    service = SandboxSessionService()
    stale_updated_at = (datetime.utcnow() - timedelta(seconds=121)).isoformat() + "Z"
    conversation = SimpleNamespace(
        sandbox_session_id="old",
        sandbox_state=json.dumps(
            {
                "provider": "mock",
                "session_key": "conv_1_1",
                "sandbox_id": "old",
                "active_skills": {},
                "last_activity_at": stale_updated_at,
                "updated_at": stale_updated_at,
            }
        ),
    )
    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value.all.return_value = [conversation]
    provider = MagicMock()
    service._sessions["conv_1_1"] = _Entry(
        handle=_handle("old"),
        provider=provider,
    )

    service._reap_stale(db=db)

    provider.destroy_sandbox_id.assert_not_called()
    assert conversation.sandbox_session_id == "old"
    assert conversation.sandbox_state is not None


def test_reap_stale_db_state_leaves_state_when_destroy_fails(monkeypatch):
    """Bug #1 regression: a failed destroy must not silently discard the DB record."""
    monkeypatch.setattr("config.SANDBOX_IDLE_TIMEOUT_S", 120, raising=False)
    service = SandboxSessionService()
    stale_updated_at = (datetime.utcnow() - timedelta(seconds=121)).isoformat() + "Z"
    conversation = SimpleNamespace(
        sandbox_session_id="old",
        sandbox_state=json.dumps(
            {
                "provider": "mock",
                "session_key": "conv_1_1",
                "sandbox_id": "old",
                "last_activity_at": stale_updated_at,
                "updated_at": stale_updated_at,
            }
        ),
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [conversation]
    provider = MagicMock()
    provider.destroy_sandbox_id.side_effect = RuntimeError("network error")
    monkeypatch.setattr(
        "services.sandbox_session_service._get_provider_by_name",
        lambda name: provider,
    )

    service._reap_stale(db=db)

    provider.destroy_sandbox_id.assert_called_once_with("old")
    # Destroy failed — the record must be preserved for a future retry.
    assert conversation.sandbox_session_id == "old"
    assert conversation.sandbox_state is not None


# ---------------------------------------------------------------------------
# Bug #1: cleanup/reaper must use tenant credentials when available
# ---------------------------------------------------------------------------


def test_provider_from_saved_state_uses_service_credentials(monkeypatch):
    from repositories.sandbox_service_repository import SandboxServiceRepository

    fake_service = SimpleNamespace(
        provider="daytona",
        endpoint="https://tenant.example.com",
        api_key="tenant-secret-key",  # pragma: allowlist secret
        extra_config=None,
    )
    monkeypatch.setattr(
        SandboxServiceRepository,
        "get_by_id",
        staticmethod(lambda db, service_id: fake_service),
    )

    provider_cls = MagicMock()
    provider_instance = MagicMock()
    provider_cls.return_value = provider_instance
    monkeypatch.setattr(
        "tools.sandbox.factory._PROVIDER_REGISTRY", {"daytona": provider_cls}
    )

    state = SavedSandboxState(
        provider="daytona",
        session_key="conv_1_1",
        sandbox_id="sbx-1",
        updated_at="now",
        sandbox_service_id=42,
    )

    provider = _provider_from_saved_state(state)

    assert provider is provider_instance
    provider_cls.assert_called_once_with(
        credentials={
            "api_key": "tenant-secret-key",
            "api_url": "https://tenant.example.com",
            "target": None,
        }
    )


def test_provider_from_saved_state_falls_back_without_sandbox_service_id(monkeypatch):
    fallback_provider = MagicMock()
    monkeypatch.setattr(
        "services.sandbox_session_service._get_provider_by_name",
        lambda name: fallback_provider,
    )

    state = SavedSandboxState(
        provider="mock", session_key="conv_1_1", sandbox_id="sbx-1", updated_at="now",
    )

    provider = _provider_from_saved_state(state)

    assert provider is fallback_provider


def test_provider_from_saved_state_falls_back_when_service_lookup_fails(monkeypatch):
    from repositories.sandbox_service_repository import SandboxServiceRepository

    monkeypatch.setattr(
        SandboxServiceRepository,
        "get_by_id",
        staticmethod(lambda db, service_id: None),
    )
    fallback_provider = MagicMock()
    monkeypatch.setattr(
        "services.sandbox_session_service._get_provider_by_name",
        lambda name: fallback_provider,
    )

    state = SavedSandboxState(
        provider="mock",
        session_key="conv_1_1",
        sandbox_id="sbx-1",
        updated_at="now",
        sandbox_service_id=999,
    )

    provider = _provider_from_saved_state(state)

    assert provider is fallback_provider


# ---------------------------------------------------------------------------
# Bug #2: creation race — only one sandbox may be created per session_key
# ---------------------------------------------------------------------------


def test_get_or_create_concurrent_calls_create_only_one_sandbox():
    service = SandboxSessionService()
    provider = MagicMock()
    provider.PROVIDER_NAME = "mock"

    def slow_create(*, working_dir, session_key, existing_sandbox_id):
        time.sleep(0.15)
        return _handle("shared-sbx")

    provider.create_sandbox.side_effect = slow_create

    results: list[SandboxHandle] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker():
        try:
            handle = service.get_or_create(
                session_key="conv_1_1",
                provider=provider,
                working_dir="/tmp",
            )
            with lock:
                results.append(handle)
        except BaseException as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert not errors
    assert len(results) == 2
    assert provider.create_sandbox.call_count == 1
    assert results[0].sandbox_id == results[1].sandbox_id == "shared-sbx"
    assert len(service._sessions) == 1


# ---------------------------------------------------------------------------
# Bug #4: global concurrency cap
# ---------------------------------------------------------------------------


def test_get_or_create_raises_capacity_error_when_cap_reached(monkeypatch):
    monkeypatch.setattr("config.SANDBOX_MAX_CONCURRENT_SESSIONS", 1, raising=False)
    service = SandboxSessionService()
    provider = MagicMock()
    provider.PROVIDER_NAME = "mock"
    provider.create_sandbox.return_value = _handle("sbx-1")

    service.get_or_create(session_key="conv_1_1", provider=provider, working_dir="/tmp")
    assert len(service._sessions) == 1

    with pytest.raises(SandboxCapacityError):
        service.get_or_create(session_key="conv_1_2", provider=provider, working_dir="/tmp")

    assert provider.create_sandbox.call_count == 1
    assert "conv_1_2" not in service._sessions


def test_get_or_create_cap_holds_across_concurrent_distinct_keys(monkeypatch):
    """The concurrency cap must be enforced atomically across DIFFERENT keys.

    The per-key creation lock only serializes creation for the SAME
    session_key. N concurrently-arriving requests for DIFFERENT keys could
    each observe `len(self._sessions) < max_sessions` before any of them
    finish creating, and all proceed — overshooting the cap. This asserts
    the reservation (`self._pending_creates`) closes that gap.
    """
    monkeypatch.setattr("config.SANDBOX_MAX_CONCURRENT_SESSIONS", 2, raising=False)
    service = SandboxSessionService()
    provider = MagicMock()
    provider.PROVIDER_NAME = "mock"

    def slow_create(*, working_dir, session_key, existing_sandbox_id):
        time.sleep(0.15)
        return _handle(f"sbx-{session_key}")

    provider.create_sandbox.side_effect = slow_create

    results: list[SandboxHandle] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker(key: str):
        try:
            handle = service.get_or_create(
                session_key=key, provider=provider, working_dir="/tmp"
            )
            with lock:
                results.append(handle)
        except SandboxCapacityError as exc:
            with lock:
                errors.append(exc)

    keys = [f"conv_1_{i}" for i in range(5)]
    threads = [threading.Thread(target=worker, args=(key,)) for key in keys]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    # Exactly 2 (the cap) succeed; the rest are rejected, never orphan-created.
    assert len(results) == 2
    assert len(errors) == 3
    assert provider.create_sandbox.call_count == 2
    assert len(service._sessions) == 2
    assert service._pending_creates == set()


def test_get_or_create_cache_hit_ignores_capacity_cap(monkeypatch):
    """Reusing an already-cached sandbox must not be blocked by the cap."""
    monkeypatch.setattr("config.SANDBOX_MAX_CONCURRENT_SESSIONS", 1, raising=False)
    service = SandboxSessionService()
    provider = MagicMock()
    provider.PROVIDER_NAME = "mock"
    handle = _handle("sbx-1")
    service._sessions["conv_1_1"] = _Entry(handle=handle, provider=provider)

    result = service.get_or_create(
        session_key="conv_1_1", provider=provider, working_dir="/tmp"
    )

    assert result.sandbox_id == "sbx-1"
    provider.create_sandbox.assert_not_called()
