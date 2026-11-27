"""Integration (real PostgreSQL): HTTP smoke tests of ``/internal/apps/{app_id}/chat/...`` (app-flexible-chat step_008).

Covers the access rules (no role / unauthenticated / viewer), conversation CRUD, ownership and App isolation
(same 404 for "not yours" and "other App"), the frozen App, input validation, the per-conversation attachments and
the reset-vs-upload ordering. Turn execution itself (LLM) is covered by the service / execution tests.
"""
import io
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import UploadFile

from models.agent import Agent
from models.app_collaborator import CollaborationRole
from services.conversation_service import ConversationService
from services.internal_chat.chat_service import InternalChatService
from services.playground_media_service import PlaygroundMediaService
from tests.factories import AIServiceFactory, AppFactory, UserFactory, configure_factories
from tests.integration.routers.internal._eos_helpers import headers_for, member_headers

NOT_FOUND = {"detail": "Resource not found", "error_code": "NOT_FOUND"}


@pytest.fixture
def world(db):
    """App A (owner ``alice``) with one AI service, a viewer ``vera``, a second member ``mike``, an outsider."""
    configure_factories(db)
    alice = UserFactory()
    app = AppFactory(owner=alice)
    other_app = AppFactory(owner=alice)
    ai = AIServiceFactory(app=app, description="gpt-x")
    other_ai = AIServiceFactory(app=other_app, description="gpt-y")
    db.flush()
    return {
        "app": app,
        "other_app": other_app,
        "ai": ai,
        "other_ai": other_ai,
        "alice": headers_for(alice),
        "alice_user": alice,
        "viewer": member_headers(db, app, CollaborationRole.VIEWER),
        "mike": member_headers(db, app, CollaborationRole.EDITOR),
        "outsider": headers_for(UserFactory()),
    }


def base(app) -> str:
    return f"/internal/apps/{app.app_id}/chat"


def create(client, world, headers_key="viewer", **body):
    body.setdefault("selection", {"ai_service_id": world["ai"].service_id})
    response = client.post(f"{base(world['app'])}/conversations", headers=world[headers_key], json=body)
    assert response.status_code == 200, response.text
    return response.json()


def stream_form(cid, ai_id, selection=None):
    return {"message": "hi", "conversation_id": str(cid),
            "selection": selection if selection is not None else json.dumps({"ai_service_id": ai_id})}


def endpoints(cid=1):
    """(method, path suffix, request kwargs) of every endpoint of the router."""
    files = {"file": ("a.txt", b"hello", "text/plain")}
    return [
        ("get", "/options", {}),
        ("get", "/defaults", {}),
        ("put", "/defaults", {"json": {"ai_service_id": 1}}),
        ("get", "/conversations", {}),
        ("post", "/conversations", {"json": {}}),
        ("get", f"/conversations/{cid}", {}),
        ("patch", f"/conversations/{cid}", {"json": {"title": "x"}}),
        ("delete", f"/conversations/{cid}", {}),
        ("post", f"/conversations/{cid}/reset", {}),
        ("post", "/stream", {"data": stream_form(cid, 1)}),
        ("post", "/messages", {"data": stream_form(cid, 1)}),
        ("post", f"/conversations/{cid}/files", {"files": files}),
        ("get", f"/conversations/{cid}/files", {}),
        ("delete", f"/conversations/{cid}/files/some-file", {}),
        ("get", f"/conversations/{cid}/files/some-file/download", {}),
    ]


ENDPOINT_IDS = [f"{m}-{p}" for m, p, _ in endpoints()]


@pytest.mark.parametrize("index", range(len(ENDPOINT_IDS)), ids=ENDPOINT_IDS)
class TestAccess:
    def test_no_role_in_the_app_is_403(self, client, world, index):
        method, path, kwargs = endpoints()[index]
        response = getattr(client, method)(base(world["app"]) + path, headers=world["outsider"], **kwargs)
        assert response.status_code == 403

    def test_unauthenticated_is_rejected(self, client, world, index):
        method, path, kwargs = endpoints()[index]
        response = getattr(client, method)(base(world["app"]) + path, **kwargs)
        assert response.status_code in (401, 403)


