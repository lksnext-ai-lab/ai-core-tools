"""Integration: how the Chat router wires a turn into the execution stack (app-flexible-chat step_008).

The execution / streaming services are patched, so these tests pin the contract the router owes them (exact kwargs,
single hook per turn, prepared context) and what the client receives, without calling any LLM.
"""
import json
import os
from unittest.mock import AsyncMock, patch

import pytest

from models.agent import Agent
from models.app_collaborator import CollaborationRole
from models.conversation import Conversation
from models.hitl_approval import ApprovalChannel
from services.agent_execution_service import AgentExecutionService
from services.agent_streaming_service import AgentStreamingService
from services.conversation_service import ConversationService
from services.file_management_service import FileManagementService
from services.playground_media_service import PlaygroundMediaService
from tests.factories import AIServiceFactory, AppFactory, UserFactory, configure_factories
from tests.integration.routers.internal._eos_helpers import headers_for, member_headers


@pytest.fixture(autouse=True)
def _no_vectorize():
    with patch.object(PlaygroundMediaService, "vectorize_uploaded_file", return_value=False):
        yield


@pytest.fixture
def world(db):
    configure_factories(db)
    owner = UserFactory()
    app = AppFactory(owner=owner)
    ai = AIServiceFactory(app=app, description="gpt-x")
    db.flush()
    return {"app": app, "app_id": app.app_id, "ai": ai, "user": owner, "headers": headers_for(owner),
            "viewer": member_headers(db, app, CollaborationRole.VIEWER)}


def url(world, path):
    return f"/internal/apps/{world['app'].app_id}/chat{path}"


def form(world, **extra):
    data = {"message": "hi", "selection": json.dumps({"ai_service_id": world["ai"].service_id})}
    data.update(extra)
    return data


def create(client, world):
    response = client.post(url(world, "/conversations"), headers=world["headers"], json={})
    assert response.status_code == 200, response.text
    return response.json()["conversation_id"]


def completed(conversation_id):
    return {
        "response": "hello", "agent_id": 1, "conversation_id": conversation_id,
        "metadata": {"agent_name": "__internal__", "agent_type": "agent", "files_processed": 0},
        "turn": None,
    }


def internal_agent_id(db, world):
    return db.query(Agent).filter(Agent.app_id == world["app_id"], Agent.kind == "internal_chat").one().agent_id


def conversations(db, world):
    return db.query(Conversation).join(Agent, Agent.agent_id == Conversation.agent_id).filter(
        Agent.app_id == world["app_id"]
    ).count()


def test_messages_pass_the_prepared_turn_to_execution(client, db, world):
    cid = create(client, world)
    execute = AsyncMock(return_value=completed(cid))
    with patch.object(AgentExecutionService, "execute_agent_chat_with_file_refs", execute):
        response = client.post(url(world, "/messages"), headers=world["headers"], data=form(world, conversation_id=cid))
    assert response.status_code == 200, response.text
    kwargs = execute.call_args.kwargs
    assert kwargs["conversation_id"] == cid and kwargs["channel"] == ApprovalChannel.INTERNAL_CHAT
    assert kwargs["turn_config"].ai_service_id == world["ai"].service_id
    assert callable(kwargs["on_turn_completed"])
    context = kwargs["user_context"]
    assert context["caller_type_override"] == "INTERNAL_CHAT" and context["app_id"] == world["app"].app_id
    assert context["user_id"] == world["user"].user_id and "api_key" not in context
    assert kwargs["agent_id"] == internal_agent_id(db, world)
    body = response.json()
    assert body["response"] == "hello" and body["conversation_id"] == cid and body["turn"] is None
    assert body["metadata"]["turn_config"]["warnings"] == [] and "warnings" not in body
    assert not {"agent_id", "agent_name", "session_id"} & set(body["metadata"])


def test_first_turn_without_a_conversation_creates_it(client, db, world):
    seen = {}

    async def execute(self, **kwargs):
        seen.update(kwargs)
        return completed(kwargs["conversation_id"])

    assert conversations(db, world) == 0
    with patch.object(AgentExecutionService, "execute_agent_chat_with_file_refs", execute):
        response = client.post(url(world, "/messages"), headers=world["headers"], data=form(world))
    assert response.status_code == 200, response.text
    new_id = response.json()["conversation_id"]
    assert new_id == seen["conversation_id"] and conversations(db, world) == 1
    listed = client.get(url(world, "/conversations"), headers=world["headers"]).json()
    assert [c["conversation_id"] for c in listed["conversations"]] == [new_id]


def test_first_turn_that_cannot_run_creates_nothing(client, db, world):
    execute = AsyncMock(return_value=completed(1))
    stream = AsyncMock()
    world["app"].is_frozen = True
    db.flush()
    with patch.object(AgentExecutionService, "execute_agent_chat_with_file_refs", execute), \
            patch.object(AgentStreamingService, "stream_agent_chat", stream):
        for path in ("/messages", "/stream"):
            assert client.post(url(world, path), headers=world["headers"], data=form(world)).status_code == 403
        world["app"].is_frozen = False
        db.flush()
        for path in ("/messages", "/stream"):
            bad = form(world, selection=json.dumps({"ai_service_id": 987654}))
            response = client.post(url(world, path), headers=world["headers"], data=bad)
            assert response.status_code == 404 and response.json()["detail"] == "Resource not found"
    assert not execute.called and not stream.called
    assert conversations(db, world) == 0
    assert db.query(Agent).filter(Agent.app_id == world["app_id"], Agent.kind == "internal_chat").count() == 0


