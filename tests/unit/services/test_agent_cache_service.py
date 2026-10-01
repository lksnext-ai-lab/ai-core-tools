"""Unit tests for agent_cache_service — checkpoint-recovery helpers.

Providers reject a checkpoint with a dangling tool_calls entry (an
AIMessage whose tool call never got a matching ToolMessage — e.g. the
backend crashed mid-tool-execution) with different wording depending on the
exact API surface hit. This must be detected reliably so the
fork-from-prior-checkpoint recovery in agent_execution_service.py and
agent_streaming_service.py actually triggers, and the checkpoint it forks
from must actually be a *safe* one to resume from.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.agent_cache_service import (
    CheckpointerCacheService,
    is_missing_tool_output_error,
)


def _msg(msg_type: str, tool_calls=None, tool_call_id=None):
    return SimpleNamespace(type=msg_type, tool_calls=tool_calls, tool_call_id=tool_call_id)


def _checkpoint_tuple(checkpoint_id: str, messages: list):
    return SimpleNamespace(
        checkpoint={"channel_values": {"messages": messages}},
        config={"configurable": {"checkpoint_id": checkpoint_id}},
    )


class TestIsMissingToolOutputError:
    def test_matches_legacy_phrasing(self):
        exc = RuntimeError(
            "Error code: 400 - No tool output found for function call call_stale"
        )
        assert is_missing_tool_output_error(exc) is True

    def test_matches_live_openai_chat_completions_phrasing(self):
        """Live-reproduced against OpenAI (gpt-4o-mini): kill the backend
        mid-tool-call, resume the same conversation — this is the exact
        error text raised. The legacy substring alone does not match it."""
        exc = RuntimeError(
            "Error code: 400 - {'error': {'message': \"An assistant message "
            "with 'tool_calls' must be followed by tool messages responding "
            "to each 'tool_call_id'. The following tool_call_ids did not "
            "have response messages: call_VtLW6LSES2D4RbPdAZ5yQDC5\", "
            "'type': 'invalid_request_error', 'param': 'messages.[5].role', "
            "'code': None}}"
        )
        assert is_missing_tool_output_error(exc) is True

    def test_unrelated_error_does_not_match(self):
        exc = RuntimeError("Error code: 401 - invalid API key")
        assert is_missing_tool_output_error(exc) is False


class TestGetRollbackCheckpointId:
    """Live-reproduced bug: killing the backend mid-tool-call left TWO
    consecutive checkpoints ending in the same dangling AIMessage (one
    from the model node adding the tool_calls, another from the tools
    node beginning execution before being interrupted). Naively rolling
    back exactly one checkpoint replayed the exact same broken state and
    failed identically. The fix must walk back past every checkpoint
    still carrying a pending tool call, not just the immediate
    predecessor."""

    @staticmethod
    def _patch_checkpointer(checkpoints: list):
        async def _alist(config, limit=None):
            for cp in checkpoints[: limit or len(checkpoints)]:
                yield cp

        checkpointer = MagicMock()
        checkpointer.alist = _alist
        return patch.object(
            CheckpointerCacheService,
            "get_async_checkpointer",
            new=AsyncMock(return_value=checkpointer),
        )

    @pytest.mark.asyncio
    async def test_skips_multiple_checkpoints_still_holding_the_pending_tool_call(self):
        pending_tool_calls = [{"id": "call_abc", "name": "Bash", "args": {}}]
        checkpoints = [
            _checkpoint_tuple("cp-4-broken", [_msg("human"), _msg("ai", pending_tool_calls)]),
            _checkpoint_tuple("cp-3-also-broken", [_msg("human"), _msg("ai", pending_tool_calls)]),
            _checkpoint_tuple("cp-2-clean", [_msg("human")]),
            _checkpoint_tuple("cp-1-clean", []),
        ]

        with self._patch_checkpointer(checkpoints):
            result = await CheckpointerCacheService.get_rollback_checkpoint_id(1, "sess")

        assert result == "cp-2-clean"

    @pytest.mark.asyncio
    async def test_skips_checkpoint_with_unresolved_tool_call_sandwiched_mid_list(self):
        """Live-reproduced: a first retry attempt appended a fresh
        HumanMessage on top of an already-broken state instead of fixing
        it, so the *newest* checkpoints all end in a clean HumanMessage
        while the original unresolved AIMessage(tool_calls=...) still
        sits earlier in the same list with no ToolMessage ever inserted
        after it. Checking only the tail message (the original,
        insufficient implementation) wrongly treated these as safe and
        replayed the same broken list, failing identically."""
        pending_tool_calls = [{"id": "call_orig", "name": "Bash", "args": {}}]
        checkpoints = [
            _checkpoint_tuple(
                "cp-3-looks-clean-but-isnt",
                [
                    _msg("human"),
                    _msg("ai"),
                    _msg("human"),
                    _msg("ai", pending_tool_calls),  # never answered below
                    _msg("human"),  # a retry's new message, appended on top
                ],
            ),
            _checkpoint_tuple(
                "cp-2-also-looks-clean-but-isnt",
                [
                    _msg("human"),
                    _msg("ai"),
                    _msg("human"),
                    _msg("ai", pending_tool_calls),
                    _msg("human"),
                ],
            ),
            _checkpoint_tuple(
                "cp-1-genuinely-clean",
                [_msg("human"), _msg("ai"), _msg("human")],
            ),
        ]

        with self._patch_checkpointer(checkpoints):
            result = await CheckpointerCacheService.get_rollback_checkpoint_id(1, "sess")

        assert result == "cp-1-genuinely-clean"

    @pytest.mark.asyncio
    async def test_resolved_tool_call_mid_list_is_considered_clean(self):
        """An AIMessage(tool_calls=...) that *does* have a matching
        ToolMessage later in the list is a normal, healthy turn and must
        not be treated as broken."""
        checkpoints = [
            _checkpoint_tuple("cp-2-not-inspected", [_msg("human"), _msg("ai")]),
            _checkpoint_tuple(
                "cp-1-healthy-tool-turn",
                [
                    _msg("human"),
                    _msg("ai", [{"id": "call_ok", "name": "Bash", "args": {}}]),
                    _msg("tool", tool_call_id="call_ok"),
                    _msg("ai"),
                ],
            ),
        ]

        with self._patch_checkpointer(checkpoints):
            result = await CheckpointerCacheService.get_rollback_checkpoint_id(1, "sess")

        assert result == "cp-1-healthy-tool-turn"

    @pytest.mark.asyncio
    async def test_returns_immediate_predecessor_when_it_is_already_clean(self):
        checkpoints = [
            _checkpoint_tuple(
                "cp-2-broken",
                [_msg("human"), _msg("ai", [{"id": "call_x", "name": "Bash", "args": {}}])],
            ),
            _checkpoint_tuple("cp-1-clean", [_msg("human"), _msg("ai")]),
        ]

        with self._patch_checkpointer(checkpoints):
            result = await CheckpointerCacheService.get_rollback_checkpoint_id(1, "sess")

        assert result == "cp-1-clean"

    @pytest.mark.asyncio
    async def test_returns_none_when_every_checkpoint_is_still_broken(self):
        pending_tool_calls = [{"id": "call_abc", "name": "Bash", "args": {}}]
        checkpoints = [
            _checkpoint_tuple("cp-2-broken", [_msg("ai", pending_tool_calls)]),
            _checkpoint_tuple("cp-1-also-broken", [_msg("ai", pending_tool_calls)]),
        ]

        with self._patch_checkpointer(checkpoints):
            result = await CheckpointerCacheService.get_rollback_checkpoint_id(1, "sess")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_with_fewer_than_two_checkpoints(self):
        checkpoints = [_checkpoint_tuple("cp-1-only", [_msg("human")])]

        with self._patch_checkpointer(checkpoints):
            result = await CheckpointerCacheService.get_rollback_checkpoint_id(1, "sess")

        assert result is None