def test_viewer_gets_options(client, world):
    response = client.get(f"{base(world['app'])}/options", headers=world["viewer"])
    assert response.status_code == 200
    body = response.json()
    assert body["has_usable_model"] is True
    assert [s["service_id"] for s in body["ai_services"]] == [world["ai"].service_id]
    assert body["default_selection"]["ai_service_id"] == world["ai"].service_id
    assert "supports_vision" not in body["ai_services"][0]


def test_defaults_get_and_put(client, world):
    url = f"{base(world['app'])}/defaults"
    assert client.get(url, headers=world["viewer"]).json()["ai_service_id"] == world["ai"].service_id
    put = client.put(url, headers=world["viewer"], json={"ai_service_id": world["ai"].service_id, "skill_ids": []})
    assert put.status_code == 200 and put.json()["ai_service_id"] == world["ai"].service_id
    assert client.put(url, headers=world["viewer"], json={"ai_service_id": 987654}).status_code == 404


def test_listing_never_creates_the_internal_agent(client, db, world):
    response = client.get(f"{base(world['app'])}/conversations", headers=world["viewer"])
    assert response.status_code == 200 and response.json() == {"conversations": [], "total": 0}
    assert db.query(Agent).filter(Agent.app_id == world["app"].app_id, Agent.kind == "internal_chat").count() == 0


def test_create_list_rename_detail_delete(client, world):
    url = base(world["app"])
    created = create(client, world, title="First")
    cid = created["conversation_id"]
    assert created["title"] == "First" and created["selection"]["ai_service_id"] == world["ai"].service_id
    assert "session_id" not in created and "agent_id" not in created

    listed = client.get(f"{url}/conversations", headers=world["viewer"]).json()
    assert listed["total"] == 1 and listed["conversations"][0]["conversation_id"] == cid

    renamed = client.patch(f"{url}/conversations/{cid}", headers=world["viewer"], json={"title": "Renamed"})
    assert renamed.status_code == 200 and renamed.json()["title"] == "Renamed"

    detail = client.get(f"{url}/conversations/{cid}", headers=world["viewer"])
    assert detail.status_code == 200
    assert detail.json()["messages"] == []
    assert detail.json()["current_selection"]["ai_service_id"] == world["ai"].service_id

    with patch.object(ConversationService, "delete_thread_history", new=AsyncMock()):
        assert client.delete(f"{url}/conversations/{cid}", headers=world["viewer"]).status_code == 204
    assert client.get(f"{url}/conversations/{cid}", headers=world["viewer"]).status_code == 404
    assert client.get(f"{url}/conversations", headers=world["viewer"]).json()["total"] == 0


def test_conversation_without_selection_uses_the_default(client, world):
    response = client.post(f"{base(world['app'])}/conversations", headers=world["viewer"], json={})
    assert response.status_code == 200
    assert response.json()["selection"]["ai_service_id"] == world["ai"].service_id


def test_list_is_paginated_with_a_bounded_limit(client, world):
    for _ in range(3):
        create(client, world)
    url = f"{base(world['app'])}/conversations"
    page = client.get(url, headers=world["viewer"], params={"limit": 2, "offset": 0}).json()
    assert len(page["conversations"]) == 2 and page["total"] == 3
    assert len(client.get(url, headers=world["viewer"], params={"limit": 2, "offset": 2}).json()["conversations"]) == 1
    for bad in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
        assert client.get(url, headers=world["viewer"], params=bad).status_code == 422


def test_request_validation(client, world):
    url = f"{base(world['app'])}/conversations"
    ai = world["ai"].service_id
    assert client.post(url, headers=world["viewer"], json={"unknown": 1}).status_code == 422
    assert client.post(url, headers=world["viewer"], json={"selection": {"ai_service_id": ai, "x": 1}}).status_code == 422
    too_many = {"ai_service_id": ai, "skill_ids": list(range(51))}
    assert client.post(url, headers=world["viewer"], json={"selection": too_many}).status_code == 422
    too_many = {"ai_service_id": ai, "mcp_config_ids": list(range(51))}
    assert client.post(url, headers=world["viewer"], json={"selection": too_many}).status_code == 422
    cid = create(client, world)["conversation_id"]
    assert client.patch(f"{url}/{cid}", headers=world["viewer"], json={"title": ""}).status_code == 422
    assert client.patch(f"{url}/{cid}", headers=world["viewer"], json={"title": "x", "agent_id": 1}).status_code == 422


