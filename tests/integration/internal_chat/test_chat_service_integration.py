"""Integration (real PostgreSQL): InternalChatService, resolver and repositories (spec app-flexible-chat step_007)."""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy as sa
from sqlalchemy import event

from models.agent import Agent
from models.ai_service import AIService
from models.app import App
from models.conversation import Conversation, ConversationSource
from models.embedding_service import EmbeddingService
from models.internal_chat import ChatConversationState, ChatUserDefault, ConversationTurn
from models.mcp_config import MCPConfig
from models.silo import Silo
from models.skill import Skill
from models.repository import Repository
from models.user import User
from repositories.internal_chat_repository import InternalChatAgentRepository
from schemas.internal_chat_schemas import ChatSelection
from services.agent_execution_context import TurnCompleted
from services.conversation_service import ConversationService
from services.internal_chat.chat_service import InternalChatService
from services.internal_chat.errors import ChatResourceNotFoundError
from utils.service_lifecycle import ServiceRetiredError
from utils.error_handlers import ValidationError

PROMPT = "system prompt"


def _user(db, email):
    u = User(email=email, name=email, is_active=True, platform_role="editor")
    db.add(u)
    db.flush()
    return u


def _app(db, owner, slug):
    a = App(name=slug, slug=slug, owner_id=owner.user_id, agent_rate_limit=0, max_file_size_mb=10)
    db.add(a)
    db.flush()
    return a


def _ai(db, app_id, name="svc", eos=None):
    s = AIService(name=name, provider="OpenAI", api_key="k", app_id=app_id, description="gpt-x", end_of_service_at=eos)
    db.add(s)
    db.flush()
    return s


@pytest.fixture
def world(db):
    alice, bob = _user(db, "alice-ic@test.com"), _user(db, "bob-ic@test.com")
    app, other = _app(db, alice, "ic-app"), _app(db, bob, "ic-other")
    emb = EmbeddingService(name="emb", provider="OpenAI", app_id=app.app_id)
    db.add(emb)
    db.flush()
    return {
        "alice": alice, "bob": bob, "app": app, "other": other, "emb": emb,
        "ai": _ai(db, app.app_id), "other_ai": _ai(db, other.app_id, "foreign"),
    }


def svc(db, user):
    return InternalChatService(db, {"user_id": user.user_id, "email": user.email})


def test_get_or_create_is_idempotent_and_unexposed(db, world):
    app_id = world["app"].app_id
    first = InternalChatAgentRepository.get_or_create(db, app_id, PROMPT)
    assert InternalChatAgentRepository.get_or_create(db, app_id, PROMPT) == first
    agent = db.get(Agent, first)
    assert agent.kind == "internal_chat" and agent.has_memory is True
    assert agent.is_tool is False and agent.a2a_enabled is False and agent.enable_code_interpreter is False
    assert agent.marketplace_visibility.name == "UNPUBLISHED"
    assert agent.rag_fixed_filters == [] and agent.service_id is None and agent.silo_id is None
    assert db.query(Agent).filter(Agent.app_id == app_id, Agent.kind == "internal_chat").count() == 1


def test_get_or_create_race_loser_rereads_winner(db, world):
    app_id = world["app"].app_id
    winner = InternalChatAgentRepository.get_or_create(db, app_id, PROMPT)
    real = InternalChatAgentRepository.get_id
    calls = iter([None])  # the loser's first SELECT saw nothing; the INSERT conflicts; re-SELECT finds the winner

    def wrapped(d, a):
        try:
            return next(calls)
        except StopIteration:
            return real(d, a)

    with patch.object(InternalChatAgentRepository, "get_id", side_effect=wrapped):
        assert InternalChatAgentRepository.get_or_create(db, app_id, PROMPT) == winner
    assert db.query(Agent).filter(Agent.app_id == app_id, Agent.kind == "internal_chat").count() == 1


def test_invalid_selection_creates_nothing(db, world):
    s = svc(db, world["alice"])
    before = db.query(Conversation).count()
    agents = db.query(Agent).filter(Agent.kind == "internal_chat").count()
    for bad in (
        ChatSelection(ai_service_id=world["other_ai"].service_id),
        ChatSelection(ai_service_id=world["ai"].service_id, silo_id=987654),
        ChatSelection(ai_service_id=world["ai"].service_id, skill_ids=[987654]),
        ChatSelection(ai_service_id=world["ai"].service_id, mcp_config_ids=[987654]),
    ):
        with pytest.raises(ChatResourceNotFoundError) as exc:
            s.prepare_turn(world["app"].app_id, bad)
        assert exc.value.message == "Resource not found" and exc.value.status_code == 404
    assert db.query(Conversation).count() == before
    assert db.query(Agent).filter(Agent.kind == "internal_chat").count() == agents


def test_retired_ai_service_raises_service_retired(db, world):
    retired = _ai(db, world["app"].app_id, "old", eos=datetime.utcnow() - timedelta(days=2))
    with pytest.raises(ServiceRetiredError):
        svc(db, world["alice"]).prepare_turn(world["app"].app_id, ChatSelection(ai_service_id=retired.service_id))


def test_other_apps_silo_skill_mcp_are_not_found(db, world):
    other_id = world["other"].app_id
    foreign_emb = EmbeddingService(name="foreign-emb", provider="OpenAI", app_id=other_id)
    db.add(foreign_emb)
    db.flush()
    # A fully working silo (embedding service present): the only reason to reject it is its App.
    silo = Silo(name="s", app_id=other_id, embedding_service_id=foreign_emb.service_id)
    skill = Skill(name="foreign-skill", content="x", app_id=other_id)
    mcp = MCPConfig(name="m", config={"a": {"url": "http://x"}}, app_id=other_id)
    db.add_all([silo, skill, mcp])
    db.flush()
    s = svc(db, world["alice"])
    ai = world["ai"].service_id
    for sel in (
        ChatSelection(ai_service_id=ai, silo_id=silo.silo_id),
        ChatSelection(ai_service_id=ai, skill_ids=[skill.skill_id]),
        ChatSelection(ai_service_id=ai, mcp_config_ids=[mcp.config_id]),
    ):
        with pytest.raises(ChatResourceNotFoundError):
            s.prepare_turn(world["app"].app_id, sel)


