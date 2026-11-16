"""Isolation of the Chat's state between users (app-flexible-chat step_010).

The hard requirement: separate users' interactions must not interfere with each other. Everything runs for real
(router, ``InternalChatService``, resolver, execution/streaming services, LangGraph checkpointer, PostgreSQL) with the
fakes of ``_chat_support`` (LLM, retriever, MCP client, metrics write).

Covered here (sequential interactions of several users): privacy of conversations between users, Apps and surfaces
(AC-17), immutability of the shared internal agent row (AC-18), per-user defaults (AC-22, sequential part), thread
separation (AC-23), refused callers, the frozen App, human approvals (AC-25), attribution of metrics and billing, and
log hygiene (NFR-11). Overlapping turns (concurrent streams, MCP forwarding, attachments/temp-silo RAG) are step_011.

Every test rebuilds its own world inside the rolled-back test transaction; the checkpoints (written on separate
connections) are removed by the ``fakes`` fixture.
"""
import json
import logging
import re
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from sqlalchemy import event, text

from models.agent import Agent
from models.app import App
from models.app_collaborator import CollaborationRole, CollaborationStatus
from models.conversation import Conversation
from models.hitl_approval import HITLApproval
from models.internal_chat import ChatConversationState, ChatUserDefault, ConversationTurn
from models.mcp_config import MCPConfig
from models.silo import Silo
from models.skill import Skill
from models.usage_record import UsageRecord
from models.user import User
from services.playground_media_service import PlaygroundMediaService
from services.session_management_service import Session as InMemorySession
from services.session_management_service import SessionManagementService
from tests.factories import (
    AgentFactory,
    AIServiceFactory,
    AppCollaboratorFactory,
    APIKeyFactory,
    UserFactory,
    configure_factories,
)
from schemas.internal_chat_schemas import ChatSelection
from tests.integration.internal_chat._chat_support import (
    NOT_FOUND,
    FakeChatModel,
    ThreadProbe,
    base,
    detail,
    ok_turn,
    selection,
    send,
    sse_turn,
    turn_form,
)
from tests.integration.routers.internal._eos_helpers import headers_for

def _selection_model(ai: int) -> ChatSelection:
    return ChatSelection(**selection(ai))


CONVERSATION_NOT_FOUND = {"detail": "Conversation not found"}  # the generic /internal/conversations router
INTERNAL_AGENT_TABLES = ("agent_skills", "agent_mcps", "agent_tools", "agent_middlewares")


@pytest.fixture(autouse=True)
def _no_vectorize():
    with patch.object(PlaygroundMediaService, "vectorize_uploaded_file", return_value=False):
        yield


@pytest.fixture
def team(db, world, monkeypatch):
    """The ``world`` App with one user of every kind (all ids/headers plain: a streamed turn closes the session).

    ``author`` is an EDITOR (so that the playground surfaces, which need EDITOR, can be tried with the author's own
    conversation id); ``peer`` is a VIEWER; ``owner`` is alice; ``admin`` an ADMINISTRATOR; ``omni`` an OMNIADMIN that is
    also an ADMINISTRATOR of the App; ``omni_outside`` an OMNIADMIN that is not a collaborator; ``pending`` / ``declined``
    hold an unanswered / declined invitation; ``outsider`` has no relation to the App.
    """
    configure_factories(db)
    app = db.get(App, world["app_id"])

    def member(role, status=CollaborationStatus.ACCEPTED, **user_kwargs):
        user = UserFactory(**user_kwargs)
        AppCollaboratorFactory(app=app, user=user, role=role, status=status, invited_by=app.owner_id)
        return user

    users = {
        "author": member(CollaborationRole.EDITOR),
        "peer": member(CollaborationRole.VIEWER),
        "admin": member(CollaborationRole.ADMINISTRATOR),
        "omni": member(CollaborationRole.ADMINISTRATOR, email=f"omni-{uuid.uuid4().hex[:8]}@mattin-test.com"),
        "pending": member(CollaborationRole.VIEWER, CollaborationStatus.PENDING),
        "declined": member(CollaborationRole.VIEWER, CollaborationStatus.DECLINED),
        "outsider": UserFactory(),
        "omni_outside": UserFactory(email=f"omni-out-{uuid.uuid4().hex[:8]}@mattin-test.com"),
    }
    monkeypatch.setenv("AICT_OMNIADMINS", f"{users['omni'].email},{users['omni_outside'].email}")
    db.flush()
    team = dict(world)
    for name, user in users.items():
        team[name] = headers_for(user)
        team[f"{name}_id"] = user.user_id
    team["owner"] = world["alice"]
    team["owner_id"] = world["alice_id"]
    db.commit()
    return team


def upload(client, team, cid, who="author", name="a.txt", content=b"AUTHOR-FILE-BODY-9d1f"):
    response = client.post(
        f"{base(team['app_id'])}/conversations/{cid}/files", headers=team[who],
        files={"file": (name, content, "text/plain")},
    )
    assert response.status_code == 200, response.text
    return response.json()["file_id"]


def conv_state(client, db, team, cid, who="author") -> dict:
    """Everything the author can observe of a conversation plus its rows, for before/after comparisons."""
    db.expire_all()
    row = db.get(Conversation, cid)
    state_row = db.get(ChatConversationState, cid)
    turns = db.query(ConversationTurn).filter_by(conversation_id=cid).order_by(ConversationTurn.turn_index).all()
    url = f"{base(team['app_id'])}/conversations/{cid}"
    files_response = client.get(f"{url}/files", headers=team[who])
    detail_response = client.get(url, headers=team[who])
    assert (files_response.status_code, detail_response.status_code) == (200, 200), (
        files_response.text, detail_response.text,
    )
    files = files_response.json()
    for entry in files.get("files", []):
        entry.pop("uploaded_at", None)  # re-derived on every listing, not stored
    return {
        "detail": detail_response.json(),
        "files": files,
        "row": (row.title, row.message_count, row.last_message, row.session_id, row.user_id),
        "state": (state_row.generation, state_row.selection) if state_row else None,
        "turns": [(t.turn_index, t.user_id, t.ai_service_id, t.silo_id) for t in turns],
    }


def conversation_requests(client, app_id, cid, fid, headers, sel) -> dict:
    """Every Chat endpoint addressed to one conversation (and one file of it)."""
    url = f"{base(app_id)}/conversations/{cid}"
    return {
        "get": client.get(url, headers=headers),
        "rename": client.patch(url, headers=headers, json={"title": "hijacked"}),
        "delete": client.delete(url, headers=headers),
        "reset": client.post(f"{url}/reset", headers=headers),
        "files_list": client.get(f"{url}/files", headers=headers),
        "files_upload": client.post(f"{url}/files", headers=headers, files={"file": ("evil.txt", b"evil", "text/plain")}),
        "file_delete": client.delete(f"{url}/files/{fid}", headers=headers),
        "file_download": client.get(f"{url}/files/{fid}/download", headers=headers),
        "messages": client.post(
            f"{base(app_id)}/messages", headers=headers, data=turn_form("intruder message", sel, cid)
        ),
        "stream": client.post(
            f"{base(app_id)}/stream", headers=headers, data=turn_form("intruder message", sel, cid)
        ),
    }


@pytest.fixture
def authored(client, db, team, fakes):
    """The author's conversation: two turns, a second model, and one attached file."""
    cid = ok_turn(client, team, "author secret one", selection(team["ai_a"]), who="author")["conversation_id"]
    ok_turn(client, team, "author secret two", selection(team["ai_b"]), conversation_id=cid, who="author")
    fid = upload(client, team, cid)
    return {"cid": cid, "fid": fid, "calls": len(fakes.calls)}


# ------------------------------------------------------------------ AC-17: privacy between users of one App


class TestSameAppPrivacy:
    @pytest.mark.parametrize("who", ["peer", "owner", "admin", "omni"])
    def test_no_other_member_can_reach_a_conversation_of_the_author(self, client, db, team, fakes, authored, who):
        cid = authored["cid"]
        before = conv_state(client, db, team, cid)
        assert before["turns"] == [(1, team["author_id"], team["ai_a"], None), (2, team["author_id"], team["ai_b"], None)]
        assert [f["filename"] for f in before["files"]["files"]] == ["a.txt"]

        listed = client.get(f"{base(team['app_id'])}/conversations", headers=team[who]).json()
        assert cid not in [c["conversation_id"] for c in listed["conversations"]]

        responses = conversation_requests(
            client, team["app_id"], cid, authored["fid"], team[who], selection(team["ai_a"])
        )
        for name, response in responses.items():
            assert (name, response.status_code, response.json()) == (name, 404, NOT_FOUND)

        # the generic conversations router has no App scope: it must be as strict
        generic = f"/internal/conversations/{cid}"
        for method, suffix, kwargs in (
            ("get", "", {}), ("get", "/history", {}), ("patch", "", {"json": {"title": "x"}}), ("delete", "", {}),
        ):
            response = getattr(client, method)(generic + suffix, headers=team[who], **kwargs)
            assert (method, suffix, response.status_code, response.json()) == (method, suffix, 404, CONVERSATION_NOT_FOUND)

        assert len(fakes.calls) == authored["calls"], "the model of an intruder's turn must never run"
        assert conv_state(client, db, team, cid) == before

    def test_the_author_still_has_everything_after_the_attempts(self, client, db, team, fakes, authored):
        cid = authored["cid"]
        before = conv_state(client, db, team, cid)
        conversation_requests(client, team["app_id"], cid, authored["fid"], team["peer"], selection(team["ai_a"]))
        assert conv_state(client, db, team, cid) == before
        messages = detail(client, team, cid, who="author")["messages"]
        assert [m["role"] for m in messages] == ["user", "agent", "user", "agent"]
        assert messages[0]["content"] == "author secret one"
        download = client.get(
            f"{base(team['app_id'])}/conversations/{cid}/files/{authored['fid']}/download", headers=team["author"]
        )
        assert download.status_code == 200

    def test_a_peers_listing_only_contains_the_peers_own_conversations(self, client, team, fakes, authored):
        own = ok_turn(client, team, "peer message", selection(team["ai_a"]), who="peer")["conversation_id"]
        peers = client.get(f"{base(team['app_id'])}/conversations", headers=team["peer"]).json()
        authors = client.get(f"{base(team['app_id'])}/conversations", headers=team["author"]).json()
        assert [c["conversation_id"] for c in peers["conversations"]] == [own] and peers["total"] == 1
        assert authored["cid"] in [c["conversation_id"] for c in authors["conversations"]]
        assert own not in [c["conversation_id"] for c in authors["conversations"]]
        assert authors["total"] == 1