def test_malformed_references_or_search_params_are_422_and_create_nothing(client, db, world):
    execute = AsyncMock(return_value=completed(1))
    with patch.object(AgentExecutionService, "execute_agent_chat_with_file_refs", execute):
        for field, value in (("file_references", '["a",'), ("file_references", '{"a": 1}'),
                             ("search_params", "{bad"), ("search_params", "[1]")):
            for path in ("/messages", "/stream"):
                response = client.post(url(world, path), headers=world["headers"], data=form(world, **{field: value}))
                assert response.status_code == 422, (path, field, value)
    assert not execute.called and conversations(db, world) == 0


def test_stream_passes_the_prepared_turn_and_cleans_up(client, world):
    cid = create(client, world)
    ai_id = world["ai"].service_id  # the stream's release expires and its close detaches the session's objects
    seen = {}

    def fake_stream(self, **kwargs):
        seen.update(kwargs)
        # the turn's claim is released (and the session objects expired) when the stream ends: read it now
        seen["ai_service_id"] = kwargs["turn_config"].ai_service_id

        async def events():
            yield 'event: metadata\ndata: {"conversation_id": %d}\n\n' % kwargs["conversation_id"]
            yield 'event: done\ndata: {"turn": null}\n\n'

        return events()

    cleanup = AsyncMock()
    with patch.object(AgentStreamingService, "stream_agent_chat", fake_stream), \
            patch.object(FileManagementService, "cleanup_ephemeral_refs", cleanup):
        response = client.post(url(world, "/stream"), headers=world["headers"], data=form(world, conversation_id=cid))
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no" and response.headers["cache-control"] == "no-cache"
    assert "event: metadata" in response.text and "event: done" in response.text
    assert seen["conversation_id"] == cid and seen["channel"] == ApprovalChannel.INTERNAL_CHAT
    assert seen["ai_service_id"] == ai_id and callable(seen["on_turn_completed"])
    assert seen["user_context"]["caller_type_override"] == "INTERNAL_CHAT"
    assert isinstance(seen["agent_id"], int)
    cleanup.assert_awaited_once()  # the stream's finally ran


def test_a_file_uploaded_through_files_is_resolved_by_file_references(client, world):
    cid = create(client, world)
    uploaded = client.post(
        url(world, f"/conversations/{cid}/files"), headers=world["headers"],
        files={"file": ("notes.txt", b"hello notes", "text/plain")},
    )
    assert uploaded.status_code == 200, uploaded.text
    file_id = uploaded.json()["file_id"]
    execute = AsyncMock(return_value=completed(cid))
    with patch.object(AgentExecutionService, "execute_agent_chat_with_file_refs", execute):
        response = client.post(
            url(world, "/messages"), headers=world["headers"],
            data=form(world, conversation_id=cid, file_references=json.dumps([file_id])),
        )
        none_selected = client.post(
            url(world, "/messages"), headers=world["headers"],
            data=form(world, conversation_id=cid, file_references="[]"),
        )
    assert response.status_code == 200 and none_selected.status_code == 200
    first, second = execute.call_args_list
    assert [r.file_id for r in first.kwargs["file_references"]] == [file_id]
    assert second.kwargs["file_references"] == []


def test_download_link_expires_and_is_encoded(client, world):
    cid = create(client, world)
    file_id = client.post(
        url(world, f"/conversations/{cid}/files"), headers=world["headers"],
        files={"file": ("my notes & more.txt", b"x", "text/plain")},
    ).json()["file_id"]
    link = client.get(url(world, f"/conversations/{cid}/files/{file_id}/download"), headers=world["headers"]).json()
    assert "exp=" in link["download_url"] and "sig=" in link["download_url"]
    assert " " not in link["download_url"] and "%26" in link["download_url"]  # the "&" of the name is encoded
    assert link["filename"] == "my notes & more.txt"


def test_deleting_a_conversation_removes_its_attachment_storage(client, world):
    cid = create(client, world)
    assert client.post(
        url(world, f"/conversations/{cid}/files"), headers=world["headers"],
        files={"file": ("a.txt", b"x", "text/plain")},
    ).status_code == 200
    fms = FileManagementService()
    work_dir = os.path.join(fms.tmp_base_folder, "conversations", str(cid))
    session_dirs = [
        os.path.join(fms._persistent_dir, name) for name in os.listdir(fms._persistent_dir) if name.endswith(f"_user_{world['user'].user_id}_app_{world['app'].app_id}_conv_{cid}")
    ]
    assert os.path.isdir(work_dir) and session_dirs
    with patch.object(ConversationService, "delete_thread_history", new=AsyncMock()):
        assert client.delete(url(world, f"/conversations/{cid}"), headers=world["headers"]).status_code == 204
    assert not os.path.exists(work_dir) and not any(os.path.exists(d) for d in session_dirs)


