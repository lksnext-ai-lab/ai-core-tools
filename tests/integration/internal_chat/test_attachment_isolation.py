"""Integration: a client-supplied ``conversation_id`` on an upload must belong to the caller.

Persistent uploads are stored under ``tmp/conversations/{conversation_id}/{filename}`` (no user / App in the path), and
conversation ids are global and sequential. Without an ownership check, a user of App B could overwrite, link to or
delete a file of a Chat conversation of App A. Covers the playground upload, the playground stream / messages
(``resolve_chat_files``) and the public attach endpoint. Spec app-flexible-chat step_008 (correction round).
"""
import io
import os
from unittest.mock import patch

import pytest

from models.app_collaborator import CollaborationRole
from services.file_management_service import FileManagementService
from services.internal_chat.chat_service import InternalChatService
from services.playground_media_service import PlaygroundMediaService
from tests.factories import AgentFactory, AIServiceFactory, APIKeyFactory, AppFactory, UserFactory, configure_factories
from tests.integration.routers.internal._eos_helpers import headers_for, member_headers

VICTIM_BYTES = b"victim secret"


@pytest.fixture
def world(db):
    configure_factories(db)
    victim = UserFactory()
    app_a = AppFactory(owner=victim)
    ai_a = AIServiceFactory(app=app_a)
    attacker = UserFactory()
    app_b = AppFactory(owner=attacker)
    agent_b = AgentFactory(app=app_b, has_memory=True)
    db.flush()
    chat = InternalChatService(db, {"user_id": victim.user_id, "email": victim.email})
    conversation, _ = chat.create_conversation(app_a.app_id)
    return {
        "victim": victim, "attacker": attacker, "app_a": app_a, "app_b": app_b, "agent_b": agent_b, "ai_a": ai_a,
        "cid": conversation.conversation_id, "attacker_headers": headers_for(attacker), "chat": chat,
    }


@pytest.fixture(autouse=True)
def _no_vectorize():
    with patch.object(PlaygroundMediaService, "vectorize_uploaded_file", return_value=False):
        yield


async def _victim_file(world):
    from fastapi import UploadFile

    result = await world["chat"].upload_attachment(
        world["app_a"].app_id, world["cid"], UploadFile(filename="secret.txt", file=io.BytesIO(VICTIM_BYTES))
    )
    path = os.path.join(FileManagementService().tmp_base_folder, "conversations", str(world["cid"]), "secret.txt")
    assert open(path, "rb").read() == VICTIM_BYTES
    return result["file_id"], path


async def test_playground_upload_with_a_foreign_conversation_is_404(client, world):
    file_id, path = await _victim_file(world)
    before = (await world["chat"].list_attachments(world["app_a"].app_id, world["cid"]))["files"]
    base = f"/internal/apps/{world['app_b'].app_id}/agents/{world['agent_b'].agent_id}"
    response = client.post(
        f"{base}/upload-file", headers=world["attacker_headers"], data={"conversation_id": str(world["cid"])},
        files={"file": ("secret.txt", b"attacker bytes", "text/plain")},
    )
    assert response.status_code == 404
    assert open(path, "rb").read() == VICTIM_BYTES
    listed = await world["chat"].list_attachments(world["app_a"].app_id, world["cid"])
    assert [f["file_id"] for f in listed["files"]] == [f["file_id"] for f in before]
    assert file_id in [f["file_id"] for f in listed["files"]]


@pytest.mark.parametrize("endpoint", ["chat", "chat/stream"])
async def test_playground_turn_with_a_foreign_conversation_is_404(client, world, endpoint):
    _, path = await _victim_file(world)
    base = f"/internal/apps/{world['app_b'].app_id}/agents/{world['agent_b'].agent_id}"
    response = client.post(
        f"{base}/{endpoint}", headers=world["attacker_headers"],
        data={"message": "hi", "conversation_id": str(world["cid"])},
        files={"files": ("secret.txt", b"attacker bytes", "text/plain")},
    )
    assert response.status_code == 404
    assert open(path, "rb").read() == VICTIM_BYTES


async def test_public_attach_with_a_foreign_conversation_is_404(client, db, world):
    _, path = await _victim_file(world)
    key = APIKeyFactory(app=world["app_b"], user=world["attacker"])
    db.flush()
    response = client.post(
        f"/public/v1/app/{world['app_b'].app_id}/files/{world['agent_b'].agent_id}/attach-file",
        headers={"X-API-KEY": key.key}, data={"conversation_id": str(world["cid"])},
        files={"file": ("secret.txt", b"attacker bytes", "text/plain")},
    )
    assert response.status_code == 404
    assert open(path, "rb").read() == VICTIM_BYTES