# ------------------------------------------------------------------ AC-17 / R-2: privacy between Apps


class TestCrossAppPrivacy:
    @pytest.fixture
    def foreign(self, client, team, fakes):
        """Bob's conversation (and file) in the other App."""
        cid = client.post(
            f"{base(team['other_app_id'])}/conversations", headers=team["bob"],
            json={"selection": selection(team["other_ai"])},
        ).json()["conversation_id"]
        fid = client.post(
            f"{base(team['other_app_id'])}/conversations/{cid}/files", headers=team["bob"],
            files={"file": ("bob.txt", b"bob file", "text/plain")},
        ).json()["file_id"]
        return {"cid": cid, "fid": fid}

    def test_a_user_of_another_app_cannot_use_their_own_app_path_with_the_authors_id(
        self, client, db, team, fakes, authored, foreign
    ):
        before = conv_state(client, db, team, authored["cid"])
        responses = conversation_requests(
            client, team["other_app_id"], authored["cid"], authored["fid"], team["bob"], selection(team["other_ai"])
        )
        for name, response in responses.items():
            assert (name, response.status_code, response.json()) == (name, 404, NOT_FOUND)
        assert conv_state(client, db, team, authored["cid"]) == before
        assert len(fakes.calls) == authored["calls"]

    def test_a_member_cannot_use_the_right_app_path_with_the_conversation_of_another_app(
        self, client, db, team, fakes, authored, foreign
    ):
        bob_before = client.get(
            f"{base(team['other_app_id'])}/conversations/{foreign['cid']}", headers=team["bob"]
        ).json()
        responses = conversation_requests(
            client, team["app_id"], foreign["cid"], foreign["fid"], team["author"], selection(team["ai_a"])
        )
        for name, response in responses.items():
            assert (name, response.status_code, response.json()) == (name, 404, NOT_FOUND)
        assert client.get(
            f"{base(team['other_app_id'])}/conversations/{foreign['cid']}", headers=team["bob"]
        ).json() == bob_before
        assert len(fakes.calls) == authored["calls"]

    @pytest.mark.parametrize("path_app,who", [("app_id", "bob"), ("other_app_id", "author")])
    def test_a_non_member_is_refused_before_the_conversation_is_looked_up(
        self, client, db, team, fakes, authored, foreign, path_app, who
    ):
        cid = authored["cid"] if path_app == "app_id" else foreign["cid"]
        fid = authored["fid"] if path_app == "app_id" else foreign["fid"]
        before = conv_state(client, db, team, authored["cid"])
        responses = conversation_requests(client, team[path_app], cid, fid, team[who], selection(team["ai_a"]))
        for name, response in responses.items():
            assert (name, response.status_code) == (name, 403)
            assert "secret" not in response.text and "bob file" not in response.text
        assert conv_state(client, db, team, authored["cid"]) == before


# ------------------------------------------------------------------ refused callers on every endpoint


class TestRefusedCallers:
    @staticmethod
    def every_endpoint(client, team, headers, cid, fid):
        url = base(team["app_id"])
        sel = selection(team["ai_a"])
        c = f"{url}/conversations/{cid}"
        return {
            "options": client.get(f"{url}/options", headers=headers),
            "defaults_get": client.get(f"{url}/defaults", headers=headers),
            "defaults_put": client.put(f"{url}/defaults", headers=headers, json=sel),
            "list": client.get(f"{url}/conversations", headers=headers),
            "create": client.post(f"{url}/conversations", headers=headers, json={"selection": sel}),
            "get": client.get(c, headers=headers),
            "rename": client.patch(c, headers=headers, json={"title": "x"}),
            "delete": client.delete(c, headers=headers),
            "reset": client.post(f"{c}/reset", headers=headers),
            "stream": client.post(f"{url}/stream", headers=headers, data=turn_form("intruder", sel, cid)),
            "stream_new": client.post(f"{url}/stream", headers=headers, data=turn_form("intruder", sel)),
            "messages": client.post(f"{url}/messages", headers=headers, data=turn_form("intruder", sel, cid)),
            "messages_new": client.post(f"{url}/messages", headers=headers, data=turn_form("intruder", sel)),
            "files_upload": client.post(f"{c}/files", headers=headers, files={"file": ("x.txt", b"x", "text/plain")}),
            "files_list": client.get(f"{c}/files", headers=headers),
            "file_delete": client.delete(f"{c}/files/{fid}", headers=headers),
            "file_download": client.get(f"{c}/files/{fid}/download", headers=headers),
        }

    @pytest.mark.parametrize("who,status", [
        ("pending", 403), ("declined", 403), ("outsider", 403), ("omni_outside", 403), ("bob", 403),
    ])
    def test_users_without_an_accepted_membership_are_refused_everywhere(
        self, client, db, team, fakes, authored, who, status
    ):
        before = conv_state(client, db, team, authored["cid"])
        conversations_before = db.query(Conversation).count()
        responses = self.every_endpoint(client, team, team[who], authored["cid"], authored["fid"])
        for name, response in responses.items():
            assert (name, response.status_code) == (name, status)
            assert response.json() == {"detail": "Insufficient permissions"}, name
        db.expire_all()
        assert db.query(Conversation).count() == conversations_before
        assert conv_state(client, db, team, authored["cid"]) == before
        assert len(fakes.calls) == authored["calls"]

    @pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer not-a-token"}], ids=["no-token", "bad-token"])
    def test_unauthenticated_callers_get_401_without_any_data(self, client, db, team, fakes, authored, headers):
        before = conv_state(client, db, team, authored["cid"])
        responses = self.every_endpoint(client, team, headers, authored["cid"], authored["fid"])
        for name, response in responses.items():
            assert (name, response.status_code) == (name, 401)
            assert response.json() == {"detail": "Authentication failed"}, name
        assert conv_state(client, db, team, authored["cid"]) == before
        assert len(fakes.calls) == authored["calls"]


# ------------------------------------------------------------------ AC-17 / FR-13: the other surfaces


