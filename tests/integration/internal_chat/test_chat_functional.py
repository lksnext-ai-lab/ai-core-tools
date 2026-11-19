"""Functional integration tests of the flexible per-App Chat (app-flexible-chat step_009).

The fakes (LLM, retriever, MCP client, metrics write), the ``world`` fixture and the HTTP helpers live in
``_chat_support.py``; the ``fakes`` and ``world`` fixtures are exposed by the package ``conftest.py``.
"""
import logging
import threading
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from models.agent import Agent
from models.app import App
from models.conversation import Conversation
from models.domain import Domain
from models.internal_chat import ConversationTurn
from models.mcp_config import MCPConfig
from models.repository import Repository
from models.sharepoint_source import SharePointSource
from models.silo import Silo
from models.skill import Skill
from models.usage_record import UsageRecord
from services.conversation_service import ConversationService
from tests.factories import (
    AIServiceFactory,
    AppFactory,
    SkillFactory,
    SystemSkillFactory,
    UserFactory,
    configure_factories,
)
from tests.integration.internal_chat._chat_support import (  # noqa: F401
    NOT_FOUND,
    base,
    detail,
    events_in,
    internal_conversations,
    message_total,
    ok_turn,
    parse_sse,
    selection,
    send,
    sse_turn,
    turns_in,
)
from tests.integration.routers.internal._eos_helpers import future, headers_for, past


# ------------------------------------------------------------------ AC-1 / AC-3: conversations


class TestConversations:
    def test_a_viewer_can_chat_and_gets_the_answer(self, client, world, fakes):
        body = ok_turn(client, world, "hello there", selection(world["ai_a"]), who="viewer")
        assert body["response"] == f"hello from {world['ai_a']}"
        assert body["turn"]["ai_service_id"] == world["ai_a"] and body["turn"]["turn_index"] == 1

    def test_crud_persists(self, client, world, fakes):
        url = base(world["app_id"])
        created = client.post(
            f"{url}/conversations", headers=world["alice"], json={"title": "First", "selection": selection(world["ai_a"])}
        )
        assert created.status_code == 200, created.text
        cid = created.json()["conversation_id"]

        renamed = client.patch(f"{url}/conversations/{cid}", headers=world["alice"], json={"title": "Renamed"})
        assert renamed.status_code == 200 and renamed.json()["title"] == "Renamed"
        listed = client.get(f"{url}/conversations", headers=world["alice"]).json()
        assert [(c["conversation_id"], c["title"]) for c in listed["conversations"]] == [(cid, "Renamed")]
        assert detail(client, world, cid)["title"] == "Renamed"

        assert client.delete(f"{url}/conversations/{cid}", headers=world["alice"]).status_code == 204
        assert client.get(f"{url}/conversations", headers=world["alice"]).json() == {"conversations": [], "total": 0}
        assert client.get(f"{url}/conversations/{cid}", headers=world["alice"]).json() == NOT_FOUND

    def test_a_conversation_with_turns_can_be_deleted(self, client, db, world, fakes):
        cid = ok_turn(client, world, "hi", selection(world["ai_a"]))["conversation_id"]
        assert client.delete(f"{base(world['app_id'])}/conversations/{cid}", headers=world["alice"]).status_code == 204
        assert db.query(ConversationTurn).filter_by(conversation_id=cid).count() == 0

    def test_list_excludes_playground_conversations_of_a_normal_agent(self, client, db, world, fakes):
        configure_factories(db)
        agent = Agent(name="normal", description="d", system_prompt="s", app_id=world["app_id"],
                      service_id=world["ai_a"], has_memory=False, temperature=0.5)
        db.add(agent)
        db.flush()
        playground = ConversationService.create_conversation(db, agent.agent_id, {"user_id": world["alice_id"]})
        playground_id = playground.conversation_id
        chat_id = ok_turn(client, world, "hi", selection(world["ai_a"]))["conversation_id"]

        listed = client.get(f"{base(world['app_id'])}/conversations", headers=world["alice"]).json()
        assert [c["conversation_id"] for c in listed["conversations"]] == [chat_id]
        assert playground_id not in {c["conversation_id"] for c in listed["conversations"]}
        # and a playground conversation is not reachable through the Chat
        response = client.get(f"{base(world['app_id'])}/conversations/{playground_id}", headers=world["alice"])
        assert response.status_code == 404 and response.json() == NOT_FOUND


# ------------------------------------------------------------------ turns without a conversation id


