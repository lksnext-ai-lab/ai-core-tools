"""Chat: no pooled DB connection is held across slow awaits; lost busy marker aborts; indexing budget; files cap."""
import time

import pytest

from models.app import App
from services import chat_attachment_service as attachment_module
from services.playground_media_service import PlaygroundMediaService
from tests.integration.internal_chat._chat_support import (  # noqa: F401  (fixtures + helpers)
    base,
    fakes,
    ok_turn,
    selection,
    turn_form,
    world,
    worker_session_on_test_db,
)


@pytest.fixture
def indexing(db, world, worker_session_on_test_db, monkeypatch):
    """Default embedding service on, the real indexing replaced by a recorder that probes the request's transaction."""
    db.get(App, world["app_id"]).default_embedding_service_id = world["emb"]
    db.commit()
    probe = {"in_tx": [], "calls": 0, "hook": None}

    def fake_vectorize(**kwargs):
        probe["in_tx"].append(db.in_transaction())  # the REQUEST's session, observed while its worker runs
        probe["calls"] += 1
        if probe["hook"] is not None:
            probe["hook"]()
        return True

    monkeypatch.setattr(PlaygroundMediaService, "vectorize_uploaded_file", staticmethod(fake_vectorize))
    return probe


def new_conversation(client, world):
    return ok_turn(client, world, "hello", selection(world["ai_a"]))["conversation_id"]


def post_turn(client, world, files, cid=None, path="/messages"):
    return client.post(
        base(world["app_id"]) + path, headers=world["alice"], data=turn_form("with files", selection(world["ai_a"]), cid),
        files=[("files", (f"f{i}.txt", b"some text content to index", "text/plain")) for i in range(files)],
    )


def test_an_upload_holds_no_connection_while_it_is_indexed(client, db, world, fakes, indexing):
    cid = new_conversation(client, world)
    response = client.post(
        f"{base(world['app_id'])}/conversations/{cid}/files", headers=world["alice"],
        files={"file": ("a.txt", b"some text content to index", "text/plain")},
    )
    assert response.status_code == 200, response.text
    assert indexing["in_tx"] == [False]


def test_a_turn_with_files_holds_no_connection_while_it_indexes(client, db, world, fakes, indexing):
    cid = new_conversation(client, world)
    response = post_turn(client, world, 1, cid)
    assert response.status_code == 200, response.text
    assert indexing["in_tx"] == [False]


def test_a_lost_busy_marker_aborts_the_turn_with_conversation_busy(client, db, world, fakes, indexing, monkeypatch):
    from repositories.internal_chat_repository import ChatConversationStateRepository as Repo

    cid = new_conversation(client, world)
    lost = {"on": False}
    real = Repo.renew_busy

    def renew(db_, conversation_id, token, ttl):
        return False if lost["on"] else real(db_, conversation_id, token, ttl)  # the marker was taken over

    monkeypatch.setattr(Repo, "renew_busy", staticmethod(renew))
    indexing["hook"] = lambda: lost.update(on=True)  # while the file is being indexed the marker is lost
    calls_before = len(fakes.calls)
    response = post_turn(client, world, 1, cid)
    assert response.status_code == 409, response.text
    assert response.json()["error_code"] == "CONVERSATION_BUSY"
    assert len(fakes.calls) == calls_before  # the model never ran


def test_the_indexing_budget_leaves_the_remaining_files_in_the_prompt(client, db, world, fakes, indexing, monkeypatch):
    monkeypatch.setattr("config.ATTACHMENT_INDEXING_TURN_BUDGET_S", 0.05, raising=False)
    indexing["hook"] = lambda: time.sleep(0.2)  # the first file alone uses up the whole budget
    cid = new_conversation(client, world)
    response = post_turn(client, world, 3, cid)
    assert response.status_code == 200, response.text
    assert indexing["calls"] == 1  # the other two were not indexed (they stay in the prompt)


def test_a_zero_budget_means_unlimited(client, db, world, fakes, indexing, monkeypatch):
    monkeypatch.setattr("config.ATTACHMENT_INDEXING_TURN_BUDGET_S", 0, raising=False)
    cid = new_conversation(client, world)
    assert post_turn(client, world, 3, cid).status_code == 200
    assert indexing["calls"] == 3


@pytest.mark.parametrize("path", ["/messages", "/stream"])
def test_more_files_than_the_cap_is_a_422_and_creates_nothing(client, db, world, fakes, indexing, monkeypatch, path):
    monkeypatch.setattr("config.CHAT_MAX_FILES_PER_TURN", 2, raising=False)
    response = post_turn(client, world, 3, path=path)
    assert response.status_code == 422, response.text
    assert response.json() == {"detail": "Too many files in one message (maximum 2)", "error_code": "TOO_MANY_FILES"}
    assert "text/event-stream" not in response.headers.get("content-type", "")  # a plain HTTP body, even for /stream
    assert fakes.calls == [] and indexing["calls"] == 0
    assert post_turn(client, world, 2, path=path).status_code == 200  # at the cap: accepted