class TestOtherSurfacesCannotReachAChatConversation:
    """The conversation id of a Chat conversation, used by its OWN author on a normal agent's playground and public
    surfaces (the foreign-user variants are in ``test_attachment_isolation``; the internal agent id in
    ``test_internal_agent_exclusion``): 404 everywhere, and the conversation does not change."""

    @pytest.fixture
    def normal_agent(self, db, team):
        configure_factories(db)
        agent = AgentFactory(app=db.get(App, team["app_id"]), has_memory=True)
        db.commit()
        return {"agent_id": agent.agent_id}

    def test_playground_endpoints(self, client, db, team, fakes, authored, normal_agent):
        before = conv_state(client, db, team, authored["cid"])
        cid, fid, h = authored["cid"], authored["fid"], team["author"]
        pg = f"/internal/apps/{team['app_id']}/agents/{normal_agent['agent_id']}"
        responses = {
            "chat": client.post(f"{pg}/chat", headers=h, data={"message": "hi", "conversation_id": str(cid)}),
            "chat_stream": client.post(f"{pg}/chat/stream", headers=h, data={"message": "hi", "conversation_id": str(cid)}),
            "upload": client.post(
                f"{pg}/upload-file", headers=h, data={"conversation_id": str(cid)},
                files={"file": ("evil.txt", b"evil", "text/plain")},
            ),
            "files": client.get(f"{pg}/files", headers=h, params={"conversation_id": cid}),
            "file_delete": client.delete(f"{pg}/files/{fid}", headers=h, params={"conversation_id": cid}),
            "file_download": client.get(f"{pg}/files/{fid}/download", headers=h, params={"conversation_id": cid}),
            "reset": client.post(f"{pg}/reset", headers=h, params={"conversation_id": cid}),
        }
        for name, response in responses.items():
            assert (name, response.status_code) == (name, 404)
            assert "author secret" not in response.text
        # ``conversation-history`` takes no conversation id (it reads the caller's playground session of this agent):
        # the Chat id must be ignored, i.e. answer exactly like a random id and like no id, and show nothing of the Chat.
        history = client.get(f"{pg}/conversation-history", headers=h, params={"conversation_id": cid})
        random_id = client.get(f"{pg}/conversation-history", headers=h, params={"conversation_id": 987654321})
        no_id = client.get(f"{pg}/conversation-history", headers=h)
        assert history.status_code == random_id.status_code == no_id.status_code == 200
        assert history.json() == random_id.json() == no_id.json()
        assert "author secret" not in history.text
        assert len(fakes.calls) == authored["calls"]
        assert conv_state(client, db, team, cid) == before

    def test_generic_conversations_router(self, client, db, team, fakes, authored):
        before = conv_state(client, db, team, authored["cid"])
        for who in ("author", "owner"):
            for method, suffix, kwargs in (
                ("get", "", {}), ("get", "/history", {}), ("patch", "", {"json": {"title": "x"}}), ("delete", "", {}),
            ):
                response = getattr(client, method)(
                    f"/internal/conversations/{authored['cid']}{suffix}", headers=team[who], **kwargs
                )
                assert (who, method, suffix, response.status_code, response.json()) == (
                    who, method, suffix, 404, CONVERSATION_NOT_FOUND,
                )
        assert conv_state(client, db, team, authored["cid"]) == before

    def test_public_api_endpoints(self, client, db, team, fakes, authored, normal_agent):
        key = APIKeyFactory(app=db.get(App, team["app_id"]), user=db.get(User, team["author_id"]))
        db.commit()
        before = conv_state(client, db, team, authored["cid"])
        cid, fid = authored["cid"], authored["fid"]
        k = {"X-API-KEY": key.key}
        chat = f"/public/v1/app/{team['app_id']}/chat/{normal_agent['agent_id']}"
        files = f"/public/v1/app/{team['app_id']}/files/{normal_agent['agent_id']}"
        responses = {
            "call": client.post(f"{chat}/call", headers=k, data={"message": "hi", "conversation_id": str(cid)}),
            "call_stream": client.post(
                f"{chat}/call/stream", headers=k, data={"message": "hi", "conversation_id": str(cid)}
            ),
            "reset": client.post(f"{chat}/reset", headers=k, params={"conversation_id": cid}),
            "get": client.get(f"{chat}/conversations/{cid}", headers=k),
            "delete": client.delete(f"{chat}/conversations/{cid}", headers=k),
            "attach": client.post(
                f"{files}/attach-file", headers=k, data={"conversation_id": str(cid)},
                files={"file": ("evil.txt", b"evil", "text/plain")},
            ),
            "attached": client.get(f"{files}/attached-files", headers=k, params={"conversation_id": cid}),
            "detach": client.delete(f"{files}/detach-file/{fid}", headers=k, params={"conversation_id": cid}),
            "download": client.get(f"{files}/files/{fid}/download", headers=k, params={"conversation_id": cid}),
        }
        for name, response in responses.items():
            assert (name, response.status_code) == (name, 404)
            assert "author secret" not in response.text
        listed = client.get(f"{chat}/conversations", headers=k)
        assert listed.status_code == 200 and cid not in [c["conversation_id"] for c in listed.json()["conversations"]]
        assert len(fakes.calls) == authored["calls"]
        assert conv_state(client, db, team, cid) == before


# ------------------------------------------------------------------ AC-18: the shared agent row never changes


def agent_snapshot(db, agent_id: int) -> dict:
    """Every column of the Agent row and every row of its association tables (what AC-18 calls "byte for byte")."""
    db.flush()
    snapshot = {
        "Agent": sorted(
            repr(sorted(dict(r).items()))
            for r in db.execute(text('SELECT * FROM "Agent" WHERE agent_id = :a'), {"a": agent_id}).mappings()
        )
    }
    for table in INTERNAL_AGENT_TABLES:
        snapshot[table] = sorted(
            repr(sorted(dict(r).items()))
            for r in db.execute(text(f"SELECT * FROM {table} WHERE agent_id = :a"), {"a": agent_id}).mappings()
        )
    return snapshot


FORBIDDEN_WRITE = re.compile(
    r'^\s*(UPDATE\s+"?Agent"?\s|(INSERT\s+INTO|DELETE\s+FROM)\s+"?(agent_skills|agent_mcps|agent_tools|agent_middlewares)"?[\s(])',
    re.IGNORECASE,
)


class TestSharedAgentIsImmutable:
    @pytest.fixture
    def extras(self, db, team):
        silo = Silo(name="silo-x", app_id=team["app_id"], embedding_service_id=team["emb"])
        skill = Skill(name="skill-x", description="SKILL-X-DESC", content="SKILL-X-CONTENT", app_id=team["app_id"])
        mcp = MCPConfig(name="mcp-x", config={"xsrv": {"url": "http://x", "transport": "streamable_http"}},
                        app_id=team["app_id"])
        db.add_all([silo, skill, mcp])
        db.commit()
        return {"silo": silo.silo_id, "skill": skill.skill_id, "mcp": mcp.config_id}

    def _write_watcher(self, test_engine):
        """Statements that write the shared agent, seen on the test engine (the request session's connection) AND on
        the backend's own engine (``db.database.engine``: sessions the code opens itself). Not observed: the
        checkpointer's psycopg pool, which only touches the ``checkpoint*`` tables."""
        from db.database import engine as backend_engine

        seen: list[str] = []

        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            if FORBIDDEN_WRITE.match(statement):
                seen.append(statement[:120])

        engines = [test_engine] if backend_engine is test_engine else [test_engine, backend_engine]
        for engine_ in engines:
            event.listen(engine_, "before_cursor_execute", before_cursor_execute)

        def stop():
            for engine_ in engines:
                event.remove(engine_, "before_cursor_execute", before_cursor_execute)

        return seen, stop

    def _internal_agent_id(self, db, app_id) -> int:
        return db.query(Agent.agent_id).filter(Agent.app_id == app_id, Agent.kind == "internal_chat").scalar()

    def test_turns_of_two_users_with_different_selections_change_nothing_on_the_agent(
        self, client, db, test_engine, team, fakes, extras
    ):
        a, b = team["ai_a"], team["ai_b"]
        first = ok_turn(client, team, "warm up", selection(a), who="author")["conversation_id"]  # creates the agent
        agent_id = self._internal_agent_id(db, team["app_id"])
        before = agent_snapshot(db, agent_id)
        assert before["Agent"], "the internal agent must exist"

        seen, stop = self._write_watcher(test_engine)
        try:
            rich = selection(a, silo=extras["silo"], skills=[extras["skill"]], mcps=[extras["mcp"]])
            retriever, mcp_tool = f"retriever_silo_{extras['silo']}", "mcp_xsrv"

            def seen_by(service, *, retriever_=False, mcp_=False, skill_=False):
                """What the LAST model call of ``service`` was given (one assertion per carried-over item)."""
                tools = fakes.tools_of(service)
                assert (retriever in tools, mcp_tool in tools, "SKILL-X-DESC" in fakes.system_prompt(service)) == (
                    retriever_, mcp_, skill_
                ), (tools, "turn config leaked into or out of this turn")

            ok_turn(client, team, "t1", rich, conversation_id=first, who="author")
            seen_by(a, retriever_=True, mcp_=True, skill_=True)
            ok_turn(client, team, "t2", selection(b), who="peer")  # the plain selection after the author's rich one
            seen_by(b)
            sse_turn(client, team, "t3", selection(b, silo=extras["silo"]), who="peer")
            seen_by(b, retriever_=True)
            sse_turn(client, team, "t4", selection(a, skills=[extras["skill"]]), who="author")
            seen_by(a, skill_=True)
            client.put(f"{base(team['app_id'])}/defaults", headers=team["peer"], json=rich)
        finally:
            stop()
        db.expire_all()
        assert seen == [], f"a Chat turn wrote the shared agent: {seen}"
        assert agent_snapshot(db, agent_id) == before
        agent_row = db.get(Agent, agent_id)
        assert (agent_row.service_id, agent_row.silo_id) == (None, None)

    def test_the_write_watcher_does_see_a_write(self, db, test_engine, team):
        """Guards the guard: the listener catches an UPDATE of the Agent row and an association insert."""
        configure_factories(db)
        agent = AgentFactory(app=db.get(App, team["app_id"]))
        skill = Skill(name="s-watch", content="c", app_id=team["app_id"])
        db.add(skill)
        db.flush()
        seen, stop = self._write_watcher(test_engine)
        try:
            db.execute(text('UPDATE "Agent" SET request_count = request_count + 1 WHERE agent_id = :a'), {"a": agent.agent_id})
            db.execute(
                text("INSERT INTO agent_skills (agent_id, skill_id) VALUES (:a, :s)"),
                {"a": agent.agent_id, "s": skill.skill_id},
            )
        finally:
            stop()
        assert len(seen) == 2

    def test_each_users_defaults_are_their_own_and_the_apps_default_is_untouched(
        self, client, db, team, fakes, extras
    ):
        a, b = team["ai_a"], team["ai_b"]
        url = f"{base(team['app_id'])}/defaults"
        app_default = client.get(url, headers=team["owner"]).json()
        rich = selection(b, silo=extras["silo"], skills=[extras["skill"]], mcps=[extras["mcp"]])
        ok_turn(client, team, "mine", rich, who="author")
        ok_turn(client, team, "mine too", selection(a), who="peer")
        assert client.get(url, headers=team["author"]).json() == rich
        assert client.get(url, headers=team["peer"]).json() == selection(a)
        # a user who never chatted gets the App default, not somebody else's choices
        assert client.get(url, headers=team["owner"]).json() == app_default
        assert client.get(url, headers=team["admin"]).json() == app_default
        assert app_default is not None
        # pinning a default changes that user only
        assert client.put(url, headers=team["peer"], json=selection(b)).status_code == 200
        assert client.get(url, headers=team["peer"]).json() == selection(b)
        assert client.get(url, headers=team["author"]).json() == rich
        rows = {(r.user_id): r.selection for r in db.query(ChatUserDefault).filter_by(app_id=team["app_id"])}
        assert rows == {team["author_id"]: rich, team["peer_id"]: selection(b)}

    def test_options_and_conversation_state_of_a_user_do_not_follow_another_users_turns(
        self, client, db, team, fakes, extras
    ):
        a, b = team["ai_a"], team["ai_b"]
        peer_cid = ok_turn(client, team, "peer one", selection(b), who="peer")["conversation_id"]
        peer_state = conv_state(client, db, team, peer_cid, who="peer")
        peer_default = client.get(f"{base(team['app_id'])}/defaults", headers=team["peer"]).json()

        author_cid = ok_turn(client, team, "author one", selection(a, silo=extras["silo"]), who="author")["conversation_id"]
        ok_turn(client, team, "author two", selection(a, skills=[extras["skill"]]), conversation_id=author_cid, who="author")

        assert conv_state(client, db, team, peer_cid, who="peer") == peer_state
        assert client.get(f"{base(team['app_id'])}/defaults", headers=team["peer"]).json() == peer_default == selection(b)
        reopened = detail(client, team, peer_cid, who="peer")
        assert reopened["current_selection"] == selection(b)
        # and the reverse
        assert detail(client, team, author_cid, who="author")["current_selection"] == selection(a, skills=[extras["skill"]])

    def test_a_chat_turn_never_calls_cancel_pending_for_agents(self, client, db, team, fakes, extras):
        from services import hitl_approval_service

        calls: list[list[int]] = []
        real = hitl_approval_service.cancel_pending_for_agents

        def spy(db_, agent_ids, reason):
            calls.append(list(agent_ids))
            return real(db_, agent_ids, reason)

        with patch.object(hitl_approval_service, "cancel_pending_for_agents", spy):
            cid = ok_turn(client, team, "one", selection(team["ai_a"]), who="author")["conversation_id"]
            ok_turn(client, team, "two", selection(team["ai_b"], silo=extras["silo"]), conversation_id=cid, who="author")
            ok_turn(client, team, "three", selection(team["ai_a"], skills=[extras["skill"]]), who="peer")
        assert calls == [], "nothing in a turn or a selection change may touch approval rules"

    def test_cancel_pending_for_agents_leaves_the_internal_agents_approvals_alone(self, client, db, team, fakes):
        """Positive control: the function does cancel a normal agent's pending approval, and given the internal
        agent's id as well it cancels nothing of the internal agent's."""
        from datetime import timezone

        from services import hitl_approval_service
        from services.conversation_service import ConversationService

        chat_cid = ok_turn(client, team, "hello", selection(team["ai_a"]), who="author")["conversation_id"]
        db.expire_all()
        internal_id = db.get(Conversation, chat_cid).agent_id
        normal = AgentFactory(app=db.get(App, team["app_id"]), has_memory=True)
        db.flush()
        normal_conv = ConversationService.create_conversation(db, normal.agent_id, {"user_id": team["author_id"]})
        now = datetime.now(timezone.utc)

        def pending(agent_id, conversation_id):
            row = HITLApproval(
                id=str(uuid.uuid4()), app_id=team["app_id"], agent_id=agent_id, conversation_id=conversation_id,
                thread_id="t", interrupt_id=uuid.uuid4().hex[:16], channel="playground", status="pending",
                actions=[], requested_by_user_id=team["author_id"], expires_at=now + timedelta(hours=1),
            )
            db.add(row)
            db.flush()
            return row.id

        normal_approval, internal_approval = pending(normal.agent_id, normal_conv.conversation_id), pending(internal_id, chat_cid)
        cancelled = hitl_approval_service.cancel_pending_for_agents(db, [normal.agent_id, internal_id], "approval_rules_changed")
        db.flush()  # the caller of the function commits
        db.expire_all()
        assert cancelled == 1
        assert db.get(HITLApproval, normal_approval).status == "cancelled"
        assert db.get(HITLApproval, internal_approval).status == "pending"