def test_prepare_turn_resolves_full_selection_and_creates_conversation(db, world):
    app_id = world["app"].app_id
    silo = Silo(name="kb", app_id=app_id, embedding_service_id=world["emb"].service_id)
    skill = Skill(name="my-skill", content="do it", app_id=app_id)
    good = MCPConfig(name="good", config={"srv": {"url": "http://x", "transport": "streamable_http"}}, app_id=app_id)
    bad = MCPConfig(name="bad", config="{not json", app_id=app_id)
    db.add_all([silo, skill, good, bad])
    db.flush()
    prepared = svc(db, world["alice"]).prepare_turn(
        app_id,
        ChatSelection(
            ai_service_id=world["ai"].service_id, silo_id=silo.silo_id, skill_ids=[skill.skill_id, skill.skill_id],
            mcp_config_ids=[good.config_id, bad.config_id],
        ),
    )
    cfg = prepared.turn_config
    assert (cfg.ai_service_is_system, cfg.ai_service_provider, cfg.ai_service_model) == (False, "OpenAI", "gpt-x")
    assert cfg.silo_id == silo.silo_id and cfg.skill_ids == (skill.skill_id,)
    assert cfg.mcp_config_ids == (good.config_id,)  # the broken config degrades silently
    conv = prepared.conversation
    assert conv.source == ConversationSource.INTERNAL_CHAT and conv.title is None
    assert conv.user_id == world["alice"].user_id
    assert prepared.user_context["app_id"] == app_id and prepared.user_context["caller_type_override"] == "INTERNAL_CHAT"
    state = db.get(ChatConversationState, conv.conversation_id)
    assert state is not None and state.app_id == app_id and state.selection["ai_service_id"] == world["ai"].service_id


def test_conversation_source_and_agent_kind_are_tied(db, world):
    app_id = world["app"].app_id
    agent_id = InternalChatAgentRepository.get_or_create(db, app_id, PROMPT)
    ctx = {"user_id": world["alice"].user_id}
    with pytest.raises(ValidationError):
        ConversationService.create_conversation(db, agent_id, ctx)  # default PLAYGROUND source on the hidden agent
    normal = Agent(name="n", app_id=app_id, has_memory=False)
    db.add(normal)
    db.flush()
    with pytest.raises(ValidationError):
        ConversationService.create_conversation(db, normal.agent_id, ctx, source=ConversationSource.INTERNAL_CHAT)


async def _complete(service, prepared, mid):
    """Run the hook the router would pass to the execution stack."""
    return await prepared.on_turn_completed(
        TurnCompleted(
            conversation_id=prepared.conversation.conversation_id, assistant_message_id=mid,
            user_context=prepared.user_context, turn_config=prepared.turn_config,
        )
    )


async def test_turns_indexes_state_and_per_user_defaults(db, world):
    app_id = world["app"].app_id
    alice, bob = svc(db, world["alice"]), svc(db, world["bob"])
    p1 = alice.prepare_turn(app_id, ChatSelection(ai_service_id=world["ai"].service_id))
    t1 = await _complete(alice, p1, "m1")
    p2 = alice.prepare_turn(app_id, ChatSelection(ai_service_id=world["ai"].service_id), p1.conversation.conversation_id)
    t2 = await _complete(alice, p2, "m2")
    assert (t1["turn_index"], t2["turn_index"]) == (1, 2)
    rows = db.query(ConversationTurn).filter_by(conversation_id=p1.conversation.conversation_id).all()
    assert {r.app_id for r in rows} == {app_id} and {r.user_id for r in rows} == {world["alice"].user_id}

    default = db.get(ChatUserDefault, (world["alice"].user_id, app_id))
    assert default.selection["ai_service_id"] == world["ai"].service_id
    assert db.get(ChatUserDefault, (world["bob"].user_id, app_id)) is None  # bob untouched
    first_updated = default.updated_at
    await _complete(alice, p2, "m3")
    db.refresh(default)
    assert default.updated_at >= first_updated

    # Bob can neither load nor reuse alice's conversation, and the failure is the generic one.
    with pytest.raises(ChatResourceNotFoundError):
        bob.prepare_turn(app_id, ChatSelection(ai_service_id=world["ai"].service_id), p1.conversation.conversation_id)
    with pytest.raises(ChatResourceNotFoundError):
        await bob.get_conversation_detail(app_id, p1.conversation.conversation_id)
    assert bob.list_conversations(app_id) == ([], 0)
    assert alice.list_conversations(app_id)[1] == 1


async def test_turn_index_allocation_locks_state_row_before_max(db, world):
    app_id = world["app"].app_id
    alice = svc(db, world["alice"])
    p = alice.prepare_turn(app_id, ChatSelection(ai_service_id=world["ai"].service_id))
    statements = []

    def capture(conn, cursor, statement, *a):
        statements.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", capture)
    try:
        await _complete(alice, p, "m1")
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", capture)
    lock_pos = next(i for i, s in enumerate(statements) if "FOR UPDATE" in s and "chat_conversation_state" in s)
    max_pos = next(i for i, s in enumerate(statements) if "max(conversation_turn.turn_index)" in s)
    assert lock_pos < max_pos


async def test_rename_reset_delete_and_detail(db, world):
    app_id = world["app"].app_id
    alice = svc(db, world["alice"])
    p = alice.prepare_turn(app_id, ChatSelection(ai_service_id=world["ai"].service_id))
    cid = p.conversation.conversation_id
    await _complete(alice, p, "m1")
    assert alice.rename_conversation(app_id, cid, "Hello").title == "Hello"

    async def history(*a, **k):
        return [{"role": "user", "content": "q", "message_id": "u1"}, {"role": "agent", "content": "a", "message_id": "m1"}]

    with patch.object(ConversationService, "history_of_conversation", new=history), \
         patch.object(ConversationService, "pending_approval_of_conversation", new=lambda *a, **k: None):
        detail = await alice.get_conversation_detail(app_id, cid)
    assert detail.messages[0]["turn"] is None and detail.messages[1]["turn"].turn_index == 1
    assert detail.current_selection.ai_service_id == world["ai"].service_id and detail.warnings == []

    with patch.object(ConversationService, "delete_thread_history", new=AsyncMock()), \
         patch("services.file_management_service.FileManagementService.remove_all_attached_files", new=AsyncMock(return_value=0)):
        await alice.reset_conversation(app_id, cid)
    assert db.query(ConversationTurn).filter_by(conversation_id=cid).count() == 0

    with patch.object(ConversationService, "delete_thread_history", new=AsyncMock()):
        await alice.delete_conversation(app_id, cid)
    assert db.get(ChatConversationState, cid) is None