def test_the_owner_flows_still_work(client, db, world):
    """Playground and public uploads into the caller's OWN conversation (and without one) are unaffected."""
    configure_factories(db)
    base = f"/internal/apps/{world['app_b'].app_id}/agents/{world['agent_b'].agent_id}"
    from services.conversation_service import ConversationService

    conversation = ConversationService.create_conversation(
        db, world["agent_b"].agent_id, {"user_id": world["attacker"].user_id}, title="mine"
    )
    for data in ({"conversation_id": str(conversation.conversation_id)}, {}):
        response = client.post(
            f"{base}/upload-file", headers=world["attacker_headers"], data=data,
            files={"file": ("mine.txt", b"mine", "text/plain")},
        )
        assert response.status_code == 200, response.text
    key = APIKeyFactory(app=world["app_b"], user=world["attacker"])
    db.flush()
    public = client.post(
        f"/public/v1/app/{world['app_b'].app_id}/files/{world['agent_b'].agent_id}/attach-file",
        headers={"X-API-KEY": key.key}, files={"file": ("mine.txt", b"mine", "text/plain")},
    )  # no conversation id: auto-created and owned by the key
    assert public.status_code == 200, public.text
    again = client.post(
        f"/public/v1/app/{world['app_b'].app_id}/files/{world['agent_b'].agent_id}/attach-file",
        headers={"X-API-KEY": key.key}, data={"conversation_id": public.json()["conversation_id"]},
        files={"file": ("mine2.txt", b"mine", "text/plain")},
    )
    assert again.status_code == 200, again.text


# ------------------------------------------------------------------ remaining file endpoints, public chat, "012"


async def test_every_other_file_endpoint_rejects_a_foreign_conversation(client, db, world):
    file_id, path = await _victim_file(world)
    cid = world["cid"]
    key = APIKeyFactory(app=world["app_b"], user=world["attacker"])
    db.flush()
    pg = f"/internal/apps/{world['app_b'].app_id}/agents/{world['agent_b'].agent_id}"
    pub_files = f"/public/v1/app/{world['app_b'].app_id}/files/{world['agent_b'].agent_id}"
    pub_chat = f"/public/v1/app/{world['app_b'].app_id}/chat/{world['agent_b'].agent_id}"
    h, k = world["attacker_headers"], {"X-API-KEY": key.key}
    requests = [
        client.get(f"{pg}/files", headers=h, params={"conversation_id": cid}),
        client.delete(f"{pg}/files/{file_id}", headers=h, params={"conversation_id": cid}),
        client.get(f"{pg}/files/{file_id}/download", headers=h, params={"conversation_id": cid}),
        client.get(f"{pub_files}/attached-files", headers=k, params={"conversation_id": cid}),
        client.delete(f"{pub_files}/detach-file/{file_id}", headers=k, params={"conversation_id": cid}),
        client.get(f"{pub_files}/files/{file_id}/download", headers=k, params={"conversation_id": cid}),
        client.post(f"{pub_chat}/call", headers=k, data={"message": "hi", "conversation_id": str(cid)},
                    files={"files": ("x.txt", b"x", "text/plain")}),
        client.post(f"{pub_chat}/call/stream", headers=k, data={"message": "hi", "conversation_id": str(cid)},
                    files={"files": ("x.txt", b"x", "text/plain")}),
    ]
    assert [r.status_code for r in requests] == [404] * len(requests)
    assert open(path, "rb").read() == VICTIM_BYTES
    listed = await world["chat"].list_attachments(world["app_a"].app_id, cid)
    assert file_id in [f["file_id"] for f in listed["files"]]  # the victim's file was not removed


def test_owner_can_list_download_and_remove_in_their_own_conversation(client, db, world):
    from services.conversation_service import ConversationService

    conversation = ConversationService.create_conversation(
        db, world["agent_b"].agent_id, {"user_id": world["attacker"].user_id}, title="mine"
    )
    cid = conversation.conversation_id
    base = f"/internal/apps/{world['app_b'].app_id}/agents/{world['agent_b'].agent_id}"
    h = world["attacker_headers"]
    file_id = client.post(
        f"{base}/upload-file", headers=h, data={"conversation_id": str(cid)},
        files={"file": ("mine.txt", b"mine", "text/plain")},
    ).json()["file_id"]
    assert client.get(f"{base}/files", headers=h, params={"conversation_id": cid}).status_code == 200
    assert client.get(f"{base}/files/{file_id}/download", headers=h, params={"conversation_id": cid}).status_code == 200
    assert client.delete(f"{base}/files/{file_id}", headers=h, params={"conversation_id": cid}).json()["success"]
    # without a conversation id (global session) nothing is checked
    assert client.get(f"{base}/files", headers=h).status_code == 200


def test_public_owner_flow_and_canonical_conversation_id(client, db, world):
    key = APIKeyFactory(app=world["app_b"], user=world["attacker"])
    db.flush()
    pub = f"/public/v1/app/{world['app_b'].app_id}/files/{world['agent_b'].agent_id}"
    k = {"X-API-KEY": key.key}
    first = client.post(f"{pub}/attach-file", headers=k, files={"file": ("a.txt", b"a", "text/plain")})
    cid = first.json()["conversation_id"]
    padded = client.post(
        f"{pub}/attach-file", headers=k, data={"conversation_id": f"0{cid}"}, files={"file": ("b.txt", b"b", "text/plain")}
    )
    assert padded.status_code == 200, padded.text
    assert padded.json()["conversation_id"] == str(cid)  # canonical, not "0<id>"
    base_dir = os.path.join(FileManagementService().tmp_base_folder, "conversations")
    assert not os.path.exists(os.path.join(base_dir, f"0{cid}"))
    listed = client.get(f"{pub}/attached-files", headers=k, params={"conversation_id": cid}).json()
    assert {f["filename"] for f in listed["files"]} == {"a.txt", "b.txt"}
    assert client.get(f"{pub}/attached-files", headers=k, params={"conversation_id": f"0{cid}"}).status_code == 200
