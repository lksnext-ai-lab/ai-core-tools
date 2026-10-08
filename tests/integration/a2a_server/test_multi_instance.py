"""HTTP-level multi-instance coverage (step_022, AC-33/AC-34).

Two independent `A2ARuntime`s (`a2a_runtime_factory`, step_012), "A" and "B",
share the same test DB and the same SDK store/stream tables -- exactly as
two `UVICORN_WORKERS` processes would. Both are driven through the real
`client` fixture's HTTP routes (`routers.a2a_server.router`); which runtime
instance actually serves a given request is controlled by monkeypatching
`routers.a2a_server.router.get_runtime` to return whichever of A/B is
"active" at that point -- the plan's documented alternative to standing up
two separate FastAPI apps. `AgentStreamingService.stream_agent_events` is
monkeypatched to a scripted async generator; no LLM calls.
"""

from __future__ import annotations

import asyncio
import time
import uuid

import pytest

import routers.a2a_server.router as router_module
from services.a2a_server.executor import MattinAgentExecutor
from services.agent_streaming_service import AgentStreamingService
from tools.streaming_utils import AgentStreamEvent
from utils.a2a_config import get_a2a_config

pytestmark = pytest.mark.integration

_HEADERS = {"A2A-Version": "1.0"}


@pytest.fixture(autouse=True)
def _clear_a2a_config_cache():
    get_a2a_config.cache_clear()
    yield
    get_a2a_config.cache_clear()


def _rpc_url(world, agent_id: int) -> str:
    return f"/a2a/v1/apps/{world.app_slug}/agents/{agent_id}"


class _ActiveWorker:
    """Monkeypatches `routers.a2a_server.router.get_runtime` so every HTTP
    request issued while this context is active is served by `rt`, while
    still exercising the real route/dispatcher code path -- the only thing
    swapped is *which* `A2ARuntime` instance (store/stream/in_flight) the
    route resolves."""

    def __init__(self, monkeypatch, rt) -> None:
        self._monkeypatch = monkeypatch
        self._rt = rt

    def __enter__(self):
        self._monkeypatch.setattr(router_module, "get_runtime", lambda: self._rt)
        return self._rt

    def __exit__(self, *exc_info) -> None:
        pass  # monkeypatch itself undoes this at test teardown


def _slow_fake(state: dict, *, chunks: int = 6, delay_s: float = 0.2):
    """Streams slowly enough that a concurrent GetTask/SubscribeToTask/
    CancelTask from "worker B" lands mid-stream, well before `done`."""

    async def _stream(
        self, agent_id, message, file_references=None, search_params=None,
        user_context=None, conversation_id=None, db=None,
    ):
        try:
            for i in range(chunks):
                state["count"] = i + 1
                yield AgentStreamEvent("token", {"content": "x"})
                await asyncio.sleep(delay_s)
            state["completed_normally"] = True
            yield AgentStreamEvent(
                "done",
                {"response": "x" * chunks, "conversation_id": conversation_id, "files": []},
                extra={
                    "structured": False, "parsed_response": None,
                    "files_data": [], "conversation_id": conversation_id,
                },
            )
        finally:
            state["stopped"] = True

    return _stream


def _send_message_payload(text: str, *, return_immediately: bool = True) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "SendMessage",
        "params": {
            "message": {"messageId": str(uuid.uuid4()), "role": "ROLE_USER", "parts": [{"text": text}]},
            "configuration": {"returnImmediately": return_immediately},
        },
    }


def _get_task_payload(task_id: str) -> dict:
    return {"jsonrpc": "2.0", "id": 2, "method": "GetTask", "params": {"id": task_id}}


def _cancel_task_payload(task_id: str) -> dict:
    return {"jsonrpc": "2.0", "id": 3, "method": "CancelTask", "params": {"id": task_id}}


def _subscribe_payload(task_id: str) -> dict:
    return {"jsonrpc": "2.0", "id": 4, "method": "SubscribeToTask", "params": {"id": task_id}}