async def test_stale_state_is_sanitized_not_an_error(db, world):
    app_id = world["app"].app_id
    alice = svc(db, world["alice"])
    p = alice.prepare_turn(app_id, ChatSelection(ai_service_id=world["ai"].service_id))
    state = db.get(ChatConversationState, p.conversation.conversation_id)
    state.selection = {"ai_service_id": world["ai"].service_id, "silo_id": 424242, "skill_ids": [1234567], "mcp_config_ids": []}
    db.flush()

    async def history(*a, **k):
        return []

    with patch.object(ConversationService, "history_of_conversation", new=history), \
         patch.object(ConversationService, "pending_approval_of_conversation", new=lambda *a, **k: None):
        detail = await alice.get_conversation_detail(app_id, p.conversation.conversation_id)
    assert detail.current_selection == ChatSelection(ai_service_id=world["ai"].service_id)
    assert {(w.kind, w.id) for w in detail.warnings} == {("silo", 424242), ("skill", 1234567)}


def _count_queries(db, fn):
    n = []
    def cap(conn, cursor, statement, *a):
        n.append(statement)
    event.listen(db.get_bind(), "before_cursor_execute", cap)
    try:
        fn()
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", cap)
    return len(n)


def test_options_query_count_is_independent_of_data_volume(db, world):
    app_id = world["app"].app_id
    alice = svc(db, world["alice"])
    # one of each (queries for the optional source lookups only run when there are silos)
    db.add_all([
        Silo(name="first", app_id=app_id, embedding_service_id=world["emb"].service_id),
        Skill(name="first-sk", content="c", app_id=app_id),
        MCPConfig(name="first-mc", config={"a": {}}, app_id=app_id),
    ])
    db.flush()
    db.expire_all()
    base = _count_queries(db, lambda: alice.get_options(app_id))
    for i in range(6):
        _ai(db, app_id, f"extra{i}")
        db.add_all([
            Silo(name=f"silo{i}", app_id=app_id, embedding_service_id=world["emb"].service_id),
            Skill(name=f"sk{i}", content="c", app_id=app_id),
            MCPConfig(name=f"mc{i}", config={"a": {}}, app_id=app_id),
        ])
    db.flush()
    db.expire_all()
    more = _count_queries(db, lambda: alice.get_options(app_id))
    assert more == base
    opts = alice.get_options(app_id)
    assert len(opts.ai_services) >= 7 and len(opts.silos) == 7 and opts.has_usable_model
    assert opts.default_selection.ai_service_id == world["ai"].service_id  # app default: first by service_id
    assert all(o.name != "foreign" for o in opts.ai_services)


# --------------------------------------------------------------------------------------------------
# Isolation (item 11)
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("bad_user", [None, True, "abc", "apikey_1", 1.5])
async def test_contexts_without_numeric_user_id_get_not_found(db, world, bad_user):
    app_id = world["app"].app_id
    s = InternalChatService(db, {"user_id": bad_user})
    sel = ChatSelection(ai_service_id=world["ai"].service_id)
    with pytest.raises(ChatResourceNotFoundError):
        s.prepare_turn(app_id, sel)
    with pytest.raises(ChatResourceNotFoundError):
        s.create_conversation(app_id)
    with pytest.raises(ChatResourceNotFoundError):
        s.rename_conversation(app_id, 1, "x")
    with pytest.raises(ChatResourceNotFoundError):
        await s.get_conversation_detail(app_id, 1)
    assert s.list_conversations(app_id) == ([], 0)


async def test_other_users_conversation_and_wrong_app_are_not_found(db, world):
    app_id = world["app"].app_id
    alice, bob = svc(db, world["alice"]), svc(db, world["bob"])
    sel = ChatSelection(ai_service_id=world["ai"].service_id)
    cid = alice.prepare_turn(app_id, sel).conversation.conversation_id
    # the other App also has its internal agent, so "wrong App" is a real mismatch, not "no agent"
    InternalChatAgentRepository.get_or_create(db, world["other"].app_id, PROMPT)

    with pytest.raises(ChatResourceNotFoundError):
        bob.prepare_turn(app_id, sel, cid)
    with pytest.raises(ChatResourceNotFoundError):
        bob.rename_conversation(app_id, cid, "mine now")
    with pytest.raises(ChatResourceNotFoundError):
        await bob.get_conversation_detail(app_id, cid)
    with pytest.raises(ChatResourceNotFoundError):
        await bob.reset_conversation(app_id, cid)
    # same owner, wrong App
    other_app = world["other"].app_id
    with pytest.raises(ChatResourceNotFoundError):
        alice.prepare_turn(other_app, ChatSelection(ai_service_id=world["other_ai"].service_id), cid)
    with pytest.raises(ChatResourceNotFoundError):
        alice.rename_conversation(other_app, cid, "x")
    with pytest.raises(ChatResourceNotFoundError):
        await alice.get_conversation_detail(other_app, cid)


def test_retired_ai_service_of_another_app_is_not_found_not_retired(db, world):
    foreign_retired = _ai(db, world["other"].app_id, "old-foreign", eos=datetime.utcnow() - timedelta(days=2))
    with pytest.raises(ChatResourceNotFoundError):
        svc(db, world["alice"]).prepare_turn(
            world["app"].app_id, ChatSelection(ai_service_id=foreign_retired.service_id)
        )


# --------------------------------------------------------------------------------------------------
# Review round: skipped MCP, atomic creation, reset, in-flight turns, locks, filters, skills
# --------------------------------------------------------------------------------------------------