def test_invalid_selection_is_the_single_not_found(client, world, db):
    for service_id in (987654, world["other_ai"].service_id):  # missing / of another App: indistinguishable
        response = client.post(
            f"{base(world['app'])}/conversations", headers=world["viewer"], json={"selection": {"ai_service_id": service_id}}
        )
        assert response.status_code == 404 and response.json() == NOT_FOUND


def test_retired_service_is_409(client, world, db):
    from datetime import datetime, timedelta

    world["ai"].end_of_service_at = datetime.utcnow() - timedelta(days=1)
    db.flush()
    response = client.post(
        f"{base(world['app'])}/conversations", headers=world["viewer"],
        json={"selection": {"ai_service_id": world["ai"].service_id}},
    )
    assert response.status_code == 409 and response.json()["error_code"] == "SERVICE_RETIRED"


# ------------------------------------------------------------------ isolation


def other_user_requests(cid):
    return [
        ("get", f"/conversations/{cid}", {}),
        ("patch", f"/conversations/{cid}", {"json": {"title": "x"}}),
        ("delete", f"/conversations/{cid}", {}),
        ("post", f"/conversations/{cid}/reset", {}),
        ("post", f"/conversations/{cid}/files", {"files": {"file": ("a.txt", b"hello", "text/plain")}}),
        ("get", f"/conversations/{cid}/files", {}),
        ("delete", f"/conversations/{cid}/files/some-file", {}),
        ("get", f"/conversations/{cid}/files/some-file/download", {}),
        ("post", "/stream", {"data": None}),
        ("post", "/messages", {"data": None}),
    ]


def test_another_user_of_the_same_app_gets_404(client, world):
    cid = create(client, world, "viewer")["conversation_id"]
    for method, path, kwargs in other_user_requests(cid):
        if "data" in kwargs:
            kwargs = {"data": stream_form(cid, world["ai"].service_id)}
        response = getattr(client, method)(base(world["app"]) + path, headers=world["mike"], **kwargs)
        assert response.status_code == 404, (method, path, response.status_code)
        assert response.json() == NOT_FOUND
    # untouched for the owner
    assert client.get(f"{base(world['app'])}/conversations/{cid}", headers=world["viewer"]).status_code == 200
    # and mike's own list does not show it
    assert client.get(f"{base(world['app'])}/conversations", headers=world["mike"]).json()["total"] == 0


def test_conversation_of_another_app_gets_404(client, world):
    # alice owns BOTH apps: the conversation exists and is hers, but not in the App of the URL
    response = client.post(
        f"{base(world['other_app'])}/conversations", headers=world["alice"],
        json={"selection": {"ai_service_id": world["other_ai"].service_id}},
    )
    assert response.status_code == 200, response.text
    foreign_cid = response.json()["conversation_id"]
    for method, path, kwargs in other_user_requests(foreign_cid):
        if "data" in kwargs:
            kwargs = {"data": stream_form(foreign_cid, world["ai"].service_id)}
        reply = getattr(client, method)(base(world["app"]) + path, headers=world["alice"], **kwargs)
        assert reply.status_code == 404, (method, path, reply.status_code)
        assert reply.json() == NOT_FOUND


# ------------------------------------------------------------------ frozen App


def test_frozen_app_blocks_new_activity_but_not_listing_or_deleting(client, world, db):
    cid = create(client, world)["conversation_id"]
    world["app"].is_frozen = True
    db.flush()
    url = base(world["app"])
    ai = world["ai"].service_id
    assert client.get(f"{url}/options", headers=world["viewer"]).status_code == 403
    assert client.post(f"{url}/conversations", headers=world["viewer"], json={}).status_code == 403
    assert client.post(f"{url}/stream", headers=world["viewer"], data=stream_form(cid, ai)).status_code == 403
    assert client.post(f"{url}/messages", headers=world["viewer"], data=stream_form(cid, ai)).status_code == 403
    assert client.get(f"{url}/conversations", headers=world["viewer"]).json()["total"] == 1
    with patch.object(ConversationService, "delete_thread_history", new=AsyncMock()):
        assert client.delete(f"{url}/conversations/{cid}", headers=world["viewer"]).status_code == 204


