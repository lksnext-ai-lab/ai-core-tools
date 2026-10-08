"""Unit coverage for `services.a2a_server.response_sanitizer` (step_017 fix round 1, CRITICAL-2).

A sanitized `-32603` response must never keep the original response's
`Content-Length`: `JSONResponse` must compute a fresh one for the rewritten
(shorter or longer) body, or an HTTP/1.1 client raises "Too little data for
declared Content-Length" (h11) when the header disagrees with the actual
bytes sent.
"""

from __future__ import annotations

import json

import pytest
from fastapi.responses import JSONResponse
from starlette.responses import Response

from services.a2a_server.response_sanitizer import (
    INTERNAL_ERROR_CODE,
    RETRYABLE_ERROR_MESSAGE,
    derive_outcome,
    extract_task_id_from_sse_item,
    sanitize_error_payload,
    sanitize_json_response,
    sanitize_sse_item,
)

pytestmark = pytest.mark.unit


class TestSanitizeErrorPayload:
    def test_rewrites_a_minus_32603_error(self):
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": INTERNAL_ERROR_CODE, "message": "connection to server at ... failed"},
        }
        changed = sanitize_error_payload(payload)
        assert changed is True
        assert payload["error"]["message"] == RETRYABLE_ERROR_MESSAGE
        assert payload["error"]["data"] == {"retryable": True}

    def test_leaves_other_error_codes_untouched(self):
        payload = {"error": {"code": -32602, "message": "bad params"}}
        changed = sanitize_error_payload(payload)
        assert changed is False
        assert payload["error"]["message"] == "bad params"

    def test_leaves_a_success_payload_untouched(self):
        payload = {"result": {"id": "t1"}}
        assert sanitize_error_payload(payload) is False

    def test_never_raises_on_an_unexpected_shape(self):
        assert sanitize_error_payload(["not", "a", "dict"]) is False
        assert sanitize_error_payload(None) is False
        assert sanitize_error_payload({"error": "not-a-dict"}) is False


class TestSanitizeJsonResponse:
    def test_content_length_matches_the_rewritten_body_exactly(self):
        """CRITICAL-2 regression test: the sanitized response's declared
        Content-Length must equal len(response.body) -- the leaking,
        original-length header is the bug this guards against."""
        leaking_message = "x" * 5000  # much longer than the generic replacement
        original = JSONResponse(
            {"jsonrpc": "2.0", "id": 1, "error": {"code": INTERNAL_ERROR_CODE, "message": leaking_message}},
            status_code=200,
        )
        sanitized = sanitize_json_response(original)

        content_length_header = next(v for k, v in sanitized.raw_headers if k == b"content-length")
        assert int(content_length_header) == len(sanitized.body)
        assert leaking_message not in sanitized.body.decode()

    def test_content_length_also_matches_when_the_new_body_is_longer(self):
        original = JSONResponse(
            {"jsonrpc": "2.0", "id": 1, "error": {"code": INTERNAL_ERROR_CODE, "message": "x"}},
            status_code=200,
        )
        sanitized = sanitize_json_response(original)
        content_length_header = next(v for k, v in sanitized.raw_headers if k == b"content-length")
        assert int(content_length_header) == len(sanitized.body)

    def test_a_non_error_response_passes_through_unchanged(self):
        original = JSONResponse({"result": {"id": "t1"}}, status_code=200)
        sanitized = sanitize_json_response(original)
        assert sanitized is original

    def test_a_non_jsonresponse_passes_through_unchanged(self):
        original = Response(content=b"raw bytes", media_type="application/octet-stream")
        sanitized = sanitize_json_response(original)
        assert sanitized is original

    def test_preserves_the_original_background_task(self):
        calls = []

        async def _bg() -> None:
            calls.append(1)

        from starlette.background import BackgroundTask

        original = JSONResponse(
            {"error": {"code": INTERNAL_ERROR_CODE, "message": "leak"}}, status_code=200
        )
        original.background = BackgroundTask(_bg)
        sanitized = sanitize_json_response(original)
        assert sanitized.background is original.background


class TestSanitizeSseItem:
    def test_rewrites_an_error_event_in_place(self):
        item = {
            "event": "message",
            "data": json.dumps({"error": {"code": INTERNAL_ERROR_CODE, "message": "db timeout: host=..."}}),
        }
        sanitized = sanitize_sse_item(item)
        new_payload = json.loads(sanitized["data"])
        assert new_payload["error"]["message"] == RETRYABLE_ERROR_MESSAGE

    def test_a_success_event_is_returned_unchanged(self):
        item = {"event": "message", "data": json.dumps({"result": {"id": "t1"}})}
        assert sanitize_sse_item(item) is item

    def test_a_malformed_data_field_is_returned_unchanged(self):
        item = {"event": "message", "data": "not-json"}
        assert sanitize_sse_item(item) is item


class TestDeriveOutcome:
    def test_ok_for_a_result_payload(self):
        resp = JSONResponse({"result": {}}, status_code=200)
        assert derive_outcome(resp) == "ok"

    def test_jsonrpc_error_code_for_an_error_payload(self):
        resp = JSONResponse({"error": {"code": -32602}}, status_code=200)
        assert derive_outcome(resp) == "jsonrpc_error_-32602"

    def test_http_status_for_a_non_jsonresponse(self):
        resp = Response(status_code=413)
        assert derive_outcome(resp) == "http_413"


class TestExtractTaskIdFromSseItem:
    def test_extracts_from_a_task_result(self):
        item = {"data": json.dumps({"result": {"task": {"id": "t42"}}})}
        assert extract_task_id_from_sse_item(item) == "t42"

    def test_extracts_from_a_status_update(self):
        item = {"data": json.dumps({"result": {"statusUpdate": {"taskId": "t43"}}})}
        assert extract_task_id_from_sse_item(item) == "t43"

    def test_returns_none_for_an_unrelated_shape(self):
        assert extract_task_id_from_sse_item({"data": json.dumps({"result": {}})}) is None
        assert extract_task_id_from_sse_item({"data": "not-json"}) is None
        assert extract_task_id_from_sse_item({}) is None