def _bad_mcp(db, app_id):
    cfg = MCPConfig(name="bad", config="{not json", app_id=app_id)
    db.add(cfg)
    db.flush()
    return cfg


async def test_skipped_mcp_stays_in_default_and_state_but_not_in_turn(db, world):
    app_id = world["app"].app_id
    bad = _bad_mcp(db, app_id)
    alice = svc(db, world["alice"])
    p = alice.prepare_turn(app_id, ChatSelection(ai_service_id=world["ai"].service_id, mcp_config_ids=[bad.config_id]))
    assert [(w.kind, w.id) for w in p.warnings] == [("mcp_config", bad.config_id)]
    assert p.turn_config.mcp_config_ids == ()
    payload = await _complete(alice, p, "m1")
    assert payload["warnings"] == [{"kind": "mcp_config", "id": bad.config_id}] and payload["mcp_configs"] == []
    cid = p.conversation.conversation_id
    assert db.get(ChatConversationState, cid).selection["mcp_config_ids"] == [bad.config_id]
    assert db.get(ChatUserDefault, (world["alice"].user_id, app_id)).selection["mcp_config_ids"] == [bad.config_id]
    assert db.query(ConversationTurn).filter_by(conversation_id=cid).one().mcp_configs == []
    # the default offered next time still contains it (and it is not a warning: the config exists)
    options = alice.get_options(app_id)
    assert options.default_selection.mcp_config_ids == [bad.config_id] and options.default_warnings == []
    # create_conversation returns the requested selection too
    _, initial = alice.create_conversation(
        app_id, ChatSelection(ai_service_id=world["ai"].service_id, mcp_config_ids=[bad.config_id])
    )
    assert initial.mcp_config_ids == [bad.config_id]


def test_conversation_and_state_row_are_created_atomically(db, world):
    app_id = world["app"].app_id
    alice = svc(db, world["alice"])
    before = db.query(Conversation).count()
    with patch("services.internal_chat.chat_service.ChatConversationStateRepository.ensure", side_effect=RuntimeError("x")):
        with pytest.raises(RuntimeError):
            alice.create_conversation(app_id, ChatSelection(ai_service_id=world["ai"].service_id))
    assert db.query(Conversation).count() == before  # no orphan conversation
    # the session is still usable
    conversation, _ = alice.create_conversation(app_id, ChatSelection(ai_service_id=world["ai"].service_id))
    assert db.get(ChatConversationState, conversation.conversation_id) is not None


async def test_reset_bumps_generation_wipes_turns_and_cleans_files_and_media(db, world):
    app_id = world["app"].app_id
    alice = svc(db, world["alice"])
    p = alice.prepare_turn(app_id, ChatSelection(ai_service_id=world["ai"].service_id))
    cid = p.conversation.conversation_id
    old_sid = p.conversation.session_id
    await _complete(alice, p, "m1")
    statements = []

    def capture(conn, cursor, statement, *a):
        statements.append(statement)

    from unittest.mock import MagicMock

    release = MagicMock()
    removed = AsyncMock(return_value=True)
    event.listen(db.get_bind(), "before_cursor_execute", capture)
    try:
        with patch.object(ConversationService, "delete_thread_history", new=AsyncMock()) as thread, \
             patch.object(ConversationService, "release_conversation_resources", new=release), \
             patch("services.file_management_service.FileManagementService.list_attached_files",
                   new=AsyncMock(return_value=[{"file_id": "f-old"}])) as listed, \
             patch("services.file_management_service.FileManagementService.remove_file", new=removed):
            await alice.reset_conversation(app_id, cid)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", capture)
    assert thread.await_args.args == (p.agent_id, old_sid)  # the OLD thread, after the commit
    release.assert_called_once()
    assert listed.await_args.args[0] == p.agent_id and listed.await_args.args[2] == str(cid)
    assert removed.await_args.args == ("f-old", p.agent_id, {"user_id": world["alice"].user_id, "oauth": True,
                                                              "app_id": app_id}, str(cid))
    assert any("FOR UPDATE" in st and "chat_conversation_state" in st for st in statements)
    assert db.query(ConversationTurn).filter_by(conversation_id=cid).count() == 0
    db.expire_all()
    assert db.get(ChatConversationState, cid).generation == 1
    assert db.get(Conversation, cid).message_count == 0
    new_sid = db.get(Conversation, cid).session_id
    assert new_sid != old_sid and new_sid.startswith(f"conv_{p.agent_id}_")


async def test_failed_old_thread_delete_does_not_fail_the_reset(db, world):
    from services.internal_chat import chat_service as cs

    app_id = world["app"].app_id
    alice = svc(db, world["alice"])
    sel = ChatSelection(ai_service_id=world["ai"].service_id)
    p = alice.prepare_turn(app_id, sel)
    cid = p.conversation.conversation_id
    old_sid = p.conversation.session_id
    await _complete(alice, p, "m1")
    db.get(Conversation, cid).message_count = 2
    db.commit()
    with patch.object(ConversationService, "delete_thread_history", new=AsyncMock(side_effect=RuntimeError("db down"))), \
         patch("services.file_management_service.FileManagementService.remove_all_attached_files", new=AsyncMock(return_value=0)), \
         patch.object(cs.logger, "error") as log_error:
        await alice.reset_conversation(app_id, cid)  # does not raise
    logged = " ".join(str(a) for call in log_error.call_args_list for a in call.args)
    assert str(cid) in logged and old_sid in logged and "db down" not in logged
    db.expire_all()
    conv = db.get(Conversation, cid)
    assert conv.session_id != old_sid and conv.message_count == 0
    assert db.get(ChatConversationState, cid).generation == 1
    assert db.query(ConversationTurn).filter_by(conversation_id=cid).count() == 0
    fresh = alice.prepare_turn(app_id, sel, cid)  # usable for a new turn
    assert fresh.conversation.session_id == conv.session_id
    assert (await _complete(alice, fresh, "m2"))["turn_index"] == 1