class TestFirstTurn:
    @pytest.mark.parametrize("path", ["/messages", "/stream"])
    def test_a_turn_without_conversation_id_creates_it(self, client, db, world, fakes, path):
        assert internal_conversations(db, world["app_id"]) == 0
        response = send(client, world, "first", selection(world["ai_a"]), path=path)
        assert response.status_code == 200, response.text
        if path == "/messages":
            cid = response.json()["conversation_id"]
        else:
            cid = parse_sse(response.text)[0]["data"]["conversation_id"]
        listed = client.get(f"{base(world['app_id'])}/conversations", headers=world["alice"]).json()
        assert [c["conversation_id"] for c in listed["conversations"]] == [cid]
        assert [m["role"] for m in detail(client, world, cid)["messages"]] == ["user", "agent"]

    @pytest.mark.parametrize("path", [
        "/messages",
        "/stream",
    ])
    def test_a_first_turn_whose_model_fails_leaves_no_conversation(self, client, db, world, fakes, path):
        fakes.fail_services.add(world["ai_a"])
        try:
            response = send(client, world, "boom", selection(world["ai_a"]), path=path)
            outcome = response.status_code
        except Exception:  # the unhandled failure surfaces through the test client
            outcome = "raised"
        assert outcome != 200 or any(e["type"] == "error" for e in parse_sse(response.text))
        assert fakes.calls_of(world["ai_a"]), "the fake model must have been reached"
        assert internal_conversations(db, world["app_id"]) == 0
        assert turns_in(db, world["app_id"]) == 0

    def test_a_failed_turn_keeps_an_existing_conversation(self, client, db, world, fakes):
        cid = ok_turn(client, world, "fine", selection(world["ai_a"]))["conversation_id"]
        fakes.fail_services.add(world["ai_a"])
        try:
            send(client, world, "boom", selection(world["ai_a"]), conversation_id=cid)
        except Exception:
            pass
        assert internal_conversations(db, world["app_id"]) == 1
        assert [m["role"] for m in detail(client, world, cid)["messages"]][:2] == ["user", "agent"]


# ------------------------------------------------------------------ AC-4: model per turn


class TestModelPerTurn:
    def test_each_turn_uses_its_own_model_and_the_second_sees_the_first(self, client, world, fakes):
        a, b = world["ai_a"], world["ai_b"]
        cid = ok_turn(client, world, "question one", selection(a))["conversation_id"]
        second = ok_turn(client, world, "question two", selection(b), conversation_id=cid)
        assert second["response"] == f"hello from {b}"

        assert [m for m in fakes.calls_of(a)[0] if m[0] == "human"] == [("human", "question one")]
        assert len(fakes.calls_of(a)) == 1, "model A must not see turn 2"
        assert len(fakes.calls_of(b)) == 1
        seen_by_b = fakes.calls_of(b)[0]
        assert ("human", "question one") in seen_by_b
        assert ("ai", f"hello from {a}") in seen_by_b
        assert seen_by_b[-1] == ("human", "question two")

        messages = detail(client, world, cid)["messages"]
        assert [m["turn"]["ai_service_id"] for m in messages if m["role"] == "agent"] == [a, b]

    def test_the_same_works_over_sse(self, client, world, fakes):
        a, b = world["ai_a"], world["ai_b"]
        first = sse_turn(client, world, "q1", selection(a))
        cid = first[0]["data"]["conversation_id"]
        sse_turn(client, world, "q2", selection(b), conversation_id=cid)
        assert len(fakes.calls_of(a)) == 1 and len(fakes.calls_of(b)) == 1
        assert ("human", "q1") in fakes.calls_of(b)[0]


# ------------------------------------------------------------------ AC-5: retired services


