"""Unit coverage for `services.a2a_server.runtime` (step_012 fix round, item 3).

No DB: `configure_sdk_logging`/the capability cards are pure functions, and
`_extended_modifier` is exercised with a `ServerCallContext` built by hand
(no real `ServerCallContextBuilder`/router involved).
"""

from __future__ import annotations

import logging
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from a2a.server.context import ServerCallContext
from a2a.types.a2a_pb2 import TaskPushNotificationConfig
from a2a.utils.errors import ExtendedAgentCardNotConfiguredError, PushNotificationNotSupportedError

from services.a2a_server.runtime import (
    A2ARuntime,
    _extended_modifier,
    build_a2a_runtime,
    build_capability_card,
    build_placeholder_extended_card,
    configure_sdk_logging,
)
from utils.a2a_config import get_a2a_config


@pytest.fixture(autouse=True)
def _clear_a2a_config_cache():
    get_a2a_config.cache_clear()
    yield
    get_a2a_config.cache_clear()


class TestConfigureSdkLogging:
    def test_defaults_to_info(self, monkeypatch):
        monkeypatch.delenv("A2A_SDK_DEBUG", raising=False)
        get_a2a_config.cache_clear()
        configure_sdk_logging()
        assert logging.getLogger("a2a").level == logging.INFO

    def test_debug_when_sdk_debug_is_enabled(self, monkeypatch):
        monkeypatch.setenv("A2A_SDK_DEBUG", "true")
        get_a2a_config.cache_clear()
        try:
            configure_sdk_logging()
            assert logging.getLogger("a2a").level == logging.DEBUG
        finally:
            # Restore INFO so this test never leaks DEBUG-level a2a logging into
            # later tests in the same process.
            monkeypatch.setenv("A2A_SDK_DEBUG", "false")
            get_a2a_config.cache_clear()
            configure_sdk_logging()


class TestCapabilityCards:
    def test_capability_card_disables_push_notifications(self):
        card = build_capability_card()
        assert card.capabilities.streaming is True
        assert card.capabilities.push_notifications is False
        assert card.capabilities.extended_agent_card is True

    def test_placeholder_extended_card_also_disables_push_notifications(self):
        card = build_placeholder_extended_card()
        assert card.capabilities.push_notifications is False


class TestExtendedModifier:
    async def test_raises_when_scope_is_missing(self):
        ctx = ServerCallContext(state={})
        with pytest.raises(ExtendedAgentCardNotConfiguredError):
            await _extended_modifier(build_placeholder_extended_card(), ctx)

    async def test_builds_the_real_card_from_the_scope_snapshot(self, monkeypatch):
        """`_extended_modifier` imports `services.a2a_server.card_service` lazily
        (step_011); mock it out so this test does not depend on that module
        existing yet."""
        fake_card_service = SimpleNamespace(build_extended_card=MagicMock(return_value="the-real-card"))
        monkeypatch.setitem(sys.modules, "services.a2a_server.card_service", fake_card_service)

        scope = SimpleNamespace(snapshot="snap", base_url="https://example.test")
        ctx = ServerCallContext(state={"a2a": scope})

        result = await _extended_modifier(build_placeholder_extended_card(), ctx)

        assert result == "the-real-card"
        fake_card_service.build_extended_card.assert_called_once_with("snap", "https://example.test")


class TestPushNotificationsAreUnsupported:
    async def test_create_push_notification_config_raises(self):
        class _NeverCalledExecutor:
            async def execute(self, context, event_queue) -> None:
                raise AssertionError("executor must never run for an unsupported capability")

            async def cancel(self, context, event_queue) -> None:
                raise AssertionError("executor must never run for an unsupported capability")

        runtime: A2ARuntime = build_a2a_runtime(_NeverCalledExecutor())
        try:
            with pytest.raises(PushNotificationNotSupportedError):
                await runtime.handler.on_create_task_push_notification_config(
                    TaskPushNotificationConfig(task_id="task-1", url="https://example.test/callback"),
                    ServerCallContext(state={"headers": {"a2a-version": "1.0"}}),
                )
        finally:
            await runtime.handler.aclose()