async def test_turn_completing_after_reset_or_delete_persists_nothing_and_drops_thread(db, world):
    app_id = world["app"].app_id
    alice = svc(db, world["alice"])
    sel = ChatSelection(ai_service_id=world["ai"].service_id)
    # --- reset while the turn runs
    p = alice.prepare_turn(app_id, sel)
    cid = p.conversation.conversation_id
    stale_sid = p.conversation.session_id
    with patch.object(ConversationService, "delete_thread_history", new=AsyncMock()):
        await alice.reset_conversation(app_id, cid)
    with patch.object(ConversationService, "delete_thread_histories_in_background") as drop:
        assert await _complete(alice, p, "late") is None
    drop.assert_called_once_with([(p.agent_id, stale_sid)])
    assert db.query(ConversationTurn).filter_by(conversation_id=cid).count() == 0
    assert db.get(ChatUserDefault, (world["alice"].user_id, app_id)) is None
    # a turn prepared AFTER the reset is on the new generation and persists
    p2 = alice.prepare_turn(app_id, sel, cid)
    assert (await _complete(alice, p2, "fresh"))["turn_index"] == 1

    # --- delete while the turn runs
    p3 = alice.prepare_turn(app_id, sel)
    session_id, agent_id = p3.conversation.session_id, p3.agent_id
    with patch.object(ConversationService, "delete_thread_history", new=AsyncMock()):
        await alice.delete_conversation(app_id, p3.conversation.conversation_id)
    with patch.object(ConversationService, "delete_thread_histories_in_background") as drop:
        assert await _complete(alice, p3, "late") is None  # INFO log, no RuntimeError
    drop.assert_called_once_with([(agent_id, session_id)])


async def test_hook_stores_execution_event_id(db, world):
    import uuid

    alice = svc(db, world["alice"])
    p = alice.prepare_turn(world["app"].app_id, ChatSelection(ai_service_id=world["ai"].service_id))
    event_id = str(uuid.uuid4())
    await p.on_turn_completed(
        TurnCompleted(
            conversation_id=p.conversation.conversation_id, assistant_message_id="m", user_context={},
            turn_config=p.turn_config, execution_event_id=event_id,
        )
    )
    row = db.query(ConversationTurn).filter_by(conversation_id=p.conversation.conversation_id).one()
    assert str(row.execution_event_id) == event_id


def test_playground_media_silos_are_not_selectable(db, world):
    app_id = world["app"].app_id
    visible = Silo(name="visible", app_id=app_id, embedding_service_id=world["emb"].service_id)
    by_type = Silo(name="temp-by-type", app_id=app_id, embedding_service_id=world["emb"].service_id)
    by_prefix = Silo(name="by-name-only", app_id=app_id, embedding_service_id=world["emb"].service_id)
    db.add_all([visible, by_type, by_prefix])
    db.flush()
    db.add_all([
        Repository(name="user-named repo", type="playground_media", app_id=app_id, silo_id=by_type.silo_id),
        Repository(name="_playground_7_conv", type="other", app_id=app_id, silo_id=by_prefix.silo_id),
    ])
    db.flush()
    names = {o.name for o in svc(db, world["alice"]).get_options(app_id).silos}
    # One definition of "temp": the typed marker only. A repository merely NAMED ``_playground_...`` is a user's.
    assert names == {"visible", "by-name-only"}
    with pytest.raises(ChatResourceNotFoundError):
        svc(db, world["alice"]).prepare_turn(
            app_id, ChatSelection(ai_service_id=world["ai"].service_id, silo_id=by_type.silo_id)
        )


def test_skill_validation_follows_selectable_rule_by_ids(db, world):
    app_id = world["app"].app_id
    own = Skill(name="ic-own", content="x", app_id=app_id)
    own_disabled = Skill(name="ic-own-off", content="x", app_id=app_id, is_enabled=False)
    sys_ok = Skill(name="ic-sys-ok", content="x", app_id=None)
    sys_off = Skill(name="ic-sys-off", content="x", app_id=None, is_enabled=False)
    sys_shadowed = Skill(name="IC-Shadow", content="x", app_id=None)
    shadow = Skill(name="ic-shadow", content="x", app_id=app_id)
    foreign = Skill(name="ic-foreign", content="x", app_id=world["other"].app_id)
    db.add_all([own, own_disabled, sys_ok, sys_off, sys_shadowed, shadow, foreign])
    db.flush()
    alice, ai = svc(db, world["alice"]), world["ai"].service_id
    ok = alice.prepare_turn(app_id, ChatSelection(ai_service_id=ai, skill_ids=[own.skill_id, sys_ok.skill_id, shadow.skill_id]))
    assert set(ok.turn_config.skill_ids) == {own.skill_id, sys_ok.skill_id, shadow.skill_id}
    for bad in (own_disabled, sys_off, sys_shadowed, foreign):
        with pytest.raises(ChatResourceNotFoundError):
            alice.prepare_turn(app_id, ChatSelection(ai_service_id=ai, skill_ids=[bad.skill_id]))


def test_skill_validation_query_cost_does_not_grow_with_the_app(db, world):
    app_id = world["app"].app_id
    chosen = Skill(name="ic-chosen", content="x", app_id=app_id)
    db.add(chosen)
    db.flush()
    alice, ai = svc(db, world["alice"]), world["ai"].service_id
    sel = ChatSelection(ai_service_id=ai, skill_ids=[chosen.skill_id])
    warm = alice.prepare_turn(app_id, sel)  # warm-up: creates agent + conversation
    cid = warm.conversation.conversation_id
    alice.release_turn(warm.claim)  # one turn at a time per conversation: give it back before the next prepare

    def prepare_and_release():
        alice.release_turn(alice.prepare_turn(app_id, sel, cid).claim)

    prepare_and_release()  # the release expires the session's objects: reload them outside the measurement
    prepare_and_release()
    base = _count_queries(db, prepare_and_release)
    db.add_all([Skill(name=f"ic-bulk-{i}", content="x" * 50, app_id=app_id) for i in range(20)])
    db.flush()
    prepare_and_release()  # (see above) the first call after a flush reloads expired state
    assert _count_queries(db, prepare_and_release) == base