class TestRetiredService:
    @pytest.fixture
    def retired(self, db, world):
        configure_factories(db)
        service = AIServiceFactory(app=db.get(App, world["app_id"]), name="old-model", end_of_service_at=past(2))
        db.commit()
        return service.service_id

    def test_a_retired_service_is_not_offered(self, client, world, retired):
        options = client.get(f"{base(world['app_id'])}/options", headers=world["alice"]).json()
        ids = [s["service_id"] for s in options["ai_services"]]
        assert retired not in ids and world["ai_a"] in ids

    @pytest.mark.parametrize("path", ["/messages", "/stream"])
    def test_sending_it_is_409_and_writes_nothing(self, client, db, world, fakes, retired, path):
        cid = ok_turn(client, world, "before", selection(world["ai_a"]))["conversation_id"]
        turns = turns_in(db, world["app_id"])
        payloads_before = len(fakes.wait_payloads(1))  # the accepted turn's metrics
        message_count = db.query(Conversation).filter_by(conversation_id=cid).one().message_count
        calls = len(fakes.calls)

        response = send(client, world, "after", selection(retired), conversation_id=cid, path=path)
        assert response.status_code == 409
        assert response.json()["error_code"] == "SERVICE_RETIRED"

        assert len(fakes.calls) == calls
        assert turns_in(db, world["app_id"]) == turns
        db.expire_all()
        assert db.query(Conversation).filter_by(conversation_id=cid).one().message_count == message_count
        assert [m["content"] for m in detail(client, world, cid)["messages"]][0] == "before"
        assert len(detail(client, world, cid)["messages"]) == 2
        time.sleep(0.5)  # metrics are written asynchronously: give a (wrongly) produced payload time to arrive
        assert len(fakes.payloads) == payloads_before  # the rejected turn produced no metrics payload

    def test_a_first_turn_with_a_retired_service_creates_no_conversation(self, client, db, world, fakes, retired):
        assert send(client, world, "x", selection(retired)).status_code == 409
        assert internal_conversations(db, world["app_id"]) == 0


# ------------------------------------------------------------------ AC-6: knowledge source


class TestKnowledgeSource:
    @pytest.fixture
    def silos(self, db, world):
        app_id, emb = world["app_id"], world["emb"]
        made = {}
        for key in ("repository", "domain", "sharepoint", "silo"):
            silo = Silo(name=f"silo-{key}", app_id=app_id, embedding_service_id=emb)
            db.add(silo)
            db.flush()
            made[key] = silo.silo_id
        db.add_all([
            Repository(name="my-repo", app_id=app_id, silo_id=made["repository"], type="files", status="active"),
            Domain(name="my-domain", base_url="https://example.com", content_tag="body", app_id=app_id,
                   silo_id=made["domain"]),
            SharePointSource(
                app_id=app_id, silo_id=made["sharepoint"], name="my-sharepoint", tenant_id="t", client_id="c",
                client_secret="s", site_id="site", drive_id="drive",  # pragma: allowlist secret
            ),
        ])
        db.commit()
        return made

    def test_options_report_the_source_type_of_each_silo(self, client, world, silos):
        options = client.get(f"{base(world['app_id'])}/options", headers=world["alice"]).json()
        by_id = {s["silo_id"]: s for s in options["silos"]}
        assert {(by_id[silos[k]]["source_type"], by_id[silos[k]]["source_name"]) for k in silos} == {
            ("repository", "my-repo"), ("domain", "my-domain"), ("sharepoint", "my-sharepoint"), ("silo", None),
        }
        for key in silos:
            assert by_id[silos[key]]["source_type"] == key

    def test_the_selected_silo_gets_its_retriever_and_none_gets_none(self, client, world, fakes, silos):
        a = world["ai_a"]
        cid = ok_turn(client, world, "with silo", selection(a, silo=silos["domain"]))["conversation_id"]
        assert f"retriever_silo_{silos['domain']}" in fakes.tools_of(a)
        ok_turn(client, world, "without silo", selection(a), conversation_id=cid)
        assert not [t for t in fakes.tools_of(a) if t.startswith("retriever_silo_")]
        ok_turn(client, world, "other silo", selection(a, silo=silos["repository"]), conversation_id=cid)
        tools = fakes.tools_of(a)
        assert f"retriever_silo_{silos['repository']}" in tools and f"retriever_silo_{silos['domain']}" not in tools

    def test_the_turn_snapshot_names_the_silo(self, client, world, fakes, silos):
        body = ok_turn(client, world, "q", selection(world["ai_a"], silo=silos["sharepoint"]))
        assert (body["turn"]["silo_id"], body["turn"]["silo_name"]) == (silos["sharepoint"], "silo-sharepoint")


# ------------------------------------------------------------------ AC-7: skills