class TestAC33CrossWorkerVisibility:
    def test_get_task_on_worker_b_shows_progress_then_terminal_for_a_task_started_on_a(
        self, client, a2a_committed_world, a2a_runtime_factory, monkeypatch
    ):
        state = {"count": 0, "stopped": False, "completed_normally": False}
        monkeypatch.setattr(AgentStreamingService, "stream_agent_events", _slow_fake(state))

        world = a2a_committed_world
        rt_a = a2a_runtime_factory(MattinAgentExecutor())
        rt_b = a2a_runtime_factory(MattinAgentExecutor())
        url = _rpc_url(world, world.agent_public_id)
        headers = {**_HEADERS, "X-API-KEY": world.key_1_raw}

        with _ActiveWorker(monkeypatch, rt_a):
            start_resp = client.post(url, json=_send_message_payload("hi"), headers=headers)
        assert start_resp.status_code == 200
        task_id = start_resp.json()["result"]["task"]["id"]

        with _ActiveWorker(monkeypatch, rt_b):
            mid_resp = client.post(url, json=_get_task_payload(task_id), headers=headers)
        assert mid_resp.status_code == 200
        mid_state = mid_resp.json()["result"]["status"]["state"]
        assert mid_state not in {"TASK_STATE_COMPLETED", "TASK_STATE_FAILED", "TASK_STATE_CANCELED"}, (
            "worker B should see the task still in progress shortly after worker A started it"
        )

        deadline = time.monotonic() + 5.0
        terminal_state = None
        while time.monotonic() < deadline:
            with _ActiveWorker(monkeypatch, rt_b):
                poll_resp = client.post(url, json=_get_task_payload(task_id), headers=headers)
            assert poll_resp.status_code == 200
            terminal_state = poll_resp.json()["result"]["status"]["state"]
            if terminal_state == "TASK_STATE_COMPLETED":
                break
            time.sleep(0.1)

        assert terminal_state == "TASK_STATE_COMPLETED", (
            f"worker B never observed the task reach TASK_STATE_COMPLETED (last seen: {terminal_state!r})"
        )
        assert state["completed_normally"] is True

    def test_subscribe_to_task_on_worker_b_yields_events_through_to_terminal(
        self, client, a2a_committed_world, a2a_runtime_factory, monkeypatch
    ):
        state = {"count": 0, "stopped": False, "completed_normally": False}
        monkeypatch.setattr(
            AgentStreamingService, "stream_agent_events", _slow_fake(state, chunks=3, delay_s=0.15)
        )

        world = a2a_committed_world
        rt_a = a2a_runtime_factory(MattinAgentExecutor())
        rt_b = a2a_runtime_factory(MattinAgentExecutor())
        url = _rpc_url(world, world.agent_public_id)
        headers = {**_HEADERS, "X-API-KEY": world.key_1_raw}

        with _ActiveWorker(monkeypatch, rt_a):
            start_resp = client.post(url, json=_send_message_payload("hi"), headers=headers)
        assert start_resp.status_code == 200
        task_id = start_resp.json()["result"]["task"]["id"]

        with _ActiveWorker(monkeypatch, rt_b):
            with client.stream("POST", url, json=_subscribe_payload(task_id), headers=headers) as resp:
                assert resp.status_code == 200
                raw_text = "".join(resp.iter_text())

        import json as _json

        frames = []
        for block in raw_text.replace("\r\n", "\n").split("\n\n"):
            data_lines = [
                line[len("data:"):].lstrip() for line in block.splitlines() if line.startswith("data:")
            ]
            if data_lines:
                frames.append(_json.loads("".join(data_lines)))

        assert frames, "SubscribeToTask on worker B yielded no SSE frames"

        def _state_of(result: dict):
            if "task" in result:
                return result["task"]["status"]["state"]
            if "statusUpdate" in result:
                return result["statusUpdate"]["status"]["state"]
            return None

        states = [s for s in (_state_of(f["result"]) for f in frames) if s is not None]
        assert states, "no frame carried a recognizable task/statusUpdate state"
        assert states[-1] == "TASK_STATE_COMPLETED"
        assert "TASK_STATE_INPUT_REQUIRED" not in states


class TestAC34CrossWorkerCancel:
    def test_cancel_task_on_worker_b_stops_the_fake_within_two_seconds_and_no_completed_follows(
        self, client, a2a_committed_world, a2a_runtime_factory, monkeypatch
    ):
        state = {"count": 0, "stopped": False, "completed_normally": False}
        monkeypatch.setattr(AgentStreamingService, "stream_agent_events", _slow_fake(state))

        world = a2a_committed_world
        rt_a = a2a_runtime_factory(MattinAgentExecutor())
        rt_b = a2a_runtime_factory(MattinAgentExecutor())
        url = _rpc_url(world, world.agent_public_id)
        headers = {**_HEADERS, "X-API-KEY": world.key_1_raw}

        with _ActiveWorker(monkeypatch, rt_a):
            start_resp = client.post(url, json=_send_message_payload("hi"), headers=headers)
        assert start_resp.status_code == 200
        task_id = start_resp.json()["result"]["task"]["id"]

        time.sleep(0.2)  # let worker A's stream actually start producing

        with _ActiveWorker(monkeypatch, rt_b):
            cancel_resp = client.post(url, json=_cancel_task_payload(task_id), headers=headers)
        assert cancel_resp.status_code == 200
        cancel_body = cancel_resp.json()
        assert "error" not in cancel_body, f"CancelTask via worker B failed: {cancel_body!r}"
        assert cancel_body["result"]["status"]["state"] == "TASK_STATE_CANCELED"

        start = time.monotonic()
        while not state["stopped"] and time.monotonic() - start < 2.0:
            time.sleep(0.05)
        elapsed = time.monotonic() - start
        assert state["stopped"] is True, f"worker A's fake stream did not stop within 2s (elapsed={elapsed:.3f}s)"
        assert elapsed < 2.0
        assert state["completed_normally"] is False

        with _ActiveWorker(monkeypatch, rt_b):
            final_resp = client.post(url, json=_get_task_payload(task_id), headers=headers)
        assert final_resp.status_code == 200
        assert final_resp.json()["result"]["status"]["state"] == "TASK_STATE_CANCELED"