# ------------------------------------------------------------------ AC-23: threads


@pytest.fixture(autouse=True)
def threads(test_engine):
    return ThreadProbe(test_engine)


class TestThreadSeparation:
    def _session(self, db, cid) -> tuple[int, str]:
        db.expire_all()
        row = db.get(Conversation, cid)
        return row.agent_id, row.session_id

    def test_each_conversation_has_its_own_thread_and_history(self, client, db, threads, team, fakes):
        a = team["ai_a"]
        author_cid = ok_turn(client, team, "AUTHOR-MARKER hello", selection(a), who="author")["conversation_id"]
        peer_cid = ok_turn(client, team, "PEER-MARKER hello", selection(a), who="peer")["conversation_id"]
        second = ok_turn(client, team, "AUTHOR-MARKER again", selection(a), who="author")["conversation_id"]  # new conversation
        ok_turn(client, team, "AUTHOR-MARKER more", selection(a), conversation_id=author_cid, who="author")
        ok_turn(client, team, "PEER-MARKER more", selection(a), conversation_id=peer_cid, who="peer")

        agent_id, author_session = self._session(db, author_cid)
        _, peer_session = self._session(db, peer_cid)
        _, second_session = self._session(db, second)
        assert len({author_session, peer_session, second_session}) == 3
        expected = {f"thread_{agent_id}_{s}" for s in (author_session, peer_session, second_session)}
        assert threads.of_agent(agent_id) == expected, "no other thread (e.g. a shared one) may exist"
        threads.assert_agent_wide_thread_untouched(agent_id)

        def user_texts(cid, who):
            return [m["content"] for m in detail(client, team, cid, who=who)["messages"] if m["role"] == "user"]

        assert user_texts(author_cid, "author") == ["AUTHOR-MARKER hello", "AUTHOR-MARKER more"]
        assert user_texts(peer_cid, "peer") == ["PEER-MARKER hello", "PEER-MARKER more"]
        assert user_texts(second, "author") == ["AUTHOR-MARKER again"]
        # what each model call saw: no marker of the other user
        peer_inputs = [text_ for _, msgs in fakes.calls for kind, text_ in msgs if "PEER-MARKER" in text_]
        author_calls = [msgs for _, msgs in fakes.calls if any("AUTHOR-MARKER" in t for _, t in msgs)]
        assert peer_inputs and author_calls
        assert not [m for msgs in author_calls for _, m in msgs if "PEER-MARKER" in m]
        peer_calls = [msgs for _, msgs in fakes.calls if any("PEER-MARKER" in t for _, t in msgs)]
        assert not [m for msgs in peer_calls for _, m in msgs if "AUTHOR-MARKER" in m]

    def test_each_users_turns_are_only_theirs(self, client, db, team, fakes):
        a, b = team["ai_a"], team["ai_b"]
        author_cid = ok_turn(client, team, "x1", selection(a), who="author")["conversation_id"]
        peer_cid = ok_turn(client, team, "y1", selection(b), who="peer")["conversation_id"]
        ok_turn(client, team, "x2", selection(b), conversation_id=author_cid, who="author")
        db.expire_all()
        turns = {
            cid: [(t.turn_index, t.user_id, t.ai_service_id) for t in
                  db.query(ConversationTurn).filter_by(conversation_id=cid).order_by(ConversationTurn.turn_index)]
            for cid in (author_cid, peer_cid)
        }
        assert turns[author_cid] == [(1, team["author_id"], a), (2, team["author_id"], b)]
        assert turns[peer_cid] == [(1, team["peer_id"], b)]
        for cid, who, uid in ((author_cid, "author", "author_id"), (peer_cid, "peer", "peer_id")):
            infos = [m["turn"] for m in detail(client, team, cid, who=who)["messages"] if m["role"] == "agent"]
            assert [i["turn_index"] for i in infos] == [t[0] for t in turns[cid]]

    def test_a_reset_rotates_only_the_callers_thread(self, client, db, threads, team, fakes):
        a = team["ai_a"]
        author_cid = ok_turn(client, team, "author before", selection(a), who="author")["conversation_id"]
        peer_cid = ok_turn(client, team, "peer before", selection(a), who="peer")["conversation_id"]
        agent_id, author_old = self._session(db, author_cid)
        _, peer_session = self._session(db, peer_cid)
        peer_thread = f"thread_{agent_id}_{peer_session}"
        peer_rows = threads.rows(peer_thread)
        peer_state = conv_state(client, db, team, peer_cid, who="peer")
        assert threads.rows(f"thread_{agent_id}_{author_old}") > 0 and peer_rows > 0

        # the peer cannot reset the author's conversation; the author can
        assert client.post(f"{base(team['app_id'])}/conversations/{author_cid}/reset", headers=team["peer"]).status_code == 404
        assert threads.rows(f"thread_{agent_id}_{author_old}") > 0
        assert client.post(f"{base(team['app_id'])}/conversations/{author_cid}/reset", headers=team["author"]).status_code == 200

        _, author_new = self._session(db, author_cid)
        assert author_new != author_old
        assert threads.rows(f"thread_{agent_id}_{author_old}") == 0
        assert detail(client, team, author_cid, who="author")["messages"] == []
        assert self._session(db, peer_cid)[1] == peer_session
        assert threads.rows(peer_thread) == peer_rows
        assert conv_state(client, db, team, peer_cid, who="peer") == peer_state

        ok_turn(client, team, "author after", selection(a), conversation_id=author_cid, who="author")
        assert [m["content"] for m in detail(client, team, author_cid, who="author")["messages"]
                if m["role"] == "user"] == ["author after"]
        assert threads.of_agent(agent_id) == {
            f"thread_{agent_id}_{author_new}", peer_thread,
        }
        threads.assert_agent_wide_thread_untouched(agent_id)

    @pytest.mark.parametrize("registry", ["empty", "expired_entry_of_the_conversation"])
    def test_the_thread_never_depends_on_the_in_memory_session_registry(
        self, client, db, threads, team, fakes, monkeypatch, registry
    ):
        """The Chat path (``turn_config``) takes the thread from ``Conversation.session_id`` and never reads
        ``SessionManagementService._sessions`` (``agent_execution_service._prepare_turn``): whatever that registry
        holds (nothing, or a 3-day-old entry that the playground would discard and answer with a shared thread) the
        thread of a turn is the conversation's own, and the registry is neither consulted nor modified."""
        a = team["ai_a"]
        registry_dict: dict = {}
        monkeypatch.setattr(SessionManagementService, "_sessions", registry_dict)
        cid = ok_turn(client, team, "AUTHOR-MARKER one", selection(a), who="author")["conversation_id"]
        peer = ok_turn(client, team, "PEER-MARKER one", selection(a), who="peer")["conversation_id"]
        assert registry_dict == {}, "a Chat turn must not register in-memory sessions"
        agent_id, session = self._session(db, cid)
        _, peer_session = self._session(db, peer)

        expired = None
        if registry == "expired_entry_of_the_conversation":
            suffix = session.replace(f"conv_{agent_id}_", "")
            key = SessionManagementService()._generate_session_id(agent_id, {"user_id": team["author_id"]}, suffix)
            expired = InMemorySession(key, agent_id, {"user_id": team["author_id"]})
            expired.last_accessed = datetime.utcnow() - timedelta(days=3)
            registry_dict[key] = expired
            assert key in SessionManagementService._sessions and expired.is_expired(timedelta(hours=24))

        ok_turn(client, team, "AUTHOR-MARKER two", selection(a), conversation_id=cid, who="author")
        ok_turn(client, team, "PEER-MARKER two", selection(a), conversation_id=peer, who="peer")

        if expired is not None:
            assert registry_dict == {expired.id: expired}, "the registry was neither read nor changed"
            assert datetime.utcnow() - expired.last_accessed > timedelta(days=2)
        assert threads.of_agent(agent_id) == {
            f"thread_{agent_id}_{session}", f"thread_{agent_id}_{peer_session}",
        }
        threads.assert_agent_wide_thread_untouched(agent_id)
        assert [m["content"] for m in detail(client, team, cid, who="author")["messages"] if m["role"] == "user"] == [
            "AUTHOR-MARKER one", "AUTHOR-MARKER two",
        ]
        assert [m["content"] for m in detail(client, team, peer, who="peer")["messages"] if m["role"] == "user"] == [
            "PEER-MARKER one", "PEER-MARKER two",
        ]