class TestSkills:
    @pytest.fixture
    def skills(self, db, world):
        configure_factories(db)
        app = db.get(App, world["app_id"])
        own = SkillFactory(app=app, name="skill-alpha", description="ALPHA-DESC")
        system = SystemSkillFactory(name="sys-skill-on", description="SYS-ON-DESC")
        disabled = SystemSkillFactory(name="sys-skill-off", is_enabled=False)
        db.commit()
        return {"own": own.skill_id, "system": system.skill_id, "disabled": disabled.skill_id}

    def test_a_skill_is_in_the_prompt_of_its_turn_only(self, client, world, fakes, skills):
        a = world["ai_a"]
        cid = ok_turn(client, world, "t1", selection(a, skills=[skills["own"]]))["conversation_id"]
        ok_turn(client, world, "t2", selection(a), conversation_id=cid)
        assert "skill-alpha" in fakes.system_prompt(a, 0)
        assert "skill-alpha" not in fakes.system_prompt(a, 1)
        assert "load_skill" in fakes.tools_of(a, 0) and "load_skill" not in fakes.tools_of(a, 1)

    def test_an_enabled_system_skill_is_selectable_and_a_disabled_one_is_not(self, client, world, fakes, skills):
        a = world["ai_a"]
        options = client.get(f"{base(world['app_id'])}/options", headers=world["alice"]).json()
        offered = {s["skill_id"] for s in options["skills"]}
        assert skills["system"] in offered and skills["disabled"] not in offered
        body = ok_turn(client, world, "use it", selection(a, skills=[skills["system"]]))
        assert [s["id"] for s in body["turn"]["skills"]] == [skills["system"]]
        assert "sys-skill-on" in fakes.system_prompt(a)

        calls = len(fakes.calls)
        response = send(client, world, "no", selection(a, skills=[skills["disabled"]]))
        assert response.status_code == 404 and response.json() == NOT_FOUND
        assert len(fakes.calls) == calls


# ------------------------------------------------------------------ AC-8: other App's resources


class TestOtherAppResources:
    @pytest.fixture
    def foreign_conversation(self, client, world, fakes):
        response = client.post(
            f"{base(world['other_app_id'])}/conversations", headers=world["bob"],
            json={"selection": selection(world["other_ai"])},
        )
        assert response.status_code == 200, response.text
        return response.json()["conversation_id"]

    def _selections(self, world):
        a = world["ai_a"]
        return {
            "service": selection(world["other_ai"]),
            "silo": selection(a, silo=world["other_silo"]),
            "skill": selection(a, skills=[world["other_skill"]]),
            "mcp": selection(a, mcps=[world["other_mcp"]]),
            "missing service": selection(987654),
        }

    @pytest.mark.parametrize("path", ["/messages", "/stream"])
    def test_every_foreign_id_is_the_same_404_and_nothing_runs_or_is_written(
        self, client, db, world, fakes, foreign_conversation, path
    ):
        own = ok_turn(client, world, "mine", selection(world["ai_a"]))["conversation_id"]
        fakes.wait_payloads(1)
        before = (
            turns_in(db, world["app_id"]), turns_in(db, world["other_app_id"]),
            events_in(db, world["app_id"]), events_in(db, world["other_app_id"]),
            internal_conversations(db, world["app_id"]),
            internal_conversations(db, world["other_app_id"]),
            message_total(db, world["app_id"]), message_total(db, world["other_app_id"]),
            len(fakes.calls), len(fakes.payloads),
        )

        bodies = []
        for name, sel in self._selections(world).items():
            for conversation_id in (None, own):
                response = send(client, world, "x", sel, conversation_id=conversation_id, path=path)
                assert (name, response.status_code) == (name, 404)
                bodies.append(response.json())
        response = send(client, world, "x", selection(world["ai_a"]), conversation_id=foreign_conversation, path=path)
        assert response.status_code == 404
        bodies.append(response.json())
        response = send(client, world, "x", selection(world["ai_a"]), conversation_id=987654, path=path)
        assert response.status_code == 404
        bodies.append(response.json())
        assert all(body == NOT_FOUND for body in bodies)

        db.expire_all()
        after = (
            turns_in(db, world["app_id"]), turns_in(db, world["other_app_id"]),
            events_in(db, world["app_id"]), events_in(db, world["other_app_id"]),
            internal_conversations(db, world["app_id"]),
            internal_conversations(db, world["other_app_id"]),
            message_total(db, world["app_id"]), message_total(db, world["other_app_id"]),
            len(fakes.calls), len(fakes.payloads),
        )
        assert after == before

    def test_foreign_resources_are_not_offered(self, client, world):
        options = client.get(f"{base(world['app_id'])}/options", headers=world["alice"]).json()
        assert world["other_ai"] not in [s["service_id"] for s in options["ai_services"]]
        assert world["other_silo"] not in [s["silo_id"] for s in options["silos"]]
        assert world["other_skill"] not in [s["skill_id"] for s in options["skills"]]
        assert world["other_mcp"] not in [s["config_id"] for s in options["mcp_configs"]]

    def test_conversation_endpoints_answer_the_same_404(self, client, world, foreign_conversation):
        url = f"{base(world['app_id'])}/conversations/{foreign_conversation}"
        responses = [
            client.get(url, headers=world["alice"]),
            client.patch(url, headers=world["alice"], json={"title": "hijack"}),
            client.delete(url, headers=world["alice"]),
            client.post(url + "/reset", headers=world["alice"]),
            client.get(url + "/files", headers=world["alice"]),
        ]
        assert [r.status_code for r in responses] == [404] * 5
        assert all(r.json() == NOT_FOUND for r in responses)
        # it is untouched
        survived = client.get(
            f"{base(world['other_app_id'])}/conversations/{foreign_conversation}", headers=world["bob"]
        )
        assert survived.status_code == 200 and survived.json()["title"] in (None, "")

    def test_a_foreign_selection_cannot_become_a_default(self, client, world):
        for sel in self._selections(world).values():
            response = client.put(f"{base(world['app_id'])}/defaults", headers=world["alice"], json=sel)
            assert response.status_code == 404 and response.json() == NOT_FOUND


