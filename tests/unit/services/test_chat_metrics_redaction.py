"""build_metrics_payload: a Chat turn never stores provider/tool text; other channels are unchanged."""
from datetime import datetime
from types import SimpleNamespace

import pytest

from services.agent_metrics_recorder import build_metrics_payload
from utils.turn_failure_log import chat_failure_summary

MARK = "TOPSECRET-ECHOED-PROMPT"


def _build(caller, code, message, tool_calls=()):
    collector = SimpleNamespace(tool_calls=list(tool_calls), llm_calls=0)
    return build_metrics_payload(
        event_id="00000000-0000-0000-0000-000000000001",
        fresh_agent=SimpleNamespace(agent_id=1, app_id=1, output_parser_id=None, ai_service=None, service_id=None),
        user_context={"caller_type_override": caller} if caller else {"user_id": 1},
        started_at=datetime.utcnow(), finished_at=datetime.utcnow(), duration_ms=1, status="ERROR",
        error_code=code, error_message=message, result=None, image_files=[], message="m", collector=collector,
    )


TOOL = {"tool_name": "t", "tool_type": "MCP", "status": "ERROR", "error_message": f"boom {MARK}",
        "started_at": datetime.utcnow().isoformat()}


class TestChatRedaction:
    def test_unmarked_text_is_withheld(self):
        payload = _build("INTERNAL_CHAT", "RuntimeError", f"provider echoes {MARK}", [TOOL])
        assert MARK not in str(payload)
        assert payload["event"]["error_message"] == "RuntimeError (details withheld)"
        assert payload["tool_calls"][0]["error_message"] == "Tool error (details withheld)"

    def test_the_class_chain_summary_is_kept(self):
        summary = chat_failure_summary(RuntimeError("x"))
        assert _build("INTERNAL_CHAT", "RuntimeError", summary)["event"]["error_message"] == summary

    @pytest.mark.parametrize("code", ["TIMEOUT", "Cancelled", "SERVICE_RETIRED", "approval_not_supported_in_channel"])
    def test_our_own_texts_are_kept(self, code):
        assert _build("INTERNAL_CHAT", code, "our text")["event"]["error_message"] == "our text"


class TestOtherChannelsUnchanged:
    @pytest.mark.parametrize("caller", [None, "PUBLIC_API", "SCHEDULED_TASK", "A2A"])
    def test_text_and_tool_errors_are_stored_as_before(self, caller):
        payload = _build(caller, "RuntimeError", f"provider echoes {MARK}", [TOOL])
        assert payload["event"]["error_message"] == f"provider echoes {MARK}"
        assert payload["tool_calls"][0]["error_message"] == f"boom {MARK}"
