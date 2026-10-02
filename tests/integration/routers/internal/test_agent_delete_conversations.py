"""
Integration tests: deleting an agent that has conversations.

Regression: DELETE /internal/apps/{app_id}/agents/{agent_id} returned 500 for any agent
with a Conversation row, because the ORM tried ``UPDATE "Conversation" SET agent_id=NULL``
on a NOT NULL column. The agent's conversations must now be deleted together with their
LangGraph checkpoints and file storage, leaving no orphan rows.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from sqlalchemy import text


def _conversation(db, agent, user=None, **kwargs):
    from models.conversation import Conversation

    conversation = Conversation(
        agent_id=agent.agent_id,
        user_id=user.user_id if user else None,
        session_id=f"session-{uuid.uuid4().hex}",
        title="Chat",
        **kwargs,
    )
    db.add(conversation)
    db.flush()
    return conversation


class TestDeleteAgentWithConversations:
    """DELETE /internal/apps/{app_id}/agents/{agent_id} with Conversation rows."""

    @pytest.fixture(autouse=True)
    def _editor_platform_role(self, fake_user, db):
        # fake_user's platform_role defaults to 'viewer', which require_editor_for_writes blocks.
        fake_user.platform_role = "editor"
        db.flush()

    def test_delete_agent_with_conversations_returns_200_and_leaves_no_orphans(
        self, client, fake_app, fake_agent, fake_user, owner_headers, db
    ):
        from models.agent import Agent
        from models.conversation import Conversation
        from services.file_management_service import FileManagementService

        agent_id = fake_agent.agent_id
        first = _conversation(db, fake_agent, fake_user)
        second = _conversation(db, fake_agent, fake_user, sandbox_session_id="sbx-1", sandbox_state="{}")
        threads = {(agent_id, first.session_id), (agent_id, second.session_id)}

        with patch(
            "services.conversation_service.CheckpointerCacheService.invalidate_checkpointer_async",
            new_callable=AsyncMock,
        ) as invalidate, patch.object(FileManagementService, "delete_agent_storage") as delete_storage:
            response = client.delete(
                f"/internal/apps/{fake_app.app_id}/agents/{agent_id}",
                headers=owner_headers,
            )

        assert response.status_code == 200, response.text
        db.expire_all()
        assert db.query(Agent).filter(Agent.agent_id == agent_id).first() is None
        assert db.query(Conversation).filter(Conversation.agent_id == agent_id).count() == 0
        # Checkpoints of every conversation thread are purged.
        purged = {(c.kwargs["agent_id"], c.kwargs["session_id"]) for c in invalidate.await_args_list}
        assert purged == threads
        delete_storage.assert_called_once()
        assert delete_storage.call_args.args[0] == agent_id
        assert sorted(delete_storage.call_args.args[1]) == sorted([first.conversation_id, second.conversation_id])

    def test_delete_agent_keeps_other_agents_conversations(
        self, client, fake_app, fake_agent, fake_ai_service, fake_user, owner_headers, db
    ):
        from models.agent import Agent
        from models.conversation import Conversation

        other = Agent(name="Other", app_id=fake_app.app_id, service_id=fake_ai_service.service_id)
        db.add(other)
        db.flush()
        _conversation(db, fake_agent, fake_user)
        kept = _conversation(db, other, fake_user)

        with patch(
            "services.conversation_service.CheckpointerCacheService.invalidate_checkpointer_async",
            new_callable=AsyncMock,
        ):
            response = client.delete(
                f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}",
                headers=owner_headers,
            )

        assert response.status_code == 200, response.text
        db.expire_all()
        assert db.query(Conversation).filter(Conversation.conversation_id == kept.conversation_id).count() == 1

    def test_conversation_agent_fk_cascades_on_delete(self, fake_agent, fake_user, db):
        """DB-level backstop: deleting the Agent row removes its conversations."""
        conversation = _conversation(db, fake_agent, fake_user)

        db.execute(text('DELETE FROM "Agent" WHERE agent_id = :id'), {"id": fake_agent.agent_id})

        remaining = db.execute(
            text('SELECT count(*) FROM "Conversation" WHERE conversation_id = :id'),
            {"id": conversation.conversation_id},
        ).scalar()
        assert remaining == 0


class TestDeleteAgentStorage:
    """FileManagementService.delete_agent_storage removes only the deleted agent's files."""

    def test_removes_agent_sessions_and_conversation_dirs(self, tmp_path):
        from services.file_management_service import FileManagementService

        service = FileManagementService.__new__(FileManagementService)
        service._files = {"agent_7_user_1_app_1_conv_3": {}, "agent_70_user_1_app_1": {}}
        service._tmp_base_folder = str(tmp_path)
        service._persistent_dir = str(tmp_path / "persistent")
        for name in ("agent_7_user_1_app_1_conv_3", "agent_7_user_2_app_1", "agent_70_user_1_app_1"):
            (tmp_path / "persistent" / name).mkdir(parents=True)
        (tmp_path / "conversations" / "3").mkdir(parents=True)
        (tmp_path / "conversations" / "4").mkdir(parents=True)

        service.delete_agent_storage(7, [3])

        assert sorted(p.name for p in (tmp_path / "persistent").iterdir()) == ["agent_70_user_1_app_1"]
        assert sorted(p.name for p in (tmp_path / "conversations").iterdir()) == ["4"]
        assert list(service._files) == ["agent_70_user_1_app_1"]