# ------------------------------------------------------------------ AC-9: turn snapshot


class TestTurnSnapshot:
    def test_every_assistant_message_carries_its_model_and_survives_deletion(self, client, db, world, fakes):
        a, b = world["ai_a"], world["ai_b"]
        cid = ok_turn(client, world, "one", selection(a))["conversation_id"]
        ok_turn(client, world, "two", selection(b), conversation_id=cid)

        messages = detail(client, world, cid)["messages"]
        agents = [m for m in messages if m["role"] == "agent"]
        assert [m["turn"]["ai_service_name"] for m in agents] == ["model-a", "model-b"]
        assert [m["turn"]["ai_service_deleted"] for m in agents] == [False, False]
        assert all(m["turn"] is None for m in messages if m["role"] != "agent")

        from models.ai_service import AIService

        db.delete(db.get(AIService, a))
        db.commit()
        agents = [m for m in detail(client, world, cid)["messages"] if m["role"] == "agent"]
        assert [(m["turn"]["ai_service_name"], m["turn"]["ai_service_deleted"]) for m in agents] == [
            ("model-a", True), ("model-b", False),
        ]

    def test_skill_and_silo_deletion_is_flagged_too(self, client, db, world, fakes):
        silo = Silo(name="kb", app_id=world["app_id"], embedding_service_id=world["emb"])
        skill = Skill(name="sk", content="x", app_id=world["app_id"])
        db.add_all([silo, skill])
        db.commit()
        cid = ok_turn(client, world, "q", selection(world["ai_a"], silo=silo.silo_id, skills=[skill.skill_id]))[
            "conversation_id"
        ]
        db.delete(db.get(Silo, silo.silo_id))
        db.delete(db.get(Skill, skill.skill_id))
        db.commit()
        turn = [m for m in detail(client, world, cid)["messages"] if m["role"] == "agent"][0]["turn"]
        assert turn["silo_deleted"] is True and turn["silo_name"] == "kb"
        assert turn["skills"] == [{"id": skill.skill_id, "name": "sk", "deleted": True}]


# ------------------------------------------------------------------ AC-10 / AC-11: defaults and reopening


class TestDefaultsAndReopening:
    def test_defaults_follow_the_last_turn(self, client, world, fakes):
        url = f"{base(world['app_id'])}/defaults"
        app_default = client.get(url, headers=world["viewer"]).json()["ai_service_id"]  # nobody has chatted yet
        chosen = world["ai_b"] if app_default == world["ai_a"] else world["ai_a"]  # deliberately NOT the App default
        ok_turn(client, world, "q", selection(chosen, skills=[]))
        assert client.get(url, headers=world["alice"]).json() == selection(chosen)
        # per user: the viewer has not chatted, so still gets the App default, not alice's choice
        assert client.get(url, headers=world["viewer"]).json()["ai_service_id"] == app_default

    def test_a_deleted_silo_is_dropped_with_a_warning(self, client, db, world, fakes):
        silo = Silo(name="kb", app_id=world["app_id"], embedding_service_id=world["emb"])
        db.add(silo)
        db.commit()
        silo_id = silo.silo_id
        cid = ok_turn(client, world, "q", selection(world["ai_a"], silo=silo_id))["conversation_id"]
        db.delete(db.get(Silo, silo_id))
        db.commit()

        opened = detail(client, world, cid)
        assert opened["current_selection"]["silo_id"] is None
        assert opened["current_selection"]["ai_service_id"] == world["ai_a"]
        assert opened["warnings"] == [{"kind": "silo", "id": silo_id}]
        options = client.get(f"{base(world['app_id'])}/options", headers=world["alice"]).json()
        assert options["default_selection"]["silo_id"] is None
        assert options["default_warnings"] == [{"kind": "silo", "id": silo_id}]

    def test_reopening_restores_the_conversation_selection_not_the_default(self, client, db, world, fakes):
        skill = Skill(name="sk-p", content="x", app_id=world["app_id"])
        db.add(skill)
        db.commit()
        p = selection(world["ai_a"], skills=[skill.skill_id])
        q = selection(world["ai_b"])
        first = ok_turn(client, world, "with P", p)["conversation_id"]
        ok_turn(client, world, "with Q", q)  # another conversation: the user default becomes Q
        assert client.get(f"{base(world['app_id'])}/defaults", headers=world["alice"]).json() == q
        assert detail(client, world, first)["current_selection"] == p