def test_set_local_timeouts_do_not_leak_past_the_transaction(test_engine):
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session
    from repositories.internal_chat_repository import set_local_timeouts

    with Session(test_engine) as s:
        default_lock = s.execute(select(func.current_setting("lock_timeout"))).scalar_one()
        s.rollback()
        set_local_timeouts(s, 3000, 8000)
        assert s.execute(select(func.current_setting("lock_timeout"))).scalar_one() == "3s"
        with s.begin_nested():  # what the hook runner does: SAVEPOINT, then the runner's commit
            assert s.execute(select(func.current_setting("statement_timeout"))).scalar_one() == "8s"
        s.commit()
        assert s.execute(select(func.current_setting("lock_timeout"))).scalar_one() == default_lock
        assert s.execute(select(func.current_setting("statement_timeout"))).scalar_one() != "8s"
        # and a rolled-back transaction does not leak either
        set_local_timeouts(s, 1000, 2000)
        s.rollback()
        assert s.execute(select(func.current_setting("lock_timeout"))).scalar_one() == default_lock


async def test_hook_gives_up_when_the_state_row_is_locked_elsewhere(test_engine, monkeypatch):
    """Real connections: a lock held by another transaction must not stall the hook beyond the lock timeout."""
    import time
    import uuid

    from sqlalchemy import delete, select
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import Session

    from services.internal_chat import chat_service as cs

    monkeypatch.setattr(cs, "HOOK_LOCK_TIMEOUT_MS", 500)
    tag = uuid.uuid4().hex[:8]
    session = Session(test_engine)
    holder = test_engine.connect()
    created = {}
    try:
        user = User(email=f"lock-{tag}@test.com", name="lock", is_active=True, platform_role="editor")
        session.add(user)
        session.flush()
        app = App(name=f"lock-{tag}", slug=f"lock-{tag}", owner_id=user.user_id, agent_rate_limit=0, max_file_size_mb=10)
        session.add(app)
        session.flush()
        ai = _ai(session, app.app_id)
        session.commit()
        created.update(user=user.user_id, app=app.app_id, ai=ai.service_id)

        service = InternalChatService(session, {"user_id": user.user_id})
        prepared = service.prepare_turn(app.app_id, ChatSelection(ai_service_id=ai.service_id))
        cid = prepared.conversation.conversation_id
        created["agent"] = prepared.agent_id

        tx = holder.begin()
        holder.execute(select(ChatConversationState.conversation_id).where(
            ChatConversationState.conversation_id == cid).with_for_update())

        started = time.monotonic()
        with pytest.raises(OperationalError):
            with session.begin_nested():
                await _complete(service, prepared, "m1")
        elapsed = time.monotonic() - started
        session.rollback()
        tx.rollback()
        assert elapsed < 2.5, f"hook waited {elapsed:.1f}s for a lock bounded at 0.5s"
        assert session.query(ConversationTurn).filter_by(conversation_id=cid).count() == 0
    finally:
        holder.close()
        session.rollback()
        if created.get("agent"):
            session.execute(delete(Agent).where(Agent.agent_id == created["agent"]))
        if created.get("ai"):
            session.execute(delete(AIService).where(AIService.service_id == created["ai"]))
        if created.get("app"):
            session.execute(delete(App).where(App.app_id == created["app"]))
        if created.get("user"):
            session.execute(delete(User).where(User.user_id == created["user"]))
        session.commit()
        session.close()


# --------------------------------------------------------------------------------------------------
# Tier freezes (item 12)
# --------------------------------------------------------------------------------------------------


def _frozen_world(db, world):
    app_id = world["app"].app_id
    emb = world["emb"].service_id
    ok_silo = Silo(name="fz-ok-silo", app_id=app_id, embedding_service_id=emb)
    frozen_silo = Silo(name="fz-frozen-silo", app_id=app_id, embedding_service_id=emb, is_frozen=True)
    ok_skill = Skill(name="fz-ok-skill", content="x", app_id=app_id)
    frozen_skill = Skill(name="fz-frozen-skill", content="x", app_id=app_id, is_frozen=True)
    db.add_all([ok_silo, frozen_silo, ok_skill, frozen_skill])
    db.flush()
    return ok_silo, frozen_silo, ok_skill, frozen_skill


def test_frozen_silo_and_skill_absent_from_options_and_not_found_on_resolve(db, world):
    app_id, ai = world["app"].app_id, world["ai"].service_id
    ok_silo, frozen_silo, ok_skill, frozen_skill = _frozen_world(db, world)
    alice = svc(db, world["alice"])
    options = alice.get_options(app_id)
    assert {o.silo_id for o in options.silos} == {ok_silo.silo_id}
    assert {o.skill_id for o in options.skills} == {ok_skill.skill_id}
    # controls resolve fine
    prepared = alice.prepare_turn(app_id, ChatSelection(ai_service_id=ai, silo_id=ok_silo.silo_id, skill_ids=[ok_skill.skill_id]))
    assert prepared.turn_config.silo_id == ok_silo.silo_id
    for sel in (
        ChatSelection(ai_service_id=ai, silo_id=frozen_silo.silo_id),
        ChatSelection(ai_service_id=ai, skill_ids=[frozen_skill.skill_id]),
    ):
        with pytest.raises(ChatResourceNotFoundError) as exc:
            alice.prepare_turn(app_id, sel)
        assert exc.value.message == "Resource not found"


def test_frozen_resources_in_stored_default_are_dropped_with_warning(db, world):
    from services.internal_chat.selection_resolver import ChatSelectionResolver

    app_id, ai = world["app"].app_id, world["ai"].service_id
    ok_silo, frozen_silo, ok_skill, frozen_skill = _frozen_world(db, world)
    selection, warnings = ChatSelectionResolver.sanitize(
        db, app_id,
        {"ai_service_id": ai, "silo_id": frozen_silo.silo_id,
         "skill_ids": [ok_skill.skill_id, frozen_skill.skill_id], "mcp_config_ids": []},
    )
    assert selection == ChatSelection(ai_service_id=ai, silo_id=None, skill_ids=[ok_skill.skill_id])
    assert {(w.kind, w.id) for w in warnings} == {("silo", frozen_silo.silo_id), ("skill", frozen_skill.skill_id)}
    # through the user-default path of get_options: degrades, does not fail
    db.add(ChatUserDefault(
        user_id=world["alice"].user_id, app_id=app_id,
        selection={"ai_service_id": ai, "silo_id": frozen_silo.silo_id, "skill_ids": [], "mcp_config_ids": []},
        updated_at=datetime.utcnow(),
    ))
    db.flush()
    options = svc(db, world["alice"]).get_options(app_id)
    assert options.default_selection.silo_id is None
    assert [(w.kind, w.id) for w in options.default_warnings] == [("silo", frozen_silo.silo_id)]


