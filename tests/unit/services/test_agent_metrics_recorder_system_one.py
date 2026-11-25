"""The metrics recorder carries System One answers and event overrides (payload level)."""
from datetime import datetime
from types import SimpleNamespace

from services.agent_metrics_recorder import build_metrics_payload

AGENT = SimpleNamespace(app_id=9, agent_id=3, service_id=None, ai_service=None, output_parser_id=None)


def build(**kw):
    base = dict(event_id="11111111-1111-1111-1111-111111111111", fresh_agent=AGENT, user_context={"user_id": 1},
                started_at=datetime(2026, 10, 9, 10, 0, 0), finished_at=datetime(2026, 10, 9, 10, 0, 1),
                duration_ms=1000, status="SUCCESS", error_code=None, error_message=None, result=None,
                image_files=[], message="hello")
    return build_metrics_payload(**{**base, **kw})


def test_overrides_replace_the_derived_event_fields():
    payload = build(event_overrides={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12,
                                     "model_name": "nimble-latest", "provider": "system_one", "llm_calls": 0,
                                     "had_files": True, "file_count": 2, "had_images": False})
    event = payload["event"]
    assert (event["input_tokens"], event["total_tokens"], event["provider"]) == (10, 12, "system_one")
    assert (event["model_name"], event["llm_calls"], event["file_count"], event["had_images"]) == ("nimble-latest", 0, 2, False)
    assert event["prompt_chars"] == 5 and event["agent_id"] == 3          # untouched fields stay derived


def test_answers_travel_in_the_payload_only_when_given():
    assert "system_one_answers" not in build()
    rows = [{"question_key": "u", "question_type": "noul", "decision": "true", "probability": 0.9,
             "expected_score": None, "confidence": None, "probabilities": None, "state_reduction": "none"}]
    assert build(system_one_answers=rows)["system_one_answers"] == rows


def test_without_the_new_arguments_the_payload_is_unchanged():
    payload = build()
    assert set(payload) == {"event", "tool_calls"} and payload["event"]["provider"] is None
