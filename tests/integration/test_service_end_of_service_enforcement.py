"""Integration tests for end-of-service enforcement on chat entry points (step_012).

AC-6, AC-12, AC-21. Real test DB; provider SDK builders are patched and asserted NOT called
for retired services (see the sibling ``test_service_end_of_service_enforcement_*`` modules
for AC-7..AC-11 and the sandbox criteria).
"""

import logging

import pytest

from tests.integration._eos_enforcement_helpers import (  # noqa: F401  (fixtures)
    LLM_ANSWER,
    ai_service,
    api_key_headers,
    future,
    guard_warnings,
    lifecycle_caplog,
    llm_builders,
    make_agent,
    past,
    sse_events,
)
from tests.integration.routers.internal._eos_helpers import ai_payload, iso

pytestmark = pytest.mark.integration


def _internal(app, agent, suffix="chat"):
    return f"/internal/apps/{app.app_id}/agents/{agent.agent_id}/{suffix}"


def _public(app, agent, suffix="call"):
    return f"/public/v1/app/{app.app_id}/chat/{agent.agent_id}/{suffix}"


def _expected_message(svc):
    return f"Service {svc.name} was retired on {svc.end_of_service_at:%Y-%m-%d}."


class TestInternalChat:
    """AC-6 (internal API)."""

    def test_chat_with_retired_llm_returns_409_with_message(self, client, db, fake_app, owner_headers, llm_builders):
        svc = ai_service(db, fake_app, name="gpt-retired", eos=past(3), notice="Use gpt-new.")
        agent = make_agent(db, fake_app, svc)

        resp = client.post(_internal(fake_app, agent), data={"message": "hi"}, headers=owner_headers)

        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"] == f"{_expected_message(svc)} Use gpt-new."
        assert resp.json()["error_code"] == "SERVICE_RETIRED"
        assert not llm_builders.called

    def test_stream_with_retired_llm_emits_sse_error_event(self, client, db, fake_app, owner_headers, llm_builders):
        svc = ai_service(db, fake_app, name="gpt-retired-stream", eos=past(2))
        agent = make_agent(db, fake_app, svc)

        resp = client.post(_internal(fake_app, agent, "chat/stream"), data={"message": "hi"}, headers=owner_headers)

        assert resp.status_code == 200, resp.text
        errors = [e for e in sse_events(resp.text) if e.get("type") == "error"]
        assert len(errors) == 1, resp.text
        payload = errors[0].get("data", errors[0])
        message = payload["message"] if isinstance(payload, dict) else payload
        assert message == _expected_message(svc)
        assert not llm_builders.called

    def test_active_and_deprecated_llm_still_chat(self, client, db, fake_app, owner_headers, llm_builders):
        svc = ai_service(db, fake_app, eos=future(2), notice="soon")  # deprecated, not retired
        agent = make_agent(db, fake_app, svc)

        resp = client.post(_internal(fake_app, agent), data={"message": "hi"}, headers=owner_headers)

        assert resp.status_code == 200, resp.text
        assert resp.json()["response"] == LLM_ANSWER
        assert llm_builders.openai.call_count == 1


class TestPublicChat:
    """AC-6 (public API)."""

    def test_call_with_retired_llm_returns_409_with_message(
        self, client, db, fake_app, fake_user, llm_builders
    ):
        svc = ai_service(db, fake_app, name="gpt-retired-public", eos=past(5), notice="Moved.")
        agent = make_agent(db, fake_app, svc)
        headers = api_key_headers(db, fake_app, fake_user)

        resp = client.post(_public(fake_app, agent), data={"message": "hi"}, headers=headers)

        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"] == f"{_expected_message(svc)} Moved."
        assert not llm_builders.called

    def test_call_stream_with_retired_llm_emits_sse_error_event(
        self, client, db, fake_app, fake_user, llm_builders
    ):
        svc = ai_service(db, fake_app, name="gpt-retired-public-stream", eos=past(5))
        agent = make_agent(db, fake_app, svc)
        headers = api_key_headers(db, fake_app, fake_user)

        resp = client.post(_public(fake_app, agent, "call/stream"), data={"message": "hi"}, headers=headers)

        assert resp.status_code == 200, resp.text
        errors = [e for e in sse_events(resp.text) if e.get("type") == "error"]
        assert len(errors) == 1, resp.text
        payload = errors[0].get("data", errors[0])
        message = payload["message"] if isinstance(payload, dict) else payload
        assert message == _expected_message(svc)
        assert not llm_builders.called