def test_frozen_app_rejects_uploads_but_not_listing_or_downloads(client, db, world):
    cid = create(client, world)
    world["app"].is_frozen = True
    db.flush()
    files = {"file": ("a.txt", b"x", "text/plain")}
    assert client.post(url(world, f"/conversations/{cid}/files"), headers=world["headers"], files=files).status_code == 403
    assert client.get(url(world, f"/conversations/{cid}/files"), headers=world["headers"]).status_code == 200


# ------------------------------------------------------------------ empty conversation of a failed first turn


@pytest.mark.parametrize("path", ["/messages", "/stream"])
def test_first_turn_whose_files_fail_leaves_no_conversation(client, db, world, path):
    boom = AsyncMock(side_effect=RuntimeError("unsupported file"))
    with patch.object(FileManagementService, "resolve_chat_files", boom):
        with pytest.raises(RuntimeError):
            client.post(url(world, path), headers=world["headers"], data=form(world))
    assert boom.called and conversations(db, world) == 0


def test_first_turn_whose_execution_raises_leaves_no_conversation(client, db, world):
    execute = AsyncMock(side_effect=RuntimeError("llm down"))
    with patch.object(AgentExecutionService, "execute_agent_chat_with_file_refs", execute), \
            patch.object(ConversationService, "delete_thread_history", new=AsyncMock()):
        with pytest.raises(RuntimeError):
            client.post(url(world, "/messages"), headers=world["headers"], data=form(world))
    assert execute.called and conversations(db, world) == 0


def test_a_failed_turn_never_discards_an_existing_conversation(client, db, world):
    cid = create(client, world)
    execute = AsyncMock(side_effect=RuntimeError("llm down"))
    with patch.object(AgentExecutionService, "execute_agent_chat_with_file_refs", execute):
        with pytest.raises(RuntimeError):
            client.post(url(world, "/messages"), headers=world["headers"], data=form(world, conversation_id=cid))
    assert conversations(db, world) == 1
    assert client.get(url(world, f"/conversations/{cid}"), headers=world["headers"]).status_code == 200


def _stream_of(*events):
    def fake_stream(self, **kwargs):
        async def gen():
            for event in events:
                yield f"data: {json.dumps(event)}\n\n"
        return gen()
    return fake_stream


def test_stream_error_without_an_answer_discards_the_conversation_this_request_created(client, db, world):
    fake = _stream_of({"type": "metadata", "data": {}}, {"type": "error", "data": {"message": "x"}})
    with patch.object(AgentStreamingService, "stream_agent_chat", fake), \
            patch.object(ConversationService, "delete_thread_history", new=AsyncMock()):
        response = client.post(url(world, "/stream"), headers=world["headers"], data=form(world))
    assert response.status_code == 200 and '"type": "error"' in response.text
    assert conversations(db, world) == 0


def test_stream_that_completed_a_turn_keeps_the_conversation(client, db, world):
    """A stream that reached ``done`` (even if the client then goes away) never discards anything."""
    fake = _stream_of({"type": "metadata", "data": {}}, {"type": "done", "data": {"turn": None}},
                      {"type": "error", "data": {"message": "late"}})
    with patch.object(AgentStreamingService, "stream_agent_chat", fake):
        client.post(url(world, "/stream"), headers=world["headers"], data=form(world))
    assert conversations(db, world) == 1


def test_stream_error_never_discards_an_existing_conversation(client, db, world):
    cid = create(client, world)
    fake = _stream_of({"type": "error", "data": {"message": "x"}})
    with patch.object(AgentStreamingService, "stream_agent_chat", fake):
        client.post(url(world, "/stream"), headers=world["headers"], data=form(world, conversation_id=cid))
    assert conversations(db, world) == 1


async def test_hanging_up_on_the_first_error_event_still_discards_the_conversation(db, world):
    """The error chunk is held back until the discard ran, so a client that closes on it leaves nothing behind."""
    from types import SimpleNamespace

    from routers.internal.internal_chat import chat_stream

    fake = _stream_of({"type": "metadata", "data": {}}, {"type": "error", "data": {"message": "x"}})
    auth = SimpleNamespace(identity=SimpleNamespace(id=str(world["user"].user_id), email=world["user"].email))
    app_id = world["app_id"]
    with patch.object(AgentStreamingService, "stream_agent_chat", fake), \
            patch.object(ConversationService, "delete_thread_history", new=AsyncMock()):
        response = await chat_stream(
            app_id=app_id, request=SimpleNamespace(headers={}), message="hi", selection=form(world)["selection"],
            auth_context=auth, role=None, db=db, _=None,
        )
        iterator = response.body_iterator
        received = []
        async for chunk in iterator:
            received.append(chunk)
            if '"type": "error"' in chunk:
                break  # the client hangs up on the first error event
        await iterator.aclose()
    assert any('"type": "error"' in c for c in received)
    assert conversations(db, {"app_id": app_id}) == 0
