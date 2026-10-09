"""Integration: evaluate endpoints (internal playground + public v1) and public agent management."""
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from tests.integration.system_one_helpers import (  # noqa: F401
    platform_editor, platform_viewer_headers, viewer_headers,
)
from tools.system_one_client import SystemOneError

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("platform_editor")]

QUESTIONS = [
    {"key": "urgent", "type": "noul", "instructions": "Is it urgent?", "threshold": 0.8},
    {"key": "area", "type": "choice", "instructions": "Which area?", "min_probability": 0.6,
     "criteria": [{"key": "billing"}, {"key": "tech"}]},
    {"key": "anger", "type": "score", "instructions": "How angry?", "criteria": ["Calm", "Angry"]},
]
RAW = {"model": "nimble-latest", "usage": {"input_tokens": 50, "output_tokens": 4},
       "answers": {"urgent": {"type": "noul", "noul": 0.91},
                   "area": {"type": "choice", "choice": "billing", "confidence": 0.39,
                            "probabilities": {"billing": 0.73, "tech": 0.27}},
                   "anger": {"type": "score", "score": 0.4, "confidence": 0.2, "legend": {"0": "Calm", "1": "Angry"},
                             "probabilities": {"0": 0.7, "1": 0.3}}}}


@pytest.fixture
def agent(db, fake_app):
    from models.system_one_agent import SystemOneAgent
    from models.system_one_service import SystemOneService

    svc = SystemOneService(name="Nimble", endpoint="http://so.test", description="nimble-latest",
                           app_id=fake_app.app_id, create_date=datetime.now())
    db.add(svc)
    db.flush()
    a = SystemOneAgent(name="Triage", app_id=fake_app.app_id, system_one_service_id=svc.service_id,
                       questions=QUESTIONS, max_state_chars=6000, is_tool=True, create_date=datetime.now())
    db.add(a)
    db.flush()
    return a


@pytest.fixture
def server():
    with patch("services.system_one_evaluator.system_one_client.evaluate", AsyncMock(return_value=RAW)) as ev, \
         patch("services.system_one_evaluator.record_agent_execution") as rec:
        yield ev, rec


def internal(app, agent_id):
    return f"/internal/apps/{app.app_id}/system-one/{agent_id}/evaluate"


def public(app, agent_id):
    return f"/public/v1/app/{app.app_id}/system-one/{agent_id}/evaluate"


# ------------------------------------------------------------------ internal

