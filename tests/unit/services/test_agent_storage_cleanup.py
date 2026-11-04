"""Unit tests for what deleting an agent frees outside the database."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.conversation_service import ConversationService


class TestReleaseAgentConversations:
    def test_frees_every_conversation_and_returns_its_thread(self):
        conversations = [SimpleNamespace(agent_id=7, session_id="conv_7_a"), SimpleNamespace(agent_id=7, session_id="conv_7_b")]
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = conversations
        with patch.object(ConversationService, "release_conversation_resources") as release:
            threads = ConversationService.release_agent_conversations(db, 7)

        assert threads == [(7, "conv_7_a"), (7, "conv_7_b")]
        assert release.call_count == 2


class TestDeleteThreadHistoriesInBackground:
    def test_nothing_to_delete(self):
        with patch.object(ConversationService, "delete_thread_history", AsyncMock()) as delete:
            ConversationService.delete_thread_histories_in_background([])
        delete.assert_not_called()

    def test_runs_inline_without_an_event_loop(self):
        with patch.object(ConversationService, "delete_thread_history", AsyncMock()) as delete:
            ConversationService.delete_thread_histories_in_background([(1, "s1"), (1, "s2")])
        assert delete.await_count == 2

    @pytest.mark.asyncio
    async def test_schedules_a_task_inside_an_event_loop(self):
        with patch.object(ConversationService, "delete_thread_history", AsyncMock()) as delete:
            ConversationService.delete_thread_histories_in_background([(1, "s1")])
            await asyncio.sleep(0)
            await asyncio.sleep(0)
        delete.assert_awaited_once_with(1, "s1")


class TestDeleteAgentStorage:
    def test_removes_only_this_agents_sessions_and_conversation_dirs(self, tmp_path):
        from services.file_management_service import FileManagementService

        persistent = tmp_path / "persistent"
        for name in ("agent_1_user_5_app_1", "agent_1_anonymous", "agent_12_user_5_app_1"):
            (persistent / name).mkdir(parents=True)
        conversation_dir = tmp_path / "conversations" / "42"
        conversation_dir.mkdir(parents=True)

        service = FileManagementService.__new__(FileManagementService)
        service._tmp_base_folder = str(tmp_path)
        service._persistent_dir = str(persistent)
        service.delete_agent_storage(1, [42])

        assert sorted(p.name for p in persistent.iterdir()) == ["agent_12_user_5_app_1"]
        assert not conversation_dir.exists()
