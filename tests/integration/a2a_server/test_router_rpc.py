"""HTTP-level coverage for the A2A JSON-RPC route (step_017, AD-4 step 4).

Every request sends `A2A-Version: 1.0` (the SDK's `validate_version`
decorator treats a missing header as protocol 0.3 and rejects a v1.0-named
method). Uses `a2a_committed_world` for the same reason as
`test_router_discovery.py`.
"""

from __future__ import annotations

import logging

import pytest

from a2a.server.cluster.version import TaskVersion
from a2a.types.a2a_pb2 import Task, TaskState, TaskStatus

from db.database import SessionLocal
from models.agent import Agent
from models.api_key import APIKey
from services.a2a_server.identity import context_for_owner, owner_for
from services.a2a_server.runtime import get_runtime
from services.a2a_server.sdk_models import get_sdk_models
from services.public_auth_service import PublicAuthService
from utils.a2a_config import get_a2a_config
from utils.security import hash_api_key

pytestmark = pytest.mark.integration

_HEADERS = {"A2A-Version": "1.0"}


@pytest.fixture(autouse=True)
def _clear_a2a_config_cache():
    get_a2a_config.cache_clear()
    yield
    get_a2a_config.cache_clear()


def _rpc_url(world, agent_id: int) -> str:
    return f"/a2a/v1/apps/{world.app_slug}/agents/{agent_id}"


def _get_task_request(task_id: str, request_id: int = 1) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "method": "GetTask", "params": {"id": task_id}}


class TestUniform404AndAuth:
    def test_missing_app_is_the_uniform_404(self, client, a2a_committed_world):
        world = a2a_committed_world
        resp = client.post(
            f"/a2a/v1/apps/does-not-exist-{world.app_id}/agents/{world.agent_public_id}",
            json=_get_task_request("x"),
            headers=_HEADERS,
        )
        assert resp.status_code == 404
        assert resp.json() == {"detail": "Not Found"}

    def test_api_key_agent_without_a_key_is_the_uniform_404(self, client, a2a_committed_world):
        world = a2a_committed_world
        resp = client.post(
            _rpc_url(world, world.agent_api_key_id), json=_get_task_request("x"), headers=_HEADERS
        )
        assert resp.status_code == 404
        assert resp.json() == {"detail": "Not Found"}

    def test_public_agent_without_a_key_is_401_with_www_authenticate(self, client, a2a_committed_world):
        world = a2a_committed_world
        resp = client.post(
            _rpc_url(world, world.agent_public_id), json=_get_task_request("x"), headers=_HEADERS
        )
        assert resp.status_code == 401
        assert "WWW-Authenticate" in resp.headers

    def test_public_agent_with_an_invalid_key_is_401(self, client, a2a_committed_world):
        world = a2a_committed_world
        resp = client.post(
            _rpc_url(world, world.agent_public_id),
            json=_get_task_request("x"),
            headers={**_HEADERS, "X-API-KEY": "not-a-real-key"},
        )
        assert resp.status_code == 401

    def test_public_agent_with_another_apps_key_is_401(self, client, a2a_committed_world):
        world = a2a_committed_world
        resp = client.post(
            _rpc_url(world, world.agent_public_id),
            json=_get_task_request("x"),
            headers={**_HEADERS, "X-API-KEY": world.other_key_raw},
        )
        assert resp.status_code == 401

    def test_public_agent_with_a_revoked_key_is_401(self, client, a2a_committed_world):
        world = a2a_committed_world
        session = SessionLocal()
        try:
            key = session.get(APIKey, world.key_2_id)
            key.is_active = False
            session.commit()
        finally:
            session.close()

        resp = client.post(
            _rpc_url(world, world.agent_public_id),
            json=_get_task_request("x"),
            headers={**_HEADERS, "X-API-KEY": world.key_2_raw},
        )
        assert resp.status_code == 401

    def test_no_task_row_is_created_by_any_of_the_above(self, client, a2a_committed_world):
        world = a2a_committed_world
        models = get_sdk_models()
        session = SessionLocal()
        try:
            before = session.query(models.task).count()
        finally:
            session.close()

        client.post(_rpc_url(world, world.agent_public_id), json=_get_task_request("x"), headers=_HEADERS)
        client.post(
            _rpc_url(world, world.agent_api_key_id), json=_get_task_request("x"), headers=_HEADERS
        )

        session = SessionLocal()
        try:
            after = session.query(models.task).count()
        finally:
            session.close()
        assert after == before

    def test_the_404_path_never_validates_a_key_when_the_app_is_missing(self, client, a2a_committed_world, monkeypatch):
        """NFR-2: no key-validation work beyond what `resolve()` already does
        uniformly runs when the app itself does not exist."""
        world = a2a_committed_world
        calls = []
        original = PublicAuthService.find_valid_key_for_app

        def _spy(self, db, app_id, api_key):
            calls.append((app_id, api_key))
            return original(self, db, app_id, api_key)

        monkeypatch.setattr(PublicAuthService, "find_valid_key_for_app", _spy)

        resp = client.post(
            f"/a2a/v1/apps/does-not-exist-{world.app_id}/agents/{world.agent_public_id}",
            json=_get_task_request("x"),
            headers={**_HEADERS, "X-API-KEY": "irrelevant"},
        )
        assert resp.status_code == 404
        assert calls == []