class TestTurnWithoutConversation:
    """AC-23 at the execution layer: a per-turn override with no resolvable conversation fails in a controlled way and
    never falls back to a thread shared by the whole agent (``thread_{agent_id}``)."""

    @pytest.fixture
    def prepared(self, client, db, team, fakes):
        from services.internal_chat.selection_resolver import ChatSelectionResolver

        author_cid = ok_turn(client, team, "AUTHOR-MARKER", selection(team["ai_a"]), who="author")["conversation_id"]
        agent_id = db.get(Conversation, author_cid).agent_id
        config = ChatSelectionResolver.resolve_full(db, team["app_id"], _selection_model(team["ai_a"])).config
        return {"agent_id": agent_id, "config": config, "author_cid": author_cid}

    @staticmethod
    def _context(team, who):
        return {"user_id": team[f"{who}_id"], "app_id": team["app_id"], "oauth": True}

    async def _prepare(self, prepared, db, team, who, conversation_id):
        from services.agent_execution_service import AgentExecutionService

        return await AgentExecutionService()._prepare_turn(
            prepared["agent_id"], "hi", user_context=self._context(team, who),
            conversation_id=conversation_id, db=db, turn_config=prepared["config"],
        )

    @pytest.mark.parametrize("case,status", [("none", 400), ("missing", 404), ("someone_elses", 404)])
    async def test_it_is_a_controlled_error_and_writes_no_shared_thread(
        self, db, threads, team, fakes, prepared, case, status
    ):
        from fastapi import HTTPException

        agent_id = prepared["agent_id"]
        conversation_id = {"none": None, "missing": 987654321, "someone_elses": prepared["author_cid"]}[case]
        who = "peer" if case == "someone_elses" else "author"
        before = threads.of_agent(agent_id)
        calls = len(fakes.calls)
        with pytest.raises(HTTPException) as raised:
            await self._prepare(prepared, db, team, who, conversation_id)
        assert raised.value.status_code == status
        threads.assert_agent_wide_thread_untouched(agent_id)
        assert threads.of_agent(agent_id) == before
        assert len(fakes.calls) == calls

    async def test_the_own_conversation_resolves_to_its_own_thread(self, db, team, fakes, prepared):
        ctx = await self._prepare(prepared, db, team, "author", prepared["author_cid"])
        assert ctx.conversation.session_id.startswith(f"conv_{prepared['agent_id']}_")
        assert ctx.turn_config is prepared["config"]


# ------------------------------------------------------------------ a failing turn stays with its user


def tree(root) -> list[tuple[str, int]]:
    import os

    return sorted(
        (os.path.relpath(os.path.join(d, f), root), os.path.getsize(os.path.join(d, f)))
        for d, _, files in os.walk(root) for f in files
    )


class TestFailuresAndIntruders:
    @pytest.mark.parametrize("path", ["/messages", "/stream"])
    def test_a_failed_turn_of_one_user_leaves_the_other_users_state_alone(
        self, client, db, threads, team, fakes, authored, path
    ):
        a, b = team["ai_a"], team["ai_b"]
        cid = authored["cid"]
        peer_cid = ok_turn(client, team, "peer ok", selection(b), who="peer")["conversation_id"]
        defaults = client.get(f"{base(team['app_id'])}/defaults", headers=team["author"]).json()
        peer_defaults = client.get(f"{base(team['app_id'])}/defaults", headers=team["peer"]).json()
        db.expire_all()
        agent_id = db.get(Conversation, cid).agent_id
        author_thread = f"thread_{agent_id}_{db.get(Conversation, cid).session_id}"
        author_before = conv_state(client, db, team, cid)
        peer_turns = db.query(ConversationTurn).filter_by(conversation_id=peer_cid).count()
        peer_state = db.get(ChatConversationState, peer_cid).selection
        author_rows = threads.rows(author_thread)
        conversations = db.query(Conversation).filter(Conversation.user_id == team["peer_id"]).count()

        fakes.fail_services.add(b)
        for conversation_id in (peer_cid, None):  # an existing conversation, and a first turn
            response = send(client, team, "peer fails", selection(b), conversation_id, who="peer", path=path)
            if path == "/messages":
                assert response.status_code == 500 and response.json() == {"detail": "Agent execution failed"}
            else:
                events = [json.loads(l[6:]) for l in response.text.splitlines() if l.startswith("data: ")]
                assert events[-1]["type"] == "error" and "done" not in [e["type"] for e in events]
        fakes.fail_services.discard(b)

        db.expire_all()
        assert conv_state(client, db, team, cid) == author_before
        assert threads.rows(author_thread) == author_rows
        assert client.get(f"{base(team['app_id'])}/defaults", headers=team["author"]).json() == defaults
        assert client.get(f"{base(team['app_id'])}/defaults", headers=team["peer"]).json() == peer_defaults
        assert db.query(ConversationTurn).filter_by(conversation_id=peer_cid).count() == peer_turns
        assert db.get(ChatConversationState, peer_cid).selection == peer_state
        assert db.query(Conversation).filter(Conversation.user_id == team["peer_id"]).count() == conversations
        again = ok_turn(client, team, "author continues", selection(a), conversation_id=cid, who="author")
        assert again["response"] == f"hello from {a}" and again["turn"]["turn_index"] == 3

    def test_file_references_of_another_users_file_are_not_followed(self, client, db, team, fakes, authored):
        before = conv_state(client, db, team, authored["cid"])
        body = ok_turn_with_references(client, team, "peer asks", selection(team["ai_a"]), [authored["fid"]], who="peer")
        sent = " ".join(text_ for _, msgs in fakes.calls for _, text_ in msgs if "peer asks" in text_ or "AUTHOR-FILE-BODY" in text_)
        assert "AUTHOR-FILE-BODY" not in sent, "the peer's model input must not carry the author's file"
        assert body["metadata"]["files_processed"] == 0
        assert conv_state(client, db, team, authored["cid"]) == before
        download = client.get(
            f"{base(team['app_id'])}/conversations/{authored['cid']}/files/{authored['fid']}/download", headers=team["author"]
        )
        assert download.status_code == 200

    @pytest.mark.parametrize("path", ["/messages", "/stream"])
    def test_a_turn_with_files_and_a_foreign_conversation_writes_nothing(
        self, client, db, team, fakes, authored, path, tmp_path
    ):
        before_tree, before = tree(tmp_path), conv_state(client, db, team, authored["cid"])
        response = client.post(
            f"{base(team['app_id'])}{path}", headers=team["peer"],
            data=turn_form("with files", selection(team["ai_a"]), authored["cid"]),
            files=[("files", ("evil.txt", b"evil bytes", "text/plain"))],
        )
        assert (response.status_code, response.json()) == (404, NOT_FOUND)
        assert tree(tmp_path) == before_tree
        assert conv_state(client, db, team, authored["cid"]) == before
        assert len(fakes.calls) == authored["calls"]

    def test_refused_attempts_leave_the_intruders_own_data_unchanged(self, client, db, team, fakes, authored):
        ok_turn(client, team, "peer own", selection(team["ai_b"]), who="peer")
        url = f"{base(team['app_id'])}/defaults"
        defaults = client.get(url, headers=team["peer"]).json()

        def own():
            db.expire_all()
            row = db.get(ChatUserDefault, (team["peer_id"], team["app_id"]))
            conversations = db.query(Conversation).filter(Conversation.user_id == team["peer_id"]).count()
            turns = db.query(ConversationTurn).filter_by(user_id=team["peer_id"]).count()
            return row.selection, row.updated_at, conversations, turns

        before = own()
        conversation_requests(client, team["app_id"], authored["cid"], authored["fid"], team["peer"], selection(team["ai_a"]))
        assert own() == before
        assert client.get(url, headers=team["peer"]).json() == defaults

    @pytest.mark.parametrize("who", ["peer", "owner"])
    def test_a_foreign_id_and_a_missing_id_are_indistinguishable_on_every_endpoint(
        self, client, db, team, fakes, authored, who
    ):
        foreign = conversation_requests(
            client, team["app_id"], authored["cid"], authored["fid"], team[who], selection(team["ai_a"])
        )
        missing = conversation_requests(
            client, team["app_id"], 987654321, authored["fid"], team[who], selection(team["ai_a"])
        )
        assert foreign.keys() == missing.keys()
        for name in foreign:
            assert (name, foreign[name].status_code, foreign[name].content) == (
                name, missing[name].status_code, missing[name].content,
            ), name

    @pytest.mark.parametrize("who", ["omni", "omni_outside"])
    def test_the_omniadmin_fixture_really_makes_omniadmins(self, client, team, who):
        """Guards the OMNIADMIN rows of the privacy tests: an admin-only endpoint answers 200 for them, 403 for others."""
        assert client.get("/internal/admin/users", headers=team[who]).status_code == 200
        assert client.get("/internal/admin/users", headers=team["author"]).status_code == 403