# ------------------------------------------------------------------ AC-12: no usable model


class TestNoUsableModel:
    def test_an_app_without_services_has_no_usable_model(self, client, db, world):
        configure_factories(db)
        empty = AppFactory(owner=db.get(App, world["app_id"]).owner)
        db.commit()
        url = base(empty.app_id)
        options = client.get(f"{url}/options", headers=world["alice"]).json()
        assert options["has_usable_model"] is False and options["ai_services"] == []
        assert options["default_selection"] is None
        assert client.get(f"{url}/defaults", headers=world["alice"]).json() is None

    def test_only_retired_services_is_no_usable_model(self, client, db, world):
        configure_factories(db)
        empty = AppFactory(owner=db.get(App, world["app_id"]).owner)
        AIServiceFactory(app=empty, end_of_service_at=past(3))
        db.commit()
        options = client.get(f"{base(empty.app_id)}/options", headers=world["alice"]).json()
        assert options["has_usable_model"] is False and options["ai_services"] == []

    def test_a_deprecated_service_is_still_usable(self, client, db, world):
        configure_factories(db)
        empty = AppFactory(owner=db.get(App, world["app_id"]).owner)
        AIServiceFactory(app=empty, end_of_service_at=future(5))
        db.commit()
        options = client.get(f"{base(empty.app_id)}/options", headers=world["alice"]).json()
        assert options["has_usable_model"] is True
        assert options["ai_services"][0]["lifecycle_status"] == "deprecated"


# ------------------------------------------------------------------ AC-16: concurrent creation


@pytest.fixture
def committed_world(test_engine):
    """A real, committed App with no internal agent (concurrent requests need their own connections)."""
    from db.database import SessionLocal
    from services.app_service import AppService

    session = SessionLocal()
    try:
        configure_factories(session)
        user = UserFactory()
        app = AppFactory(owner=user)
        AIServiceFactory(app=app)
        session.commit()
        ids = {"user_id": user.user_id, "app_id": app.app_id, "headers": headers_for(user)}
    finally:
        session.close()
    yield ids

    failures: list[str] = []
    session = SessionLocal()
    try:
        AppService(session).delete_app(ids["app_id"])
        session.execute(text('DELETE FROM "User" WHERE user_id = :id'), {"id": ids["user_id"]})
        session.commit()
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        failures.append(f"cleanup raised {type(exc).__name__}: {exc}")
    finally:
        session.close()
    session = SessionLocal()
    try:
        if session.query(App).filter(App.app_id == ids["app_id"]).count():
            failures.append(f"App {ids['app_id']} is still in the database")
        if session.execute(text('SELECT 1 FROM "User" WHERE user_id = :id'), {"id": ids["user_id"]}).first():
            failures.append(f"User {ids['user_id']} is still in the database")
    finally:
        session.close()
    assert not failures, "committed_world teardown left data behind: " + "; ".join(failures)


def test_concurrent_first_use_creates_exactly_one_internal_agent(committed_world):
    from db.database import SessionLocal
    from main import app as fastapi_app

    app_id, headers = committed_world["app_id"], committed_world["headers"]
    barrier = threading.Barrier(10)
    statuses: list[int] = []
    errors: list[BaseException] = []

    def create():
        try:
            client = TestClient(fastapi_app)  # no lifespan: only the request path is exercised
            barrier.wait(timeout=15)
            statuses.append(client.post(f"{base(app_id)}/conversations", headers=headers, json={}).status_code)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=create) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not errors, errors
    assert statuses == [200] * 10

    session = SessionLocal()
    try:
        agents = session.query(Agent).filter(Agent.app_id == app_id, Agent.kind == "internal_chat").count()
        conversations = (
            session.query(Conversation).join(Agent, Agent.agent_id == Conversation.agent_id)
            .filter(Agent.app_id == app_id).count()
        )
    finally:
        session.close()
    assert agents == 1
    assert conversations == 10


