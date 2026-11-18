"""End-to-end JSON-RPC-over-HTTP coverage (step_022, AD-4 step 4 follow-up).

Fills the residual gap the step_017 review board flagged: a live
`SendStreamingMessage` HTTP round trip through a real `TestClient` request,
the real `A2ARuntime` the `client` fixture's lifespan builds, and the real
JSON-RPC dispatcher/SSE wrapper -- with only `AgentStreamingService.
stream_agent_events` monkeypatched to a scripted async generator (no LLM).

Every SSE frame this module reads is parsed as **test-side JSON only**: it
splits the raw `text/event-stream` body on `data: ` lines and
`json.loads`s each payload itself, exactly as any real A2A client would --
never by importing or calling anything from the bridge/dispatcher's own
SSE-frame-building code. That is what AC-15's "no SSE text is parsed
anywhere in the bridge" is checking from the *outside*.
"""

from __future__ import annotations

import json
import uuid

import pytest

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


def _send_streaming_payload(text: str = "hello", *, context_id: str | None = None) -> dict:
    message: dict = {
        "messageId": str(uuid.uuid4()),
        "role": "ROLE_USER",
        "parts": [{"text": text}],
    }
    if context_id is not None:
        message["contextId"] = context_id
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "SendStreamingMessage",
        "params": {"message": message},
    }


def _happy_path_fake(calls: list):
    """Mirrors `test_executor_bridge.py`'s `_happy_path_fake`: metadata, two
    token chunks, then a `done` whose `response` is the authoritative final
    text (`"Hello world"`, i.e. the concatenation of the two token chunks)."""

    async def _stream(
        self, agent_id, message, file_references=None, search_params=None,
        user_context=None, conversation_id=None, db=None, channel=None, resume=None,
    ):
        calls.append({"conversation_id": conversation_id})
        yield AgentStreamEvent("metadata", {"conversation_id": conversation_id})
        yield AgentStreamEvent("token", {"content": "Hello "})
        yield AgentStreamEvent("token", {"content": "world"})
        yield AgentStreamEvent(
            "done",
            {"response": "Hello world", "conversation_id": conversation_id, "files": []},
            extra={
                "structured": False,
                "parsed_response": None,
                "files_data": [],
                "conversation_id": conversation_id,
            },
        )

    return _stream


def _parse_sse_frames(raw_text: str) -> list[dict]:
    """Test-side-only SSE parsing (AC-15): splits on blank-line-delimited
    events (`sse_starlette` terminates each event with `\\r\\n\\r\\n`), keeps
    each event's `data:` line, and `json.loads`s it. Never touches any
    SDK/bridge SSE-building code."""
    frames: list[dict] = []
    for block in raw_text.replace("\r\n", "\n").split("\n\n"):
        data_lines = [
            line[len("data:"):].lstrip() for line in block.splitlines() if line.startswith("data:")
        ]
        if not data_lines:
            continue
        payload = "".join(data_lines)
        frames.append(json.loads(payload))
    return frames


def _frame_state(result: dict) -> str | None:
    """The `TaskState` string this frame reports, whether it is the initial
    `task` result (AC-14's SUBMITTED-then-WORKING shape) or a later
    `statusUpdate` event -- both carry `status.state`."""
    if "task" in result:
        return result["task"]["status"]["state"]
    if "statusUpdate" in result:
        return result["statusUpdate"]["status"]["state"]
    return None