async def test_frozen_app_rejects_new_activity_but_keeps_existing_conversations(db, world):
    from fastapi import HTTPException

    app_id, ai = world["app"].app_id, world["ai"].service_id
    alice = svc(db, world["alice"])
    sel = ChatSelection(ai_service_id=ai)
    p = alice.prepare_turn(app_id, sel)  # control: not frozen
    cid = p.conversation.conversation_id
    assert alice.get_options(app_id).has_usable_model

    world["app"].is_frozen = True
    db.flush()
    conversations_before = db.query(Conversation).count()
    for call in (
        lambda: alice.get_options(app_id),
        lambda: alice.create_conversation(app_id),
        lambda: alice.create_conversation(app_id, sel),
        lambda: alice.prepare_turn(app_id, sel),
        lambda: alice.prepare_turn(app_id, sel, cid),
    ):
        with pytest.raises(HTTPException) as exc:
            call()
        assert exc.value.status_code == 403 and "frozen" in exc.value.detail
    assert db.query(Conversation).count() == conversations_before
    # existing conversations stay reachable, like a frozen agent's in the playground
    assert alice.list_conversations(app_id)[1] == 1
    assert alice.rename_conversation(app_id, cid, "still works").title == "still works"
    with patch.object(ConversationService, "delete_thread_history", new=AsyncMock()):
        await alice.delete_conversation(app_id, cid)


def test_internal_agent_is_never_frozen(db, world):
    agent_id = InternalChatAgentRepository.get_or_create(db, world["app"].app_id, PROMPT)
    assert db.get(Agent, agent_id).is_frozen is False


# --------------------------------------------------------------------------------------------------
# Reset / delete races (thread rotation). A fake checkpoint store records which thread ids are deleted.
# --------------------------------------------------------------------------------------------------


class _FakeThreads:
    """Stands in for the LangGraph checkpointer: thread id -> messages; records every delete."""

    def __init__(self):
        self.threads = {}
        self.deleted = []

    def write(self, session_id, *messages):
        self.threads.setdefault(session_id, []).extend(messages)

    async def delete(self, agent_id, session_id, strict=False):
        self.deleted.append(session_id)
        self.threads.pop(session_id, None)

    def delete_background(self, threads):
        for _agent_id, session_id in threads:
            self.deleted.append(session_id)
            self.threads.pop(session_id, None)

    def patches(self):
        return (
            patch.object(ConversationService, "delete_thread_history", new=self.delete),
            patch.object(ConversationService, "delete_thread_histories_in_background", new=self.delete_background),
            patch("services.file_management_service.FileManagementService.remove_all_attached_files",
                  new=AsyncMock(return_value=0)),
            patch.object(ConversationService, "release_conversation_resources", new=lambda *a, **k: None),
        )


async def test_race_A_stale_turn_completing_during_reset_cannot_resurrect_history(db, world):
    app_id = world["app"].app_id
    alice = svc(db, world["alice"])
    sel = ChatSelection(ai_service_id=world["ai"].service_id)
    p1 = alice.prepare_turn(app_id, sel)
    cid = p1.conversation.conversation_id
    old_sid = p1.conversation.session_id
    await _complete(alice, p1, "m1")  # a pre-reset turn row exists
    stale = alice.prepare_turn(app_id, sel, cid)  # turn that is still running when the reset starts
    fake = _FakeThreads()
    fake.write(old_sid, "pre-reset history")
    p_a, p_b, p_c, p_d = fake.patches()

    real_delete = fake.delete

    async def delete_then_stale_turn_finishes(agent_id, session_id, strict=False):
        await real_delete(agent_id, session_id, strict)
        fake.write(session_id, "stale turn rewrites the whole history")  # checkpoint written after the delete
        assert await _complete(alice, stale, "late") is None  # its hook runs while the reset is in step 2

    with p_a, p_b, p_c, p_d:
        with patch.object(ConversationService, "delete_thread_history", new=delete_then_stale_turn_finishes):
            await alice.reset_conversation(app_id, cid)

    db.expire_all()
    new_sid = db.get(Conversation, cid).session_id
    assert new_sid != old_sid
    assert fake.threads.get(new_sid, []) == [] and old_sid not in fake.threads  # nothing from before survives
    assert db.query(ConversationTurn).filter_by(conversation_id=cid).count() == 0
    assert new_sid not in fake.deleted


async def test_race_B_stale_turn_never_deletes_the_thread_of_a_live_post_reset_turn(db, world):
    app_id = world["app"].app_id
    alice = svc(db, world["alice"])
    sel = ChatSelection(ai_service_id=world["ai"].service_id)
    tab_a = alice.prepare_turn(app_id, sel)
    cid = tab_a.conversation.conversation_id
    old_sid = tab_a.conversation.session_id
    fake = _FakeThreads()
    fake.write(old_sid, "old")
    p_a, p_b, p_c, p_d = fake.patches()
    with p_a, p_b, p_c, p_d:
        await alice.reset_conversation(app_id, cid)
        tab_b = alice.prepare_turn(app_id, sel, cid)  # new turn after the reset: new generation, new thread
        live_sid = tab_b.conversation.session_id
        assert live_sid != old_sid
        fake.write(live_sid, "live turn message")
        deleted_before = list(fake.deleted)
        assert await _complete(alice, tab_a, "stale") is None  # stale tab A completes first
        assert fake.deleted[len(deleted_before):] == [old_sid]  # only the old thread is dropped
        assert fake.threads[live_sid] == ["live turn message"]
        payload = await _complete(alice, tab_b, "live")  # the live turn persists normally
        assert payload["turn_index"] == 1
    assert live_sid not in fake.deleted