# ------------------------------------------------------------------ AC-26: MCP


class TestMcp:
    @pytest.fixture
    def mcps(self, db, world):
        app_id = world["app_id"]
        good = MCPConfig(name="good", config={"alpha": {"url": "http://x", "transport": "streamable_http"}},
                         app_id=app_id)
        boom = MCPConfig(name="boom", config={"boom_srv": {"url": "http://y", "transport": "streamable_http"}},
                         app_id=app_id)
        unusable = MCPConfig(name="unusable", config="{not json", app_id=app_id)
        db.add_all([good, boom, unusable])
        db.commit()
        return {"good": good.config_id, "boom": boom.config_id, "unusable": unusable.config_id}

    @pytest.fixture
    def agent_log(self):
        from tools import agentTools

        records: list[logging.LogRecord] = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        handler = Capture(level=logging.WARNING)
        agentTools.logger.addHandler(handler)
        yield records
        agentTools.logger.removeHandler(handler)

    def test_a_selected_mcp_exposes_its_tools_and_an_unselected_one_does_not(self, client, world, fakes, mcps):
        a = world["ai_a"]
        cid = ok_turn(client, world, "with mcp", selection(a, mcps=[mcps["good"]]))["conversation_id"]
        assert "mcp_alpha" in fakes.tools_of(a)
        ok_turn(client, world, "without", selection(a), conversation_id=cid)
        assert "mcp_alpha" not in fakes.tools_of(a)
        assert len(fakes.mcp_clients) == 1, "no MCP client may be built when none is selected"

    def test_an_mcp_that_fails_to_connect_does_not_fail_the_turn(self, client, world, fakes, mcps, agent_log):
        a = world["ai_a"]
        body = ok_turn(client, world, "go", selection(a, mcps=[mcps["good"], mcps["boom"]]))
        assert body["response"] == f"hello from {a}"
        tools = fakes.tools_of(a)
        assert "mcp_boom_srv" not in tools and "mcp_alpha" not in tools  # the whole client failed: no MCP tools
        assert any("MCP tools unavailable" in r.getMessage() for r in agent_log)

    def test_a_connect_failure_is_reported_in_the_turn_warnings(self, client, world, fakes, mcps):
        body = ok_turn(client, world, "go", selection(world["ai_a"], mcps=[mcps["boom"]]))
        assert {"kind": "mcp_config", "id": mcps["boom"]} in body["turn"]["warnings"]

    def test_an_unusable_config_is_skipped_and_reported(self, client, world, fakes, mcps):
        a = world["ai_a"]
        sel = selection(a, mcps=[mcps["good"], mcps["unusable"]])
        warning = {"kind": "mcp_config", "id": mcps["unusable"]}

        body = ok_turn(client, world, "sync", sel)
        assert body["metadata"]["turn_config"]["warnings"] == [warning]
        assert body["turn"]["warnings"] == [warning]
        assert "mcp_alpha" in fakes.tools_of(a)
        assert [m["id"] for m in body["metadata"]["turn_config"]["mcp_configs"]] == [mcps["good"]]

        events = sse_turn(client, world, "stream", sel)
        meta, done = events[0], events[-1]
        assert meta["type"] == "metadata" and meta["data"]["turn_config"]["warnings"] == [warning]
        assert done["type"] == "done" and done["data"]["turn"]["warnings"] == [warning]
        # what the user asked for is remembered, even though one config was skipped
        assert client.get(f"{base(world['app_id'])}/defaults", headers=world["alice"]).json()[
            "mcp_config_ids"
        ] == sorted([mcps["good"], mcps["unusable"]])


# ------------------------------------------------------------------ SSE contract and frozen App


class TestStreamContract:
    def test_metadata_event_has_the_chat_shape_and_done_carries_the_turn(self, client, world, fakes):
        events = sse_turn(client, world, "hello", selection(world["ai_a"]))
        types = [e["type"] for e in events]
        assert types[0] == "metadata" and types[-1] == "done"
        meta = events[0]["data"]
        assert not {"session_id", "agent_id", "agent_name"} & set(meta)
        assert meta["turn_config"]["ai_service"] == {"id": world["ai_a"], "name": "model-a"}
        assert meta["turn_config"]["warnings"] == []
        assert events[-1]["data"]["turn"]["turn_index"] == 1

    def test_the_answer_streams_as_token_events(self, client, world, fakes):
        events = sse_turn(client, world, "hello", selection(world["ai_a"]))
        tokens = [e for e in events if e["type"] == "token"]
        assert len(tokens) >= 2, "the fake model must stream the answer in several chunks"
        assert "".join(t["data"]["content"] for t in tokens) == f"hello from {world['ai_a']}"
        assert events[-1]["type"] == "done"