class TestBodyCap:
    def test_a_chunked_oversize_body_is_413_and_creates_no_task(self, client, a2a_committed_world, monkeypatch):
        world = a2a_committed_world
        monkeypatch.setenv("A2A_MAX_REQUEST_MB", "1")
        get_a2a_config.cache_clear()

        big_text = "x" * (2 * 1024 * 1024)
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "SendMessage",
            "params": {"message": {"messageId": "m1", "role": "ROLE_USER", "parts": [{"text": big_text}]}},
        }

        models = get_sdk_models()
        session = SessionLocal()
        try:
            before = session.query(models.task).count()
        finally:
            session.close()

        def _chunks():
            import json as _json

            body = _json.dumps(payload).encode()
            for i in range(0, len(body), 8192):
                yield body[i : i + 8192]

        resp = client.post(
            _rpc_url(world, world.agent_public_id),
            headers={**_HEADERS, "X-API-KEY": world.key_1_raw},
            content=_chunks(),
        )
        assert resp.status_code == 413

        session = SessionLocal()
        try:
            after = session.query(models.task).count()
        finally:
            session.close()
        assert after == before


class TestExtendedCard:
    def test_extended_card_requires_a_key(self, client, a2a_committed_world):
        world = a2a_committed_world
        payload = {"jsonrpc": "2.0", "id": 1, "method": "GetExtendedAgentCard", "params": {}}
        resp = client.post(_rpc_url(world, world.agent_public_id), json=payload, headers=_HEADERS)
        assert resp.status_code == 401

    def test_extended_card_contains_this_agents_examples(self, client, a2a_committed_world):
        world = a2a_committed_world
        session = SessionLocal()
        try:
            agent = session.get(Agent, world.agent_public_id)
            agent.a2a_examples = ["Summarize this document", "Translate to French"]
            session.commit()
        finally:
            session.close()

        payload = {"jsonrpc": "2.0", "id": 1, "method": "GetExtendedAgentCard", "params": {}}
        resp = client.post(
            _rpc_url(world, world.agent_public_id),
            json=payload,
            headers={**_HEADERS, "X-API-KEY": world.key_1_raw},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "result" in body
        skills = body["result"].get("skills", [])
        assert skills, "expected at least one skill on the extended card"
        all_examples = [example for skill in skills for example in skill.get("examples", [])]
        assert "Summarize this document" in all_examples
        assert "Translate to French" in all_examples


class TestMalformedIdShape:
    def test_an_overlong_task_id_is_rejected_before_dispatch(self, client, a2a_committed_world):
        world = a2a_committed_world
        resp = client.post(
            _rpc_url(world, world.agent_public_id),
            json=_get_task_request("x" * 100),
            headers={**_HEADERS, "X-API-KEY": world.key_1_raw},
        )
        assert resp.status_code == 200  # JSON-RPC errors are HTTP 200
        body = resp.json()
        assert body["error"]["code"] == -32602  # InvalidParamsError


class TestTerminalTaskPreCheck:
    async def test_send_message_naming_an_already_terminal_task_is_rejected_before_dispatch(
        self, client, a2a_committed_world
    ):
        """RB-5: the SDK path would still invoke the executor for a send
        naming an existing, already-terminal task (and leak two
        `EventQueueSource` tasks per rejected send, SDK 1.2.2) -- the router
        must reject before ever calling `dispatcher.handle_requests`."""
        world = a2a_committed_world
        rt = get_runtime()
        assert rt is not None

        owner = owner_for(world.app_id, world.agent_public_id, hash_api_key(world.key_1_raw))
        ctx = context_for_owner(owner)
        task_id = "rb5-terminal-task"
        task = Task(id=task_id, context_id="rb5-ctx", status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED))
        await rt.store.save(task, event=task, prev=None, prev_version=TaskVersion.MISSING, context=ctx)

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "SendMessage",
            "params": {
                "message": {
                    "messageId": "m1",
                    "taskId": task_id,
                    "role": "ROLE_USER",
                    "parts": [{"text": "hello"}],
                }
            },
        }
        resp = client.post(
            _rpc_url(world, world.agent_public_id),
            json=payload,
            headers={**_HEADERS, "X-API-KEY": world.key_1_raw},
        )
        assert resp.status_code == 200  # JSON-RPC errors are HTTP 200
        body = resp.json()
        assert "error" in body


class TestRequestLogging:
    def test_exactly_one_a2a_rpc_line_is_emitted_with_no_raw_key(self, client, a2a_committed_world, caplog):
        world = a2a_committed_world
        # `routers.a2a_server.router`'s logger has `propagate=False` (utils/logger.py),
        # so plain `caplog.at_level(...)` never sees it -- attach caplog's own
        # handler directly (same pattern as test_system_skills_seeder.py).
        import routers.a2a_server.router as router_module

        caplog.set_level(logging.INFO)
        router_module.logger.addHandler(caplog.handler)
        try:
            resp = client.post(
                _rpc_url(world, world.agent_public_id),
                json=_get_task_request("does-not-exist"),
                headers={**_HEADERS, "X-API-KEY": world.key_1_raw},
            )
        finally:
            router_module.logger.removeHandler(caplog.handler)
        assert resp.status_code == 200
        rpc_lines = [r for r in caplog.records if r.getMessage().startswith("a2a.rpc ")]
        assert len(rpc_lines) == 1
        message = rpc_lines[0].getMessage()
        assert "method=GetTask" in message
        assert f"app_id={world.app_id}" in message
        assert world.key_1_raw not in message
        assert hash_api_key(world.key_1_raw) not in message