def test_stream_validation_errors_are_http_errors_not_sse(client, world):
    cid = create(client, world)["conversation_id"]
    url = f"{base(world['app'])}/stream"
    ai = world["ai"].service_id
    for bad in ("not json", "[]", json.dumps({"ai_service_id": ai, "extra": 1}), json.dumps({})):
        response = client.post(url, headers=world["viewer"], data=stream_form(cid, ai, bad))
        assert response.status_code == 422, bad
        assert "text/event-stream" not in response.headers.get("content-type", "")
    unknown = client.post(url, headers=world["viewer"], data=stream_form(cid, 987654))
    assert unknown.status_code == 404 and unknown.json() == NOT_FOUND
    no_conversation = client.post(url, headers=world["viewer"], data={"message": "hi", "selection": "{}"})
    assert no_conversation.status_code == 422  # the selection is invalid ({} has no ai_service_id)


# ------------------------------------------------------------------ attachments


@pytest.fixture
def vectorize_off():
    with patch.object(PlaygroundMediaService, "vectorize_uploaded_file", return_value=False):
        yield


def test_attachments_are_scoped_to_the_conversation(client, world, vectorize_off):
    url = base(world["app"])
    first = create(client, world)["conversation_id"]
    second = create(client, world)["conversation_id"]

    uploaded = client.post(
        f"{url}/conversations/{first}/files", headers=world["viewer"], files={"file": ("a.txt", b"hello", "text/plain")}
    )
    assert uploaded.status_code == 200, uploaded.text
    file_id = uploaded.json()["file_id"]

    listed = client.get(f"{url}/conversations/{first}/files", headers=world["viewer"]).json()
    assert [f["file_id"] for f in listed["files"]] == [file_id]
    assert client.get(f"{url}/conversations/{second}/files", headers=world["viewer"]).json()["files"] == []

    # the id of a file of ANOTHER conversation (same user) is not found here: no IDOR by guessing ids
    assert client.get(f"{url}/conversations/{second}/files/{file_id}/download", headers=world["viewer"]).status_code == 404
    assert client.delete(f"{url}/conversations/{second}/files/{file_id}", headers=world["viewer"]).status_code == 404

    download = client.get(f"{url}/conversations/{first}/files/{file_id}/download", headers=world["viewer"])
    assert download.status_code == 200 and download.json()["filename"] == "a.txt"
    assert "/static/" in download.json()["download_url"]

    assert client.delete(f"{url}/conversations/{first}/files/{file_id}", headers=world["viewer"]).json()["success"]
    assert client.get(f"{url}/conversations/{first}/files", headers=world["viewer"]).json()["files"] == []
    assert client.delete(f"{url}/conversations/{first}/files/{file_id}", headers=world["viewer"]).status_code == 404


async def test_reset_removes_the_old_attachments_but_not_one_uploaded_after_it(db, world, vectorize_off):
    """A is attached, B arrives right after the reset's commit (inside the old-thread delete): only A goes."""
    app_id = world["app"].app_id
    user_id = world["alice_user"].user_id
    chat = InternalChatService(db, {"user_id": user_id, "email": world["alice_user"].email})
    conversation, _ = chat.create_conversation(app_id)
    cid = conversation.conversation_id

    def upload(name):
        return chat.upload_attachment(app_id, cid, UploadFile(filename=name, file=io.BytesIO(b"content " + name.encode())))

    file_a = (await upload("a.txt"))["file_id"]
    uploaded_b: dict = {}

    async def thread_delete_after_commit(agent_id, session_id, strict=False):
        # the reset's transaction is committed here: the conversation already has its NEW session id
        uploaded_b.update(await upload("b.txt"))

    with patch.object(ConversationService, "delete_thread_history", new=thread_delete_after_commit):
        await chat.reset_conversation(app_id, cid)

    remaining = [f["file_id"] for f in (await chat.list_attachments(app_id, cid))["files"]]
    assert remaining == [uploaded_b["file_id"]]
    assert file_a not in remaining
    await chat.remove_attachment(app_id, cid, uploaded_b["file_id"])