class TestFrozenApp:
    def test_a_frozen_app_rejects_new_chat_activity(self, client, db, world, fakes):
        cid = ok_turn(client, world, "before", selection(world["ai_a"]))["conversation_id"]
        db.query(App).filter(App.app_id == world["app_id"]).update({"is_frozen": True})
        db.commit()
        url = base(world["app_id"])
        h = world["alice"]
        calls = len(fakes.calls)
        assert client.get(f"{url}/options", headers=h).status_code == 403
        assert client.get(f"{url}/defaults", headers=h).status_code == 403
        assert client.post(f"{url}/conversations", headers=h, json={}).status_code == 403
        for path in ("/messages", "/stream"):
            assert send(client, world, "x", selection(world["ai_a"]), cid, path=path).status_code == 403
        assert len(fakes.calls) == calls
        upload = client.post(
            f"{url}/conversations/{cid}/files", headers=h, files={"file": ("a.txt", b"x", "text/plain")}
        )
        assert upload.status_code == 403
        # reading stays possible
        assert client.get(f"{url}/conversations/{cid}", headers=h).status_code == 200

    def test_frozen_silos_and_skills_are_not_listed_nor_selectable(self, client, db, world, fakes):
        silo = Silo(name="frozen-silo", app_id=world["app_id"], embedding_service_id=world["emb"], is_frozen=True)
        skill = Skill(name="frozen-skill", content="x", app_id=world["app_id"], is_frozen=True)
        db.add_all([silo, skill])
        db.commit()
        options = client.get(f"{base(world['app_id'])}/options", headers=world["alice"]).json()
        assert silo.silo_id not in [s["silo_id"] for s in options["silos"]]
        assert skill.skill_id not in [s["skill_id"] for s in options["skills"]]
        for sel in (selection(world["ai_a"], silo=silo.silo_id), selection(world["ai_a"], skills=[skill.skill_id])):
            response = send(client, world, "x", sel)
            assert response.status_code == 404 and response.json() == NOT_FOUND


# ------------------------------------------------------------------ AC-27: SaaS billing and metrics


class TestSaasBillingAndMetrics:
    @pytest.fixture
    def system_service(self, db):
        configure_factories(db)
        service = AIServiceFactory(app=None, name="platform-model", description="gpt-sys")
        db.commit()
        yield service.service_id
        db.query(UsageRecord).delete()
        db.delete(db.get(type(service), service.service_id))
        db.commit()

    def test_a_system_model_is_billed_to_the_user_in_saas_mode(self, client, db, world, fakes, system_service, monkeypatch):
        monkeypatch.setenv("AICT_DEPLOYMENT_MODE", "saas")
        ok_turn(client, world, "billable", selection(system_service))
        records = db.query(UsageRecord).filter_by(user_id=world["alice_id"]).all()
        assert [r.call_count for r in records] == [1]
        assert db.query(UsageRecord).filter(UsageRecord.user_id != world["alice_id"]).count() == 0

    def test_an_own_model_is_not_billed(self, client, db, world, fakes, monkeypatch):
        monkeypatch.setenv("AICT_DEPLOYMENT_MODE", "saas")
        ok_turn(client, world, "free", selection(world["ai_a"]))
        assert db.query(UsageRecord).filter_by(user_id=world["alice_id"]).count() == 0

    def test_the_metrics_event_is_an_internal_chat_event_with_the_turns_model(self, client, world, fakes):
        ok_turn(client, world, "one", selection(world["ai_a"]))
        ok_turn(client, world, "two", selection(world["ai_b"]))
        sse_turn(client, world, "three", selection(world["ai_a"]))
        events = [p["event"] for p in fakes.wait_payloads(3)]
        assert {e["caller_type"] for e in events} == {"INTERNAL_CHAT"}
        assert sorted(e["ai_service_id"] for e in events) == sorted([world["ai_a"], world["ai_b"], world["ai_a"]])
        assert {e["user_id"] for e in events} == {world["alice_id"]}
        assert {e["status"] for e in events} == {"SUCCESS"}