def ok_turn_with_references(client, team, message, sel, file_ids, who):
    response = client.post(
        f"{base(team['app_id'])}/messages", headers=team[who],
        data={**turn_form(message, sel), "file_references": json.dumps(file_ids)},
    )
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------------------------------ FR-13 / frozen App


class TestFrozenApp:
    def test_turns_and_uploads_are_refused_but_reading_and_cleaning_up_still_work(self, client, db, team, fakes, authored):
        cid, fid = authored["cid"], authored["fid"]
        spare = client.post(
            f"{base(team['app_id'])}/conversations", headers=team["author"], json={"selection": selection(team["ai_a"])}
        ).json()["conversation_id"]
        peer_cid = ok_turn(client, team, "peer secret", selection(team["ai_a"]), who="peer")["conversation_id"]
        db.query(App).filter(App.app_id == team["app_id"]).update({"is_frozen": True})
        db.commit()
        url = f"{base(team['app_id'])}/conversations"
        h = team["author"]

        for path in ("/messages", "/stream"):
            assert send(client, team, "x", selection(team["ai_a"]), cid, who="author", path=path).status_code == 403
            assert send(client, team, "x", selection(team["ai_a"]), None, who="author", path=path).status_code == 403
        assert client.post(f"{url}/{cid}/files", headers=h, files={"file": ("n.txt", b"n", "text/plain")}).status_code == 403
        assert len(fakes.calls) == authored["calls"] + 1  # + the peer's turn before the freeze

        assert {c["conversation_id"] for c in client.get(url, headers=h).json()["conversations"]} == {cid, spare}
        assert client.get(f"{url}/{cid}", headers=h).status_code == 200
        assert client.get(f"{url}/{cid}/files", headers=h).status_code == 200
        assert client.get(f"{url}/{cid}/files/{fid}/download", headers=h).status_code == 200
        renamed = client.patch(f"{url}/{cid}", headers=h, json={"title": "kept"})
        assert renamed.status_code == 200 and renamed.json()["title"] == "kept"
        assert client.delete(f"{url}/{spare}", headers=h).status_code == 204
        # the freeze never opens another user's conversation
        assert client.get(f"{url}/{peer_cid}", headers=h).status_code == 404
        assert client.get(f"{url}/{peer_cid}", headers=team["peer"]).status_code == 200


# ------------------------------------------------------------------ AC-25: human approvals


class ToolCallingModel(FakeChatModel):
    """Asks for one tool call on the first model call of a run, answers with text once a tool message exists."""

    tool_name: str
    available: list = []

    def bind_tools(self, tools, **kwargs):
        super().bind_tools(tools, **kwargs)
        self.available = [getattr(t, "name", None) for t in tools]
        return self

    def _wants_tool(self, messages) -> bool:
        return self.tool_name in self.available and not any(m.type == "tool" for m in messages)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.rec.calls.append((self.service_id, [(m.type, m.text) for m in messages]))
        if self._wants_tool(messages):
            message = AIMessage(content="", tool_calls=[{"name": self.tool_name, "args": {"query": "q"}, "id": "call_1"}])
        else:
            message = AIMessage(content="answer after the tool was refused")
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        self.rec.calls.append((self.service_id, [(m.type, m.text) for m in messages]))
        if self._wants_tool(messages):
            chunk = AIMessageChunk(
                content="",
                tool_call_chunks=[{"name": self.tool_name, "args": json.dumps({"query": "q"}), "id": "call_1", "index": 0}],
            )
        else:
            chunk = AIMessageChunk(content="answer after the tool was refused")
        yield ChatGenerationChunk(message=chunk)