class TestSendStreamingMessageHttpRoundTrip:
    """AC-15/AC-16: a live SendStreamingMessage HTTP round trip, SSE frames
    parsed test-side, through the real router + runtime + dispatcher."""

    def test_stream_emits_working_then_appended_artifacts_then_completed(
        self, client, a2a_committed_world, monkeypatch
    ):
        calls: list = []
        monkeypatch.setattr(AgentStreamingService, "stream_agent_events", _happy_path_fake(calls))

        world = a2a_committed_world
        with client.stream(
            "POST",
            _rpc_url(world, world.agent_public_id),
            json=_send_streaming_payload("hi"),
            headers={**_HEADERS, "X-API-KEY": world.key_1_raw},
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            raw_text = "".join(resp.iter_text())

        frames = _parse_sse_frames(raw_text)
        assert frames, "expected at least one SSE frame"

        # Every frame is a well-formed JSON-RPC 2.0 response envelope.
        for frame in frames:
            assert frame.get("jsonrpc") == "2.0"
            assert "result" in frame, f"frame had no 'result': {frame!r}"

        results = [frame["result"] for frame in frames]

        states = [_frame_state(r) for r in results]
        non_null_states = [s for s in states if s is not None]
        artifact_updates = [r["artifactUpdate"] for r in results if "artifactUpdate" in r]

        assert artifact_updates, "expected at least one artifactUpdate frame"

        # Order: the task opens at SUBMITTED/WORKING, a TASK_STATE_WORKING
        # status is reported before any artifact is appended, and the very
        # last frame overall is a terminal TASK_STATE_COMPLETED status.
        assert "TASK_STATE_WORKING" in non_null_states
        working_index = states.index("TASK_STATE_WORKING")
        assert states[-1] == "TASK_STATE_COMPLETED"

        # AC-16: no frame ever reports TASK_STATE_INPUT_REQUIRED.
        assert "TASK_STATE_INPUT_REQUIRED" not in non_null_states

        # The artifact-update frames all carry `append` semantics (the
        # first chunk is the only one that may omit it -- AD-6/output_mapper
        # convention) and their text parts concatenate to the final text.
        concatenated = ""
        for artifact in artifact_updates:
            assert artifact["artifact"]["artifactId"] == "response"
            for part in artifact["artifact"]["parts"]:
                concatenated += part.get("text", "")

        assert concatenated == "Hello world"

        # Every artifact-update frame appears strictly between the opening
        # `working` status and the closing `completed` one.
        completed_index = len(frames) - 1
        for i, result in enumerate(results):
            if "artifactUpdate" in result:
                assert working_index < i < completed_index

        assert len(calls) == 1

    def test_a_follow_up_with_the_same_context_id_reuses_the_conversation_and_a_new_task_id(
        self, client, a2a_committed_world, monkeypatch
    ):
        """AC-17: a follow-up SendStreamingMessage naming the same
        `contextId` passes the same `conversation_id` to
        `stream_agent_events`, and gets a new `taskId`."""
        conversation_ids: list = []

        def _fake_factory():
            async def _stream(
                self, agent_id, message, file_references=None, search_params=None,
                user_context=None, conversation_id=None, db=None, channel=None, resume=None,
            ):
                conversation_ids.append(conversation_id)
                yield AgentStreamEvent("metadata", {"conversation_id": conversation_id})
                yield AgentStreamEvent("token", {"content": "ok"})
                yield AgentStreamEvent(
                    "done",
                    {"response": "ok", "conversation_id": conversation_id, "files": []},
                    extra={
                        "structured": False, "parsed_response": None,
                        "files_data": [], "conversation_id": conversation_id,
                    },
                )

            return _stream

        monkeypatch.setattr(AgentStreamingService, "stream_agent_events", _fake_factory())

        world = a2a_committed_world
        url = _rpc_url(world, world.agent_public_id)
        headers = {**_HEADERS, "X-API-KEY": world.key_1_raw}

        with client.stream("POST", url, json=_send_streaming_payload("first"), headers=headers) as resp:
            assert resp.status_code == 200
            first_frames = _parse_sse_frames("".join(resp.iter_text()))

        first_task_id = next(f["result"]["task"]["id"] for f in first_frames if "task" in f["result"])
        context_id = next(f["result"]["task"]["contextId"] for f in first_frames if "task" in f["result"])
        assert context_id

        with client.stream(
            "POST", url, json=_send_streaming_payload("second", context_id=context_id), headers=headers
        ) as resp:
            assert resp.status_code == 200
            second_frames = _parse_sse_frames("".join(resp.iter_text()))

        second_task_id = next(f["result"]["task"]["id"] for f in second_frames if "task" in f["result"])
        second_context_id = next(
            f["result"]["task"]["contextId"] for f in second_frames if "task" in f["result"]
        )

        assert second_context_id == context_id
        assert second_task_id != first_task_id

        assert len(conversation_ids) == 2
        assert conversation_ids[0] is not None
        assert conversation_ids[0] == conversation_ids[1]