async def test_race_C_turn_completing_during_delete_is_dropped_and_leaves_nothing(db, world):
    app_id = world["app"].app_id
    alice = svc(db, world["alice"])
    p = alice.prepare_turn(app_id, ChatSelection(ai_service_id=world["ai"].service_id))
    cid, sid = p.conversation.conversation_id, p.conversation.session_id
    fake = _FakeThreads()
    fake.write(sid, "history")
    p_a, p_b, p_c, p_d = fake.patches()
    real_delete = fake.delete

    async def delete_then_turn_finishes(agent_id, session_id, strict=False):
        # the row delete is already committed when the thread delete runs
        assert db.get(Conversation, cid) is None
        fake.write(session_id, "checkpoint written by the still-running turn")
        assert await _complete(alice, p, "late") is None
        await real_delete(agent_id, session_id, strict)

    with p_a, p_b, p_c, p_d:
        with patch.object(ConversationService, "delete_thread_history", new=delete_then_turn_finishes):
            await alice.delete_conversation(app_id, cid)
    assert db.get(ChatConversationState, cid) is None
    assert db.query(ConversationTurn).filter_by(conversation_id=cid).count() == 0
    assert sid not in fake.threads and sid in fake.deleted
    assert db.get(ChatUserDefault, (world["alice"].user_id, app_id)) is None


async def test_prepared_turn_is_bound_to_one_thread_even_if_a_reset_follows(db, world):
    app_id = world["app"].app_id
    alice = svc(db, world["alice"])
    sel = ChatSelection(ai_service_id=world["ai"].service_id)
    first = alice.prepare_turn(app_id, sel)
    cid = first.conversation.conversation_id
    alice.release_turn(first.claim)  # one turn at a time per conversation
    bound = alice.prepare_turn(app_id, sel, cid)
    old_sid = bound.conversation.session_id  # what the execution stack will read from the pinned row
    fake = _FakeThreads()
    p_a, p_b, p_c, p_d = fake.patches()
    with p_a, p_b, p_c, p_d:
        await alice.reset_conversation(app_id, cid)
    new = alice.prepare_turn(app_id, sel, cid)
    assert new.conversation.session_id != old_sid
    assert new.conversation.session_id.startswith(f"conv_{new.agent_id}_")


async def test_reset_never_awaits_while_holding_the_conversation_lock(test_engine):
    """Regression: a sync UPDATE of the Conversation row elsewhere in the worker must not wait for the reset's
    (slow) thread delete, nor freeze the event loop."""
    import asyncio
    import time
    import uuid

    from sqlalchemy import delete, text
    from sqlalchemy.orm import Session

    tag = uuid.uuid4().hex[:8]
    session = Session(test_engine)
    other = test_engine.connect()
    created = {}
    ticks = []
    try:
        user = User(email=f"loop-{tag}@test.com", name="loop", is_active=True, platform_role="editor")
        session.add(user)
        session.flush()
        app = App(name=f"loop-{tag}", slug=f"loop-{tag}", owner_id=user.user_id, agent_rate_limit=0, max_file_size_mb=10)
        session.add(app)
        session.flush()
        ai = _ai(session, app.app_id)
        session.commit()
        created.update(user=user.user_id, app=app.app_id, ai=ai.service_id)
        service = InternalChatService(session, {"user_id": user.user_id})
        prepared = service.prepare_turn(app.app_id, ChatSelection(ai_service_id=ai.service_id))
        cid = prepared.conversation.conversation_id
        created["agent"] = prepared.agent_id

        thread_delete_started = asyncio.Event()

        async def slow_thread_delete(agent_id, session_id):
            thread_delete_started.set()
            await asyncio.sleep(1.0)  # a slow checkpoint delete

        async def ticker():
            while True:
                ticks.append(time.monotonic())
                await asyncio.sleep(0.02)

        async def scenario():
            tick_task = asyncio.create_task(ticker())
            with patch.object(ConversationService, "delete_thread_history", new=slow_thread_delete), \
                 patch("services.file_management_service.FileManagementService.remove_all_attached_files",
                       new=AsyncMock(return_value=0)), \
                 patch.object(ConversationService, "release_conversation_resources", new=lambda *a, **k: None):
                reset_task = asyncio.create_task(service.reset_conversation(app.app_id, cid))
                try:
                    await thread_delete_started.wait()
                    # what ConversationService.increment_message_count does, from "another turn" in the same worker
                    other.execute(text("SET lock_timeout = '1500ms'"))
                    started = time.monotonic()
                    other.execute(
                        text('UPDATE "Conversation" SET message_count = message_count + 2 WHERE conversation_id = :c'),
                        {"c": cid},
                    )
                    other.commit()
                    elapsed = time.monotonic() - started
                    ticks_after = len(ticks)
                    await asyncio.sleep(0.2)
                    await reset_task
                finally:
                    # On a regression the UPDATE raises while the reset still holds its locks: never leave the
                    # reset (or the ticker) running past the test, or the suite teardown waits on its transaction.
                    for task in (reset_task, tick_task):
                        task.cancel()
                    await asyncio.gather(reset_task, tick_task, return_exceptions=True)
            return elapsed, ticks_after

        elapsed, ticks_after = await asyncio.wait_for(scenario(), timeout=20)
        assert elapsed < 0.5, f"the UPDATE waited {elapsed:.2f}s: the reset holds the row lock across an await"
        assert len(ticks) > ticks_after, "the event loop stopped ticking"
        assert max(b - a for a, b in zip(ticks, ticks[1:])) < 0.5, "the event loop was frozen"
    finally:
        other.close()
        session.rollback()
        if created.get("agent"):
            session.execute(delete(Agent).where(Agent.agent_id == created["agent"]))
        if created.get("ai"):
            session.execute(delete(AIService).where(AIService.service_id == created["ai"]))
        if created.get("app"):
            session.execute(delete(App).where(App.app_id == created["app"]))
        if created.get("user"):
            session.execute(delete(User).where(User.user_id == created["user"]))
        session.commit()
        session.close()