class TestHumanApprovals:
    @pytest.fixture
    def gated(self, db, team, fakes, monkeypatch):
        """A turn with the silo selected asks to run the retriever tool, which an approval rule gates (this test only)."""
        from langchain.agents.middleware import HumanInTheLoopMiddleware
        from langchain_core.tools import StructuredTool

        silo = Silo(name="gated-silo", app_id=team["app_id"], embedding_service_id=team["emb"])
        db.add(silo)
        db.commit()
        tool_name = f"retriever_silo_{silo.silo_id}"
        executed: list[str] = []

        def run(query: str = "") -> str:
            executed.append(query)
            return "retrieved"

        monkeypatch.setattr(
            "tools.agentTools.get_retriever_tool",
            lambda silo_, *a, **k: StructuredTool.from_function(func=run, name=tool_name, description="gated"),
        )
        monkeypatch.setattr(
            "tools.aiServiceTools.create_llm_from_service",
            lambda ai_service, temperature=0, is_vision=False: ToolCallingModel(
                service_id=ai_service.service_id, rec=fakes, tool_name=tool_name
            ),
        )
        monkeypatch.setattr(
            "tools.middleware.factory.build_agent_middlewares",
            lambda agent, llm, *a, **k: [HumanInTheLoopMiddleware(
                interrupt_on={tool_name: {"allowed_decisions": ["approve", "reject"]}}
            )],
        )
        return {"silo": silo.silo_id, "executed": executed, "tool": tool_name}

    def _approvals(self, db, app_id):
        db.expire_all()
        return db.query(HITLApproval).filter(HITLApproval.app_id == app_id).all()

    def test_a_gated_tool_in_a_message_turn_is_rejected_on_the_spot(self, client, db, team, fakes, gated):
        sel = selection(team["ai_a"], silo=gated["silo"])
        cid = ok_turn(client, team, "plain", selection(team["ai_a"]), who="author")["conversation_id"]
        response = send(client, team, "use the tool", sel, cid, who="author")
        assert response.status_code == 409, response.text  # ApprovalNotSupportedError.status_code
        error = response.json()["detail"]
        assert error["code"] == "approval_not_supported_in_channel"
        assert gated["tool"] in error["message"] and "cannot provide" in error["message"]
        self._assert_nothing_answerable(client, db, team, cid, gated, approval_id=error["approval_id"])

    def test_a_gated_tool_in_a_stream_turn_ends_in_an_error_event_without_an_interrupt(
        self, client, db, team, fakes, gated
    ):
        sel = selection(team["ai_a"], silo=gated["silo"])
        cid = ok_turn(client, team, "plain", selection(team["ai_a"]), who="author")["conversation_id"]
        response = send(client, team, "use the tool", sel, cid, who="author", path="/stream")
        assert response.status_code == 200  # the stream was opened; the refusal travels as an event
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        types = [e["type"] for e in events]
        assert types.count("error") == 1 and types[-1] == "error"
        assert "hitl_interrupt" not in types and "done" not in types
        error = events[-1]["data"]
        assert error["code"] == "approval_not_supported_in_channel"
        assert gated["tool"] in error["message"] and "cannot provide" in error["message"]
        self._assert_nothing_answerable(client, db, team, cid, gated, approval_id=error["approval_id"])

    def _assert_nothing_answerable(self, client, db, team, cid, gated, approval_id):
        assert gated["executed"] == [], "the gated tool must not run"
        rows = self._approvals(db, team["app_id"])
        assert len(rows) == 1
        row = rows[0]
        assert row.id == approval_id
        assert (row.status, row.resolution_reason, row.channel) == ("cancelled", "channel_not_interactive", "internal_chat")
        assert row.requested_by_user_id == team["author_id"] and row.decided_by_user_id is None
        assert [d["type"] for d in row.decisions] == ["reject"], "the only decision is the system's rejection"

        got = client.get(f"/internal/approvals/{row.id}", headers=team["author"])
        assert got.status_code == 200 and got.json()["status"] == "cancelled"
        decision = {"decisions": [{"action_id": "call_1", "type": "approve"}]}
        author_decide = client.post(f"/internal/approvals/{row.id}/decisions/stream", headers=team["author"], json=decision)
        author_cancel = client.post(f"/internal/approvals/{row.id}/cancel", headers=team["author"])
        for answer in (author_decide, author_cancel):
            assert answer.status_code == 409
            assert answer.json()["detail"]["code"] == "approval_already_decided"
            assert answer.json()["detail"]["status"] == "cancelled"
        for who in ("peer", "owner", "admin"):
            for answer in (
                client.get(f"/internal/approvals/{row.id}", headers=team[who]),
                client.post(f"/internal/approvals/{row.id}/decisions/stream", headers=team[who], json=decision),
                client.post(f"/internal/approvals/{row.id}/cancel", headers=team[who]),
            ):
                assert answer.status_code == 404, (who, answer.text)
                assert answer.json() == {"detail": {"code": "approval_not_found", "message": "Approval not found."}}
        assert gated["executed"] == []
        # nothing changed by those answers, the conversation is not left paused, and the next ordinary turn works
        db.expire_all()
        assert db.get(HITLApproval, row.id).status == "cancelled" and len(self._approvals(db, team["app_id"])) == 1
        assert detail(client, team, cid, who="author")["pending_approval"] is None
        state = db.get(ChatConversationState, cid)
        assert (state.busy_token, state.busy_until) == (None, None), "the rejected turn gave the conversation back"
        again = ok_turn(client, team, "next", selection(team["ai_a"]), conversation_id=cid, who="author")
        assert again["response"] == "answer after the tool was refused"

    @pytest.mark.parametrize("path", ["/messages", "/stream"])
    def test_a_failed_rejection_resume_still_ends_cancelled_and_stays_so(
        self, client, db, team, fakes, gated, monkeypatch, path
    ):
        """The resume that rejects the pause raises: the row must not stay DECIDING (the sweeper would re-pend it)."""

        fail = {"on": True}

        class FailingResumeModel(ToolCallingModel):
            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                if fail["on"] and any(m.type == "tool" for m in messages):
                    raise RuntimeError("provider down during the rejection resume")
                return super()._generate(messages, stop, run_manager, **kwargs)

            def _stream(self, messages, stop=None, run_manager=None, **kwargs):
                if fail["on"] and any(m.type == "tool" for m in messages):
                    raise RuntimeError("provider down during the rejection resume")
                yield from super()._stream(messages, stop, run_manager, **kwargs)

        monkeypatch.setattr(
            "tools.aiServiceTools.create_llm_from_service",
            lambda ai_service, temperature=0, is_vision=False: FailingResumeModel(
                service_id=ai_service.service_id, rec=fakes, tool_name=gated["tool"]
            ),
        )
        cid = ok_turn(client, team, "plain", selection(team["ai_a"]), who="author")["conversation_id"]
        response = send(client, team, "use the tool", selection(team["ai_a"], silo=gated["silo"]), cid,
                        who="author", path=path)
        if path == "/messages":
            assert response.status_code == 500, response.text
        else:
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
            assert events[-1]["type"] == "error" and "done" not in [e["type"] for e in events]
        assert gated["executed"] == [], "the gated tool must not run"

        rows = self._approvals(db, team["app_id"])
        assert len(rows) == 1
        row = rows[0]
        assert (row.status, row.resolution_reason, row.channel) == ("cancelled", "channel_not_interactive", "internal_chat")
        assert row.decided_by_user_id is None and row.decided_at is not None

        decision = {"decisions": [{"action_id": "call_1", "type": "approve"}]}
        for who in ("author", "peer", "owner", "admin"):
            answers = (
                client.post(f"/internal/approvals/{row.id}/decisions/stream", headers=team[who], json=decision),
                client.post(f"/internal/approvals/{row.id}/cancel", headers=team[who]),
            )
            for answer in answers:
                assert answer.status_code in (404, 409), (who, answer.text)
        assert gated["executed"] == []
        assert db.get(HITLApproval, row.id).status == "cancelled"

        # the author's next turn on the same conversation, provider healthy again
        fail["on"] = False
        again = send(client, team, "next", selection(team["ai_a"]), cid, who="author")
        assert again.status_code == 200, again.text
        assert again.json()["response"] == "answer after the tool was refused"
        # the dangling tool call was closed by the checkpoint recovery: the model saw the tool as refused
        last_input = [(t, c) for _, msgs in fakes.calls[-1:] for t, c in msgs]
        assert any(t == "tool" and "rejected" in c for t, c in last_input), last_input
        assert detail(client, team, cid, who="author")["pending_approval"] is None
        assert gated["executed"] == []

    @staticmethod
    def _failing_resume_and_strict_model(monkeypatch, fakes, gated):
        """The rejection resume raises BEFORE the HITL node commits; the model rejects unanswered tool calls."""
        from langgraph.graph.state import CompiledStateGraph
        from langgraph.types import Command

        fail = {"on": True}
        original = CompiledStateGraph.ainvoke

        async def ainvoke(self, input, *args, **kwargs):
            if fail["on"] and isinstance(input, Command):
                raise RuntimeError("checkpointer unavailable during the rejection resume")
            return await original(self, input, *args, **kwargs)

        class StrictModel(ToolCallingModel):
            """Like Anthropic/Mistral/Google: a history with an unanswered tool call is an error."""

            def _check(self, messages):
                pending: set[str] = set()
                for m in messages:
                    if m.type == "ai":
                        pending |= {c["id"] for c in (getattr(m, "tool_calls", None) or [])}
                    elif m.type == "tool":
                        pending.discard(m.tool_call_id)
                if pending:
                    raise ValueError(f"strict provider: tool calls without a result: {sorted(pending)}")

            def _generate(self, messages, *a, **k):
                self._check(messages)
                return super()._generate(messages, *a, **k)

            def _stream(self, messages, *a, **k):
                self._check(messages)
                yield from super()._stream(messages, *a, **k)

        monkeypatch.setattr(CompiledStateGraph, "ainvoke", ainvoke)
        monkeypatch.setattr(
            "tools.aiServiceTools.create_llm_from_service",
            lambda ai_service, temperature=0, is_vision=False: StrictModel(
                service_id=ai_service.service_id, rec=fakes, tool_name=gated["tool"]
            ),
        )
        return fail

    @pytest.mark.parametrize("path", ["/messages", "/stream"])
    def test_a_failure_before_the_rejection_is_recorded_does_not_poison_the_next_turn(
        self, client, db, team, fakes, gated, monkeypatch, path
    ):
        fail = self._failing_resume_and_strict_model(monkeypatch, fakes, gated)
        cid = ok_turn(client, team, "plain", selection(team["ai_a"]), who="author")["conversation_id"]
        response = send(client, team, "use the tool", selection(team["ai_a"], silo=gated["silo"]), cid,
                        who="author", path=path)
        assert (response.status_code == 500) if path == "/messages" else ("error" in response.text), response.text
        row = self._approvals(db, team["app_id"])[0]
        assert (row.status, row.resolution_reason) == ("cancelled", "channel_not_interactive")

        fail["on"] = False
        again = send(client, team, "next", selection(team["ai_a"]), cid, who="author")
        assert again.status_code == 200, again.text
        assert again.json()["response"] == "answer after the tool was refused"
        assert gated["executed"] == []

    def test_the_sweeper_cancels_a_stuck_chat_row_but_repends_other_channels(
        self, client, db, team, fakes, gated, monkeypatch
    ):
        """A backdated DECIDING row on a still-paused thread: Chat is cancelled, any other channel is re-pended."""
        from datetime import timezone

        from services import hitl_expiry_worker
        from services.agent_execution_service import AgentExecutionService

        fail = self._failing_resume_and_strict_model(monkeypatch, fakes, gated)
        # simulate a crash: the failure branch cannot close anything, so the thread stays paused
        async def nothing(*a, **k):
            return None

        monkeypatch.setattr(AgentExecutionService, "_close_unanswered_tool_calls", staticmethod(nothing))
        cid = ok_turn(client, team, "plain", selection(team["ai_a"]), who="author")["conversation_id"]
        send(client, team, "use the tool", selection(team["ai_a"], silo=gated["silo"]), cid, who="author")
        row = self._approvals(db, team["app_id"])[0]

        def backdate(channel):
            row.status, row.channel, row.resolution_reason = "deciding", channel, None
            row.decided_at = row.expires_at = datetime.now(timezone.utc) - timedelta(days=2)
            db.commit()

        backdate("mcp")
        client.portal.call(hitl_expiry_worker._recover_stuck, db)
        db.expire_all()
        assert db.get(HITLApproval, row.id).status == "pending", "other channels keep the previous behaviour"

        backdate("internal_chat")
        client.portal.call(hitl_expiry_worker._recover_stuck, db)
        db.expire_all()
        recovered = db.get(HITLApproval, row.id)
        assert (recovered.status, recovered.resolution_reason) == ("cancelled", "channel_not_interactive")
        assert fail["on"] and gated["executed"] == []

    def test_another_users_turn_is_not_affected_by_a_rejected_pause(self, client, db, team, fakes, gated):
        peer_cid = ok_turn(client, team, "peer plain", selection(team["ai_a"]), who="peer")["conversation_id"]
        author_cid = ok_turn(client, team, "author plain", selection(team["ai_a"]), who="author")["conversation_id"]
        refused = send(client, team, "tool", selection(team["ai_a"], silo=gated["silo"]), author_cid, who="author")
        assert refused.status_code == 409 and refused.json()["detail"]["code"] == "approval_not_supported_in_channel"
        detail_peer = detail(client, team, peer_cid, who="peer")
        assert detail_peer["pending_approval"] is None
        assert ok_turn(client, team, "peer next", selection(team["ai_a"]), conversation_id=peer_cid, who="peer")