class TestInternalEvaluate:
    def test_returns_typed_answers(self, client, fake_app, agent, owner_headers, server):
        r = client.post(internal(fake_app, agent.agent_id), data={"text": "call me back"}, headers=owner_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert list(body["answers"]) == ["urgent", "area", "anger"]
        assert body["answers"]["urgent"] == {"type": "noul", "decision": True, "probability": 0.91, "threshold": 0.8}
        assert body["answers"]["area"]["decision"] == "billing" and body["answers"]["area"]["confidence"] == 0.39
        assert body["answers"]["anger"]["decision"] == "Calm" and body["answers"]["anger"]["expected_score"] == 0.4
        assert body["state_reduction"] == "none" and body["model"] == "nimble-latest"
        assert body["usage"] == {"input_tokens": 50, "output_tokens": 4}

    def test_app_viewer_can_evaluate(self, client, fake_app, agent, viewer_headers, server):
        r = client.post(internal(fake_app, agent.agent_id), data={"text": "hello"}, headers=viewer_headers)
        assert r.status_code == 200

    def test_platform_viewers_stay_read_only_like_for_every_other_post(self, client, fake_app, agent,
                                                                       platform_viewer_headers, server):
        """The platform guard (require_editor_for_writes) rejects any POST of a platform viewer; evaluate is not exempted."""
        r = client.post(internal(fake_app, agent.agent_id), data={"text": "hello"}, headers=platform_viewer_headers)
        assert r.status_code == 403
        server[0].assert_not_awaited()

    def test_requires_authentication(self, client, fake_app, agent, server):
        assert client.post(internal(fake_app, agent.agent_id), data={"text": "x"}).status_code in (401, 403)

    def test_attachments_are_read_and_added(self, client, fake_app, agent, owner_headers, server):
        r = client.post(internal(fake_app, agent.agent_id), data={"text": "see file"}, headers=owner_headers,
                        files=[("files", ("notes.txt", b"FILE BODY", "text/plain"))])
        assert r.status_code == 200, r.text
        state = server[0].await_args.args[1]
        assert "see file" in state and "FILE BODY" in state

    def test_caller_context_is_the_playground_user(self, client, fake_app, agent, owner_headers, server, fake_user):
        client.post(internal(fake_app, agent.agent_id), data={"text": "x"}, headers=owner_headers)
        ctx = server[1].call_args.kwargs["user_context"]
        assert ctx["user_id"] == fake_user.user_id and "api_key_id" not in ctx and ctx["app_id"] == fake_app.app_id

    @pytest.mark.parametrize("kwargs,status", [
        ({"data": {"text": "  "}}, 400),
        ({"data": {}}, 400),
        ({"data": {"text": "x"}, "files": [("files", ("p.png", b"\x89PNG", "image/png"))]}, 400),
        ({"data": {"text": "x"}, "files": [("files", ("b.bin", b"\xff\xfe\x00", "application/octet-stream"))]}, 400),
    ])
    def test_bad_input_is_400(self, client, fake_app, agent, owner_headers, server, kwargs, status):
        r = client.post(internal(fake_app, agent.agent_id), headers=owner_headers, **kwargs)
        assert r.status_code == status, r.text
        server[0].assert_not_awaited()

    def test_unknown_agent_is_404(self, client, fake_app, owner_headers, server):
        assert client.post(internal(fake_app, 987654), data={"text": "x"}, headers=owner_headers).status_code == 404

    def test_a_normal_agent_is_404(self, client, fake_app, fake_agent, owner_headers, server):
        assert client.post(internal(fake_app, fake_agent.agent_id), data={"text": "x"}, headers=owner_headers).status_code == 404

    def test_agent_of_another_app_is_404(self, client, db, fake_app, fake_user, agent, owner_headers, server):
        from models.app import App

        other = App(name="Other", slug="other-eval", owner_id=fake_user.user_id)
        db.add(other)
        db.flush()
        assert client.post(internal(other, agent.agent_id), data={"text": "x"}, headers=owner_headers).status_code in (403, 404)
        server[0].assert_not_awaited()

    @pytest.mark.parametrize("kind,status", [("unavailable", 503), ("timeout", 504), ("overloaded", 503)])
    def test_server_failures_are_http_errors_with_a_message(self, client, fake_app, agent, owner_headers, server, kind, status):
        server[0].side_effect = SystemOneError(kind, f"server says {kind}")
        r = client.post(internal(fake_app, agent.agent_id), data={"text": "x"}, headers=owner_headers)
        assert r.status_code == status and f"server says {kind}" in r.json()["detail"]


# -------------------------------------------------------------------- public

class TestPublicEvaluate:
    def test_evaluates_with_an_api_key(self, client, fake_app, agent, fake_api_key, server):
        r = client.post(public(fake_app, agent.agent_id), data={"text": "call me"},
                        headers={"X-API-KEY": fake_api_key.key})
        assert r.status_code == 200, r.text
        assert r.json()["answers"]["urgent"]["decision"] is True
        ctx = server[1].call_args.kwargs["user_context"]
        assert ctx["api_key_id"] == fake_api_key.key_id and ctx["app_id"] == fake_app.app_id

    def test_without_or_with_a_wrong_key_is_401(self, client, fake_app, agent, server):
        assert client.post(public(fake_app, agent.agent_id), data={"text": "x"}).status_code == 401
        assert client.post(public(fake_app, agent.agent_id), data={"text": "x"},
                           headers={"X-API-KEY": "nope"}).status_code == 401

    def test_agent_of_another_app_is_404(self, client, db, fake_app, fake_user, agent, fake_api_key, server):
        from models.api_key import APIKey
        from models.app import App

        other = App(name="Other", slug="other-pub-eval", owner_id=fake_user.user_id)
        db.add(other)
        db.flush()
        key = APIKey(key="other-app-key-for-tests-only", name="k", app_id=other.app_id, user_id=fake_user.user_id,
                     is_active=True, created_at=datetime.now())  # pragma: allowlist secret
        db.add(key)
        db.flush()
        r = client.post(public(other, agent.agent_id), data={"text": "x"}, headers={"X-API-KEY": key.key})
        assert r.status_code == 404
        server[0].assert_not_awaited()

    def test_the_documented_schema_is_typed(self, client):
        spec = client.get("/openapi-public.json")
        assert spec.status_code == 200
        doc = spec.json()
        schemas = doc["components"]["schemas"]
        assert {"NoulAnswer", "ChoiceAnswer", "ScoreAnswer", "SystemOneResult"} <= set(schemas)
        answer = schemas["SystemOneResult"]["properties"]["answers"]["additionalProperties"]
        assert answer["discriminator"]["propertyName"] == "type"        # a typed union, not a generic dict
        path = "/public/v1/app/{app_id}/system-one/{agent_id}/evaluate"
        assert path in doc["paths"] and "post" in doc["paths"][path]
