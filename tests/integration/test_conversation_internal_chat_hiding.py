"""Integration: ConversationService hides App Chat conversations by default and keeps every other kind (FR-13)."""

import pytest

from models.agent import AGENT_KIND_INTERNAL_CHAT
from models.conversation import Conversation, ConversationSource
from models.ocr_agent import OCRAgent
from models.scheduled_task import ScheduledTask
from services.conversation_service import ConversationService
from tests.factories import AIServiceFactory, AgentFactory, configure_factories
from utils.security import hash_api_key

API_KEY = "k" * 64


def _conv(db, agent, session_tag, **kw) -> Conversation:
    conv = Conversation(
        agent_id=agent.agent_id, session_id=f"conv_{agent.agent_id}_{session_tag}", title=session_tag,
        message_count=0, **kw,
    )
    db.add(conv)
    db.flush()
    return conv


@pytest.fixture
def agents(db, fake_app, fake_ai_service):
    configure_factories(db)
    standard = AgentFactory(app=fake_app, ai_service=fake_ai_service, name="std")
    internal = AgentFactory(
        app=fake_app, ai_service=AIServiceFactory(app=fake_app), name="__internal_chat__",
        kind=AGENT_KIND_INTERNAL_CHAT,
    )
    ocr = OCRAgent(
        name="ocr", description="", app_id=fake_app.app_id, service_id=fake_ai_service.service_id,
        vision_service_id=fake_ai_service.service_id, system_prompt="", has_memory=False, temperature=0.7,
    )
    db.add(ocr)
    db.flush()
    return standard, internal, ocr


def test_default_keeps_standard_ocr_scheduled_and_api_key_conversations(db, fake_app, fake_user, agents):
    standard, _, ocr = agents
    task = ScheduledTask(
        name="t", agent_id=standard.agent_id, app_id=fake_app.app_id, created_by=fake_user.user_id,
        orchestrator_schedule_name="sched-hide-1", cron_expression="*/5 * * * *", input={"message": "hi"},
    )
    db.add(task)
    db.flush()

    user_ctx = {"user_id": fake_user.user_id}
    std_conv = _conv(db, standard, "std", user_id=fake_user.user_id)
    ocr_conv = _conv(db, ocr, "ocr", user_id=fake_user.user_id)
    sched_conv = _conv(db, standard, "sched", scheduled_task_id=task.id, source=ConversationSource.SCHEDULED_TASK)
    key_conv = _conv(db, standard, "key", api_key_hash=hash_api_key(API_KEY), source=ConversationSource.API)

    get = ConversationService.get_conversation
    assert get(db, std_conv.conversation_id, user_ctx) is std_conv
    assert get(db, ocr_conv.conversation_id, user_ctx) is ocr_conv
    assert get(db, sched_conv.conversation_id, {"scheduled_task_id": task.id}) is sched_conv
    assert get(db, key_conv.conversation_id, {"api_key": API_KEY}) is key_conv

    listed, total = ConversationService.list_conversations(db, standard.agent_id, user_ctx)
    assert {c.conversation_id for c in listed} == {std_conv.conversation_id} and total == 1
    listed, _ = ConversationService.list_conversations(db, standard.agent_id, {"api_key": API_KEY})
    assert [c.conversation_id for c in listed] == [key_conv.conversation_id]
    listed, _ = ConversationService.list_conversations(db, ocr.agent_id, user_ctx)
    assert [c.conversation_id for c in listed] == [ocr_conv.conversation_id]


def test_internal_chat_conversation_hidden_by_default_returned_with_flag(db, fake_user, agents):
    _, internal, _ = agents
    user_ctx = {"user_id": fake_user.user_id}
    chat = _conv(db, internal, "chat", user_id=fake_user.user_id, source=ConversationSource.INTERNAL_CHAT)
    # Same internal agent but a (wrongly) non-INTERNAL_CHAT source: hidden by the owning-agent rule too.
    odd = _conv(db, internal, "odd", user_id=fake_user.user_id)

    for conv in (chat, odd):
        assert ConversationService.get_conversation(db, conv.conversation_id, user_ctx) is None
        assert ConversationService.get_conversation(
            db, conv.conversation_id, user_ctx, agent_id=internal.agent_id
        ) is None
    assert ConversationService.list_conversations(db, internal.agent_id, user_ctx) == ([], 0)

    found = ConversationService.get_conversation(
        db, chat.conversation_id, user_ctx, agent_id=internal.agent_id, include_internal_chat=True
    )
    assert found is chat
    listed, total = ConversationService.list_conversations(
        db, internal.agent_id, user_ctx, include_internal_chat=True
    )
    assert total == 2 and {c.conversation_id for c in listed} == {chat.conversation_id, odd.conversation_id}


class TestIncrementMessageCount:
    """``increment_message_count`` is an atomic UPDATE shared by every channel, not only the Chat."""

    def test_increments_and_stores_a_200_char_preview(self, db, agents, fake_user):
        standard, _, _ = agents
        conv = _conv(db, standard, "count", user_id=fake_user.user_id)

        ConversationService.increment_message_count(db, conv.conversation_id, last_message="x" * 250, increment_by=2)
        ConversationService.increment_message_count(db, conv.conversation_id)

        db.refresh(conv)
        assert conv.message_count == 3
        assert conv.last_message == "x" * 200  # the second call has no preview and keeps the first one

    def test_does_not_overwrite_a_count_changed_elsewhere(self, db, agents, fake_user):
        """The loaded instance is stale on purpose: the UPDATE must add to the stored value, not to the cached one."""
        standard, _, _ = agents
        conv = _conv(db, standard, "stale", user_id=fake_user.user_id)
        db.query(Conversation).filter(Conversation.conversation_id == conv.conversation_id).update(
            {"message_count": 10}, synchronize_session=False
        )

        ConversationService.increment_message_count(db, conv.conversation_id, increment_by=2)

        db.refresh(conv)
        assert conv.message_count == 12

    def test_missing_conversation_is_a_no_op(self, db):
        ConversationService.increment_message_count(db, 999_999_999, last_message="hi")