# ------------------------------------------------------------------ metrics and billing attribution


class TestAttribution:
    def test_metrics_and_turn_rows_carry_the_user_who_sent_the_turn(self, client, db, team, fakes):
        a = team["ai_a"]
        author_cid = ok_turn(client, team, "from author 1", selection(a), who="author")["conversation_id"]
        peer_cid = ok_turn(client, team, "from peer 1", selection(team["ai_b"]), who="peer")["conversation_id"]
        sse_turn(client, team, "from author 2", selection(a), conversation_id=author_cid, who="author")
        ok_turn(client, team, "from owner 1", selection(a), who="owner")
        payloads = fakes.wait_payloads(4)
        events = [p["event"] for p in payloads]
        # paired per event (the order in which the background writes arrive is not part of the contract)
        assert sorted((e["user_id"], e["ai_service_id"]) for e in events) == sorted([
            (team["author_id"], a), (team["peer_id"], team["ai_b"]), (team["author_id"], a), (team["owner_id"], a),
        ])
        assert {e["caller_type"] for e in events} == {"INTERNAL_CHAT"}
        assert all(e.get("api_key_id") in (None, "") for e in events)
        db.expire_all()
        owners = {
            c.conversation_id: c.user_id for c in db.query(Conversation).filter(Conversation.conversation_id.in_([author_cid, peer_cid]))
        }
        assert owners == {author_cid: team["author_id"], peer_cid: team["peer_id"]}
        assert {t.user_id for t in db.query(ConversationTurn).filter_by(conversation_id=author_cid)} == {team["author_id"]}

    def test_system_model_usage_is_billed_to_the_sender_only(self, client, db, team, fakes, monkeypatch):
        monkeypatch.setenv("AICT_DEPLOYMENT_MODE", "saas")
        configure_factories(db)
        system = AIServiceFactory(app=None, name="platform-model-iso", description="gpt-sys")
        db.commit()
        system_id = system.service_id  # rolled back with the test transaction
        ok_turn(client, team, "a1", selection(system_id), who="author")
        ok_turn(client, team, "a2", selection(system_id), who="author")
        ok_turn(client, team, "p1", selection(system_id), who="peer")
        db.expire_all()
        users = [team[f"{n}_id"] for n in ("author", "peer", "owner", "admin")]
        records = {r.user_id: r.call_count for r in db.query(UsageRecord).filter(UsageRecord.user_id.in_(users))}
        assert records == {team["author_id"]: 2, team["peer_id"]: 1}


# ------------------------------------------------------------------ NFR-11: log hygiene

class RaisingModel(FakeChatModel):
    """A provider error that echoes the prompt back, as real provider 4xx bodies do."""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.rec.calls.append((self.service_id, [(m.type, m.text) for m in messages]))
        raise RuntimeError("provider rejected the request: " + messages[-1].text)

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        self._generate(messages)
        yield  # pragma: no cover


class TestLogHygiene:
    @pytest.mark.parametrize("path", ["/messages", "/stream"])
    @pytest.mark.parametrize("scenario", [
        "success",
        "mcp_server_fails",
        "llm_error_echoes_the_prompt",
    ])
    def test_a_turn_logs_no_content_token_or_mcp_header(
        self, client, db, team, fakes, debug_records, monkeypatch, path, scenario
    ):
        mcp_secret = f"mcp-header-secret-{uuid.uuid4().hex}"
        message = f"TOPSECRET-MESSAGE-{uuid.uuid4().hex}"
        server = "boom_srv" if scenario == "mcp_server_fails" else "srv"
        mcp = MCPConfig(
            name="with-headers",
            config={server: {"url": "http://mcp.invalid/x", "transport": "streamable_http",
                             "headers": {"X-Api-Key": mcp_secret, "Authorization": f"Bearer {mcp_secret}"}}},
            app_id=team["app_id"],
        )
        db.add(mcp)
        db.commit()
        if scenario == "llm_error_echoes_the_prompt":
            monkeypatch.setattr(
                "tools.aiServiceTools.create_llm_from_service",
                lambda ai_service, temperature=0, is_vision=False: RaisingModel(service_id=ai_service.service_id, rec=fakes),
            )
        token = team["author"]["Authorization"].split(" ", 1)[1]
        needles = {"message": message, "jwt": token, "jwt-signature": token.rsplit(".", 1)[1], "mcp header": mcp_secret}

        response = send(client, team, message, selection(team["ai_a"], mcps=[mcp.config_id]), who="author", path=path)
        if scenario == "llm_error_echoes_the_prompt":
            assert message in "".join(c for _, msgs in fakes.calls for _, c in msgs), "the model did see the message"
            if path == "/messages":
                assert response.status_code == 500
            else:
                events = [json.loads(l[6:]) for l in response.text.splitlines() if l.startswith("data: ")]
                assert [e["type"] for e in events].count("error") == 1 and events[-1]["type"] == "error"
        else:
            assert response.status_code == 200, response.text
        assert fakes.mcp_clients and mcp_secret in json.dumps(fakes.mcp_clients), "the MCP connection did get its headers"
        assert not any(mcp_secret in r.text for r in [response]), "nor does the client see the header values"

        records = list(debug_records.values())
        assert any("internal_chat.turn" in r.getMessage() for r in records), "the turn's own log line was captured"
        assert any(r.levelno == logging.DEBUG for r in records), "DEBUG records were captured"
        formatter = logging.Formatter()
        leaks = []
        for record in records:
            # message + traceback + every attribute (``extra=`` fields, args), not only the rendered message
            rendered = formatter.format(record) + " " + repr(record.__dict__)
            for label, needle in needles.items():
                if needle in rendered:
                    leaks.append((label, record.name, record.levelname, rendered[:240]))
        assert not leaks, leaks

    @pytest.mark.parametrize("path", ["/messages", "/stream"])
    def test_a_failed_turn_stores_no_content_in_the_metrics_errors_an_admin_reads(
        self, client, db, team, fakes, debug_records, monkeypatch, path
    ):
        from models.agent_execution_event import AgentExecutionEvent

        message = f"TOPSECRET-METRICS-{uuid.uuid4().hex}"
        monkeypatch.setattr(
            "tools.aiServiceTools.create_llm_from_service",
            lambda ai_service, temperature=0, is_vision=False: RaisingModel(service_id=ai_service.service_id, rec=fakes),
        )
        send(client, team, message, selection(team["ai_a"]), who="author", path=path)
        payloads = fakes.wait_payloads(1)
        event = payloads[-1]["event"]
        assert event["status"] == "ERROR" and event["error_code"] == "RuntimeError"
        assert message not in json.dumps(payloads)
        match = re.search(r"correlation_id=([0-9a-f]{8})", event["error_message"])
        assert match and event["error_message"].startswith("RuntimeError"), event["error_message"]
        correlation_id = match.group(1)
        assert any(
            f"correlation_id={correlation_id}" in r.getMessage() and "(chat turn)" in r.getMessage()
            for r in debug_records.values()
        ), "the dashboard entry matches a log line"

        # persist the captured payload (the fake replaced the real writer) and read it as the App owner
        db.add(AgentExecutionEvent(
            event_id=uuid.UUID(event["event_id"]), app_id=event["app_id"], agent_id=event["agent_id"],
            conversation_id=event["conversation_id"], user_id=event["user_id"], caller_type=event["caller_type"],
            started_at=datetime.fromisoformat(event["started_at"]), status=event["status"],
            error_code=event["error_code"], error_message=event["error_message"],
        ))
        db.commit()
        body = client.get(f"/internal/apps/{team['app_id']}/metrics/errors?range=24h", headers=team["owner"])
        assert body.status_code == 200, body.text
        assert message not in body.text
        assert correlation_id in body.text
