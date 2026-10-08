"""Unit coverage for `services.a2a_server.identity` (step_012, AD-3).

No DB, no SDK store -- pure string/dataclass logic plus the `User`/
`ServerCallContext` adapter types.
"""

from __future__ import annotations

import logging

import pytest
from a2a.auth.user import UnauthenticatedUser
from a2a.server.context import ServerCallContext
from pydantic import SecretStr

from services.a2a_server.identity import (
    A2ACallerUser,
    A2ACallScope,
    A2ARequestLog,
    context_for_owner,
    owner_for,
    owner_prefix,
    parse_owner,
    resolve_a2a_owner,
)

_KEY_HASH = "a" * 64


class TestOwnerForAndParse:
    def test_owner_for_builds_the_ad3_shape(self):
        assert owner_for(1, 2, _KEY_HASH) == f"a2a:1:2:{_KEY_HASH}"

    def test_parse_owner_round_trips(self):
        owner = owner_for(42, 7, _KEY_HASH)
        assert parse_owner(owner) == (42, 7, _KEY_HASH)

    @pytest.mark.parametrize(
        "owner",
        [
            "",
            "not-a2a",
            "a2a:1:2",  # missing key hash
            "a2a:1:2:tooshort",
            "a2a:x:2:" + _KEY_HASH,  # non-numeric app id
            "a2a:1:2:" + ("A" * 64),  # uppercase hex not allowed
        ],
    )
    def test_parse_owner_returns_none_for_malformed_input(self, owner):
        assert parse_owner(owner) is None

    @pytest.mark.parametrize(
        "app_id, agent_id, key_hash",
        [
            (1, 2, "tooshort"),
            (1, 2, "A" * 64),  # uppercase hex not allowed
            (1, 2, "g" * 64),  # non-hex char
        ],
    )
    def test_owner_for_raises_value_error_on_a_malformed_result(self, app_id, agent_id, key_hash):
        with pytest.raises(ValueError):
            owner_for(app_id, agent_id, key_hash)


class TestOwnerPrefix:
    def test_app_prefix_does_not_match_a_different_numeric_prefix(self):
        """`a2a:1:` must not match an owner for app 12 (`a2a:12:...`)."""
        prefix = owner_prefix(1)
        owner_for_app_12 = owner_for(12, 5, _KEY_HASH)
        assert not owner_for_app_12.startswith(prefix)

    def test_app_prefix_matches_every_owner_of_that_app(self):
        prefix = owner_prefix(1)
        assert owner_for(1, 5, _KEY_HASH).startswith(prefix)
        assert owner_for(1, 99, _KEY_HASH).startswith(prefix)

    def test_agent_prefix_is_narrower_than_app_prefix(self):
        app_prefix = owner_prefix(1)
        agent_prefix = owner_prefix(1, 5)
        assert agent_prefix.startswith(app_prefix)
        assert owner_for(1, 5, _KEY_HASH).startswith(agent_prefix)
        assert not owner_for(1, 6, _KEY_HASH).startswith(agent_prefix)


class TestA2ACallerUser:
    def test_is_authenticated_and_user_name(self):
        owner = owner_for(1, 2, _KEY_HASH)
        user = A2ACallerUser(owner)
        assert user.is_authenticated is True
        assert user.user_name == owner

    @pytest.mark.parametrize("owner", ["", "not-a2a", "a2a:1:2:tooshort"])
    def test_raises_value_error_for_a_malformed_owner(self, owner):
        with pytest.raises(ValueError):
            A2ACallerUser(owner)


class TestResolveA2AOwner:
    def test_resolves_the_owner_from_an_a2a_caller_user(self):
        owner = owner_for(1, 2, _KEY_HASH)
        ctx = ServerCallContext(user=A2ACallerUser(owner))
        assert resolve_a2a_owner(ctx) == owner

    def test_raises_for_any_other_user_type(self):
        ctx = ServerCallContext(user=UnauthenticatedUser())
        with pytest.raises(PermissionError):
            resolve_a2a_owner(ctx)


class TestContextForOwner:
    def test_builds_a_context_with_the_owner_and_version_header(self):
        owner = owner_for(1, 2, _KEY_HASH)
        ctx = context_for_owner(owner)
        assert isinstance(ctx.user, A2ACallerUser)
        assert ctx.user.user_name == owner
        assert ctx.state["headers"]["a2a-version"] == "1.0"


class TestA2ARequestLog:
    def test_emit_logs_one_line_with_caller_ids_via_extra(self, caplog):
        log = A2ARequestLog(method="SendMessage")
        log.task_id = "task-1"
        log.context_id = "ctx-1"
        log.conversation_id = 99
        log.outcome = "success"
        logger = logging.getLogger("test.a2a.request_log")
        with caplog.at_level(logging.INFO, logger="test.a2a.request_log"):
            log.emit(logger, app_id=7, agent_id=8, api_key_id=9)
        # Only this logger's records: unrelated asyncio GC warnings from
        # earlier tests can land in caplog at any time.
        records = [r for r in caplog.records if r.name == "test.a2a.request_log"]
        assert len(records) == 1
        record = records[0]
        message = record.getMessage()
        for expected in ("SendMessage", "task-1", "ctx-1", "99", "success", "app_id=7", "agent_id=8", "api_key_id=9"):
            assert expected in message
        # Structured fields are also attached via `extra=`, for log consumers
        # that parse LogRecord attributes rather than the formatted message.
        assert record.app_id == 7
        assert record.agent_id == 8
        assert record.api_key_id == 9
        assert record.outcome == "success"

    def test_emit_never_logs_a_key_or_a_hash(self, caplog):
        log = A2ARequestLog(method="SendMessage", outcome="success")
        logger = logging.getLogger("test.a2a.request_log.no_secrets")
        secret_hash = "f" * 64
        with caplog.at_level(logging.INFO, logger="test.a2a.request_log.no_secrets"):
            log.emit(logger, app_id=1, agent_id=2, api_key_id=3)
        records = [r for r in caplog.records if r.name == "test.a2a.request_log.no_secrets"]
        message = records[0].getMessage()
        assert secret_hash not in message
        assert "raw" not in message.lower()
        assert "hash" not in message.lower()


class TestA2ACallScopeSecretRedaction:
    def test_repr_never_leaks_the_raw_api_key(self):
        raw_key = "super-secret-raw-api-key-value"
        scope = A2ACallScope(
            app_id=1,
            app_slug="acme",
            agent_id=2,
            api_key_id=3,
            api_key_hash=_KEY_HASH,
            api_key=SecretStr(raw_key),
            snapshot=object(),
            request_log=A2ARequestLog(method="SendMessage"),
            base_url="https://example.test",
        )
        rendered = repr(scope)
        assert raw_key not in rendered
        assert raw_key not in str(scope)

    def test_repr_also_excludes_the_api_key_hash_snapshot_and_request_log(self):
        scope = A2ACallScope(
            app_id=1,
            app_slug="acme",
            agent_id=2,
            api_key_id=3,
            api_key_hash=_KEY_HASH,
            api_key=SecretStr("irrelevant"),
            snapshot=object(),
            request_log=A2ARequestLog(method="SendMessage"),
            base_url="https://example.test",
        )
        rendered = repr(scope)
        assert _KEY_HASH not in rendered
        assert "snapshot=" not in rendered
        assert "request_log=" not in rendered
        # The non-sensitive identifying fields are still visible.
        assert "app_id=1" in rendered
        assert "agent_id=2" in rendered