class TestRetirementIsReversible:
    """AC-12: moving the date into the future (or clearing it) restores the service, nothing else changes."""

    @pytest.mark.parametrize("new_date", [future(60), None], ids=["future-date", "cleared"])
    def test_chat_works_again_after_date_moves(
        self, client, db, fake_app, owner_headers, llm_builders, new_date
    ):
        svc = ai_service(db, fake_app, name="gpt-comes-back", eos=past(1))
        agent = make_agent(db, fake_app, svc)
        url = _internal(fake_app, agent)

        blocked = client.post(url, data={"message": "hi"}, headers=owner_headers)
        assert blocked.status_code == 409, blocked.text
        assert not llm_builders.called

        update = client.post(
            f"/internal/apps/{fake_app.app_id}/ai-services/{svc.service_id}",
            json=ai_payload(name="gpt-comes-back", end_of_service_at=iso(new_date) if new_date else None),
            headers=owner_headers,
        )
        assert update.status_code == 200, update.text
        db.refresh(agent)
        assert agent.service_id == svc.service_id  # the agent itself was not touched

        ok = client.post(url, data={"message": "hi again"}, headers=owner_headers)
        assert ok.status_code == 200, ok.text
        assert ok.json()["response"] == LLM_ANSWER
        assert llm_builders.openai.call_count == 1


class TestBlockedCallLogging:
    """AC-21: exactly one WARNING from the guard per blocked call, with id, kind, app id and channel."""

    def test_internal_chat_logs_one_warning(self, client, db, fake_app, owner_headers, llm_builders, lifecycle_caplog):
        svc = ai_service(db, fake_app, name="gpt-logged", eos=past(1))
        agent = make_agent(db, fake_app, svc)

        resp = client.post(_internal(fake_app, agent), data={"message": "hi"}, headers=owner_headers)

        assert resp.status_code == 409
        warnings = guard_warnings(lifecycle_caplog)
        assert len(warnings) == 1, [w.getMessage() for w in warnings]
        text = warnings[0].getMessage()
        assert f"service_id={svc.service_id}" in text
        assert "kind=ai" in text
        assert f"app_id={fake_app.app_id}" in text
        assert "channel=internal_sync" in text
        assert f"resource_id={agent.agent_id}" in text
        # the 409 handler / router catch must not log the same block again
        assert [r for r in lifecycle_caplog.records if r.levelno >= logging.ERROR] == []

    def test_public_chat_logs_one_warning_with_public_channel(
        self, client, db, fake_app, fake_user, llm_builders, lifecycle_caplog
    ):
        svc = ai_service(db, fake_app, name="gpt-logged-public", eos=past(1))
        agent = make_agent(db, fake_app, svc)

        resp = client.post(_public(fake_app, agent), data={"message": "hi"},
                           headers=api_key_headers(db, fake_app, fake_user))

        assert resp.status_code == 409
        warnings = guard_warnings(lifecycle_caplog)
        assert len(warnings) == 1, [w.getMessage() for w in warnings]
        text = warnings[0].getMessage()
        assert f"service_id={svc.service_id}" in text and "kind=ai" in text
        assert f"app_id={fake_app.app_id}" in text
        assert "channel=public_api" in text
        assert f"resource_id={agent.agent_id}" in text
