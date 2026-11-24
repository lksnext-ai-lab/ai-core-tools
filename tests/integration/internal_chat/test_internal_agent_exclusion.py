"""Integration (real PostgreSQL): the hidden internal chat agent is excluded and rejected everywhere.

Spec ``app-flexible-chat`` FR-13, AC-14, AC-15, AC-16, AC-29 (plan AD-6).

The internal chat agent is ``Agent.kind == 'internal_chat'``. Each surface must answer a request that
targets it exactly like a request that targets a non-existent agent id (same status and same body),
must never list it, and must have no side effect on its row, its association tables, its conversations
or its scheduled tasks.
"""

import json
import logging
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from db.database import Base
from models.agent import AGENT_KIND_INTERNAL_CHAT, Agent
from models.agent_marketplace_profile import AgentMarketplaceProfile
from models.agent_marketplace_rating import AgentMarketplaceRating
from models.conversation_starter import ConversationStarter
from models.app import App
from models.app_collaborator import CollaborationRole
from models.conversation import Conversation, ConversationSource
from models.scheduled_task import ScheduledTask
from tests.factories import AgentFactory, AIServiceFactory, APIKeyFactory, configure_factories
from tests.integration.a2a_server.conftest import a2a_committed_world, a2a_sdk_tables  # noqa: F401  (fixtures)
from tests.integration.routers.internal._eos_helpers import headers_for, member_headers

MISSING_ID = 999999  # placeholder; the autouse fixture below derives a real never-used id per test
API_KEY = "internal-chat-exclusion-key-0001-integration-only"  # pragma: allowlist secret


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _derive_missing_id(db):
    """An id that can not exist: far above the highest Agent id of the DB (instead of a hard-coded 999999)."""
    global MISSING_ID
    MISSING_ID = (db.query(sa.func.max(Agent.agent_id)).scalar() or 0) + 10_000_000


def _agent_fk_columns():
    """(table, column) for every FK pointing at ``Agent.agent_id`` (association/dependent tables)."""
    out = []
    for table in Base.metadata.sorted_tables:
        for fk in table.foreign_keys:
            if fk.column.table.name == "Agent" and fk.column.name == "agent_id":
                out.append((table, fk.parent))
    return out


def snapshot(db, *agent_ids):
    """Full DB state of the given agents: their row plus every row of every table referencing them."""
    db.flush()
    agent_table = Base.metadata.tables["Agent"]
    state = {}
    rows = db.execute(sa.select(agent_table).where(agent_table.c.agent_id.in_(agent_ids))).mappings().all()
    state["Agent"] = sorted(repr(sorted(dict(r).items())) for r in rows)
    for table, column in _agent_fk_columns():
        rows = db.execute(sa.select(table).where(column.in_(agent_ids))).mappings().all()
        state[f"{table.name}.{column.name}"] = sorted(repr(sorted(dict(r).items())) for r in rows)
    # Tables that carry an agent_id column WITHOUT a foreign key (not reflected above).
    covered = {table.name for table, _ in _agent_fk_columns()} | {"Agent"}
    for name, in db.execute(sa.text(
        "SELECT table_name FROM information_schema.columns WHERE table_schema = current_schema() "
        "AND column_name = 'agent_id'"
    )).fetchall():
        if name in covered:
            continue
        rows = db.execute(
            sa.text(f'SELECT * FROM "{name}" WHERE agent_id = ANY(:ids)'), {"ids": list(agent_ids)}
        ).mappings().all()
        state[f"{name}.agent_id(no-fk)"] = sorted(repr(sorted(dict(r).items())) for r in rows)
    # LangGraph checkpoint rows of the agents' threads (thread_{agent_id}_{session}).
    for name, in db.execute(sa.text(
        "SELECT table_name FROM information_schema.columns WHERE table_schema = current_schema() "
        "AND column_name = 'thread_id' AND table_name LIKE 'checkpoint%'"
    )).fetchall():
        for agent_id in agent_ids:
            count = db.execute(
                sa.text(f'SELECT count(*) FROM "{name}" WHERE thread_id LIKE :p'), {"p": f"thread_{agent_id}\\_%"}
            ).scalar()
            state[f"{name}.thread_{agent_id}"] = count
    return state


def assert_same(hidden, missing, hidden_id=None):
    """Same status and same body/detail as the response for a non-existent agent id.

    Some surfaces echo the requested id in the detail ("Agent 54 not found"); when ``hidden_id`` is given
    it is normalised to ``MISSING_ID`` before comparing, so only the echoed id may differ.
    """
    assert hidden.status_code == missing.status_code, (hidden.status_code, hidden.text, missing.status_code, missing.text)
    try:
        hidden_body, missing_body = hidden.json(), missing.json()
    except ValueError:
        hidden_body, missing_body = hidden.text, missing.text
    if hidden_id is not None:
        hidden_body = json.loads(json.dumps(hidden_body).replace(str(hidden_id), str(MISSING_ID)))
    assert hidden_body == missing_body


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def standard_agent(db, fake_app, fake_ai_service):
    configure_factories(db)
    return AgentFactory(app=fake_app, ai_service=fake_ai_service, name="Standard Agent", is_tool=True)


@pytest.fixture
def internal_agent(db, fake_app, fake_user, standard_agent):
    """The hidden agent inserted directly, with associations and dependents that a buggy path could change."""
    from models.mcp_config import MCPConfig
    from models.middleware import Middleware, MiddlewareType
    from tests.factories import SkillFactory

    configure_factories(db)
    agent = Agent(
        name="__internal_chat__", description="", system_prompt="", app_id=fake_app.app_id,
        kind=AGENT_KIND_INTERNAL_CHAT, has_memory=True, temperature=0.7,
    )
    db.add(agent)
    db.flush()

    skill = SkillFactory(app=fake_app)
    mcp_config = MCPConfig(name="cfg", config={"x": {"url": "http://x", "transport": "streamable_http"}}, app_id=fake_app.app_id)
    middleware = Middleware(name="mw", middleware_type=MiddlewareType.SUMMARIZATION, config={}, app_id=fake_app.app_id)
    db.add_all([mcp_config, middleware])
    db.flush()
    db.execute(sa.text("INSERT INTO agent_skills (agent_id, skill_id) VALUES (:a, :s)"),
               {"a": agent.agent_id, "s": skill.skill_id})
    db.execute(sa.text("INSERT INTO agent_mcps (agent_id, config_id) VALUES (:a, :c)"),
               {"a": agent.agent_id, "c": mcp_config.config_id})
    db.execute(sa.text('INSERT INTO agent_middlewares (agent_id, middleware_id, "order") VALUES (:a, :m, 0)'),
               {"a": agent.agent_id, "m": middleware.middleware_id})
    profile = AgentMarketplaceProfile(agent_id=agent.agent_id, display_name="x")
    db.add(profile)
    db.flush()
    db.add(ConversationStarter(profile_id=profile.id, prompt="internal starter", order=0))
    db.add(AgentMarketplaceRating(profile_id=profile.id, user_id=fake_user.user_id, rating=4))
    db.add(ScheduledTask(
        name="t", agent_id=agent.agent_id, app_id=fake_app.app_id, created_by=fake_user.user_id,
        orchestrator_schedule_name="sched-internal-excl", cron_expression="*/5 * * * *", input={"message": "hi"},
    ))
    for tag, source in (("chat", ConversationSource.INTERNAL_CHAT), ("odd", ConversationSource.PLAYGROUND)):
        db.add(Conversation(
            agent_id=agent.agent_id, session_id=f"conv_{agent.agent_id}_{tag}", title=tag, message_count=0,
            user_id=fake_user.user_id, source=source,
        ))
    db.flush()
    return agent


@pytest.fixture
def api_key(db, fake_app, fake_user):
    configure_factories(db)
    return APIKeyFactory(app=fake_app, user=fake_user, key=API_KEY)


@pytest.fixture
def role_headers(db, fake_app, fake_user, owner_headers, monkeypatch):
    """Headers per role: OWNER, ADMINISTRATOR, VIEWER and an OMNIADMIN that is not a collaborator."""
    from tests.factories import UserFactory

    from models.app_collaborator import CollaborationStatus
    from tests.factories import AppCollaboratorFactory

    configure_factories(db)
    omni = UserFactory(email="omni-internal-excl@mattin-test.com")
    omni_member = UserFactory(email="omni-member-internal-excl@mattin-test.com")
    AppCollaboratorFactory(app=fake_app, user=omni_member, role=CollaborationRole.ADMINISTRATOR,
                           status=CollaborationStatus.ACCEPTED, invited_by=fake_app.owner_id)
    monkeypatch.setenv("AICT_OMNIADMINS", f"{omni.email},{omni_member.email}")
    db.flush()
    return {
        "OWNER": owner_headers,
        "ADMINISTRATOR": member_headers(db, fake_app, CollaborationRole.ADMINISTRATOR),
        "VIEWER": member_headers(db, fake_app, CollaborationRole.VIEWER),
        # OMNIADMIN with no collaboration on the App: platform-level privileges only (403 on App routes).
        "OMNIADMIN": headers_for(omni),
        # OMNIADMIN that is also an ADMINISTRATOR collaborator of the App.
        "OMNIADMIN_MEMBER": headers_for(omni_member),
    }


ROLES = ["OWNER", "ADMINISTRATOR", "VIEWER", "OMNIADMIN_MEMBER"]


@pytest.fixture
def exposed(db, internal_agent):
    """Make the internal agent LOOK exposed so only the ``visible_clause()`` filters can hide it.

    The DB CHECK ``ck_agent_internal_chat_unexposed`` pins the internal agent to ``is_tool=false``,
    ``a2a_enabled=false``, ``UNPUBLISHED`` and no code interpreter, which would make several surfaces
    reject it for an unrelated reason ("not a tool", "not enabled", "not published"). This fixture drops
    the CHECK inside the test's own transaction and forces those columns, so that removing
    ``Agent.visible_clause()`` from a query turns the test red.

    PostgreSQL DDL is transactional: the ``db`` fixture rolls the whole connection transaction back at
    teardown, which restores the constraint (``TestDbConstraints.test_unexposed_check_is_in_place`` guards
    that it never leaks). ``ALTER TABLE`` holds an ACCESS EXCLUSIVE lock on "Agent" until that rollback,
    so another pytest session using the same test DB blocks for the few ms the test lasts.
    """
    db.flush()
    db.execute(sa.text('ALTER TABLE "Agent" DROP CONSTRAINT ck_agent_internal_chat_unexposed'))
    db.execute(
        sa.text(
            "UPDATE \"Agent\" SET is_tool = true, a2a_enabled = true, marketplace_visibility = 'PUBLIC' "
            "WHERE agent_id = :a"
        ),
        {"a": internal_agent.agent_id},
    )
    db.expire_all()
    assert internal_agent.is_tool is True and internal_agent.a2a_enabled is True
    return internal_agent


@pytest.fixture
def exec_mocks():
    """Replace the execution entry points: a route that reaches them proves the agent was NOT filtered."""
    from types import SimpleNamespace

    from services.agent_execution_service import AgentExecutionService
    from services.agent_streaming_service import AgentStreamingService
    from services.file_management_service import FileManagementService

    result = {"response": "mock answer", "agent_id": 1, "conversation_id": 1,
              "metadata": {"agent_name": "x", "agent_type": "agent", "files_processed": 0, "has_memory": False}}

    async def stream(*args, **kwargs):
        yield 'data: {"type": "token", "data": "hi"}\n\n'

    chat = AsyncMock(return_value=result)
    ocr = AsyncMock(return_value={"result": {"content": "ocr text"}, "agent_id": 1, "metadata": {}, "extracted_text": "ocr text"})
    reset = AsyncMock(return_value=True)
    streaming = MagicMock(side_effect=lambda *a, **k: stream())
    with patch.object(AgentExecutionService, "execute_agent_chat_with_file_refs", chat), \
            patch.object(AgentExecutionService, "execute_agent_ocr", ocr), \
            patch.object(AgentExecutionService, "reset_agent_conversation", reset), \
            patch.object(AgentStreamingService, "stream_agent_chat", streaming), \
            patch.object(FileManagementService, "resolve_chat_files", AsyncMock(return_value=[])):
        yield SimpleNamespace(chat=chat, ocr=ocr, reset=reset, stream=streaming,
                              executed=lambda: any(m.called for m in (chat, ocr, streaming)))


@pytest.fixture(params=["as_created", "forced_exposed"])
def hidden(request):
    """The internal agent as the product creates it, and forced to look like a tool/public/A2A agent
    (CHECK dropped) so that only ``visible_clause()`` can hide it."""
    return request.getfixturevalue("internal_agent" if request.param == "as_created" else "exposed")


def _agents_base(app) -> str:
    return f"/internal/apps/{app.app_id}/agents"


# ---------------------------------------------------------------------------
# Internal agents router
# ---------------------------------------------------------------------------

_UPDATE_BODY = {"name": "renamed", "description": "d", "system_prompt": "p"}

# (case id, method, path suffix with {aid}, request kwargs)
INTERNAL_ROUTER_CASES = [
    ("detail", "get", "/{aid}", {}),
    ("update", "post", "/{aid}", {"json": _UPDATE_BODY}),
    ("update_is_tool", "post", "/{aid}", {"json": {**_UPDATE_BODY, "is_tool": True}}),
    ("update_a2a_enabled", "post", "/{aid}", {"json": {**_UPDATE_BODY, "a2a_enabled": True}}),
    ("delete", "delete", "/{aid}", {}),
    ("export", "post", "/{aid}/export", {}),
    ("update_prompt", "post", "/{aid}/update-prompt", {"json": {"type": "system", "prompt": "x"}}),
    ("playground", "get", "/{aid}/playground", {}),
    ("chat", "post", "/{aid}/chat", {"data": {"message": "hi"}}),
    ("chat_stream", "post", "/{aid}/chat/stream", {"data": {"message": "hi"}}),
    ("reset", "post", "/{aid}/reset", {}),
    ("conversation_history", "get", "/{aid}/conversation-history", {}),
    ("upload_file", "post", "/{aid}/upload-file", {"files": {"file": ("a.txt", b"hello", "text/plain")}}),
    ("files", "get", "/{aid}/files", {}),
    ("marketplace_visibility", "put", "/{aid}/marketplace-visibility", {"json": {"marketplace_visibility": "public"}}),
    ("marketplace_profile_get", "get", "/{aid}/marketplace-profile", {}),
    ("marketplace_profile_put", "put", "/{aid}/marketplace-profile", {"json": {"display_name": "x"}}),
]


# Cases whose route needs EDITOR: a VIEWER is refused with 403 before the agent is looked up.
EDITOR_ONLY_CASES = {
    "update", "update_is_tool", "update_a2a_enabled", "delete", "update_prompt",
    "marketplace_visibility", "marketplace_profile_put",
}
# `files` answers 500 for a missing agent too (pre-existing router quirk wrapping its own 404): only
# "same as missing" can be pinned there.
SAME_AS_MISSING_ONLY = {"files"}
EXECUTION_CASES = {"chat", "chat_stream"}


def _expected_status(role, case_id):
    if role == "VIEWER" and case_id in EDITOR_ONLY_CASES:
        return 403
    return 404


class TestInternalAgentsRouter:
    @pytest.mark.parametrize("role", ROLES)
    @pytest.mark.parametrize("case", INTERNAL_ROUTER_CASES, ids=[c[0] for c in INTERNAL_ROUTER_CASES])
    def test_rejection_matches_missing_agent_and_has_no_side_effect(
        self, client, db, fake_app, standard_agent, internal_agent, role_headers, exec_mocks, role, case
    ):
        case_id, method, path, kwargs = case
        headers = role_headers[role]
        before = snapshot(db, internal_agent.agent_id, standard_agent.agent_id)
        url = _agents_base(fake_app) + path

        missing = getattr(client, method)(url.format(aid=MISSING_ID), headers=headers, **kwargs)
        hidden = getattr(client, method)(url.format(aid=internal_agent.agent_id), headers=headers, **kwargs)

        assert_same(hidden, missing)
        if case_id not in SAME_AS_MISSING_ONLY:
            assert hidden.status_code == _expected_status(role, case_id), hidden.text
            if hidden.status_code == 404:
                assert hidden.json() == {"detail": "Agent not found"}
        else:
            assert hidden.status_code >= 400
        assert not exec_mocks.executed()  # the agent never reached the execution layer
        assert snapshot(db, internal_agent.agent_id, standard_agent.agent_id) == before

    @pytest.mark.parametrize("case", INTERNAL_ROUTER_CASES, ids=[c[0] for c in INTERNAL_ROUTER_CASES])
    def test_control_route_is_reachable_for_a_standard_agent(
        self, client, fake_app, standard_agent, internal_agent, owner_headers, exec_mocks, case
    ):
        """Same request against a standard agent: not 401/403/422 and not the "agent not found" answer,
        so the 404 above comes from the agent filter and not from routing or a malformed request."""
        case_id, method, path, kwargs = case
        url = _agents_base(fake_app) + path
        missing = getattr(client, method)(url.format(aid=MISSING_ID), headers=owner_headers, **kwargs)
        control = getattr(client, method)(url.format(aid=standard_agent.agent_id), headers=owner_headers, **kwargs)
        assert control.status_code not in (401, 403, 422), control.text
        assert control.status_code != missing.status_code or control.text != missing.text
        if case_id == "chat":
            assert control.status_code == 200 and exec_mocks.chat.called
        if case_id == "chat_stream":
            assert control.status_code == 200 and exec_mocks.stream.called

    @pytest.mark.parametrize("role", ROLES)
    def test_list_excludes_internal_agent(self, client, fake_app, standard_agent, internal_agent, role_headers, role):
        resp = client.get(_agents_base(fake_app) + "/", headers=role_headers[role])
        assert resp.status_code == 200
        ids = [a["agent_id"] for a in resp.json()]
        assert standard_agent.agent_id in ids
        assert internal_agent.agent_id not in ids

    @pytest.mark.parametrize("role", ROLES)
    def test_not_listed_in_other_agent_form_tools(
        self, client, fake_app, fake_ai_service, standard_agent, hidden, role_headers, role
    ):
        configure = AgentFactory(app=fake_app, ai_service=fake_ai_service, name="Other")
        resp = client.get(f"{_agents_base(fake_app)}/{configure.agent_id}", headers=role_headers[role])
        assert resp.status_code == 200
        tools = resp.json()["tools"]
        tool_ids = [t.get("agent_id", t.get("id")) for t in tools]
        assert standard_agent.agent_id in tool_ids
        assert hidden.agent_id not in tool_ids

    def test_new_agent_form_tools_exclude_hidden(self, client, fake_app, standard_agent, hidden, owner_headers):
        resp = client.get(f"{_agents_base(fake_app)}/0", headers=owner_headers)
        assert resp.status_code == 200
        tools = resp.json()["tools"]
        assert standard_agent.agent_id in [t.get("agent_id", t.get("id")) for t in tools]
        assert hidden.agent_id not in [t.get("agent_id", t.get("id")) for t in tools]
        assert "__internal_chat__" not in json.dumps(tools)

    def test_adding_hidden_as_tool_is_ignored_like_unknown_id(
        self, client, db, fake_app, fake_ai_service, standard_agent, hidden, owner_headers
    ):
        configure_factories(db)
        target = AgentFactory(app=fake_app, ai_service=fake_ai_service, name="Target")
        url = f"{_agents_base(fake_app)}/{target.agent_id}"
        body = {**_UPDATE_BODY, "name": "Target"}
        before_internal = snapshot(db, hidden.agent_id)

        missing = client.post(url, json={**body, "tool_ids": [MISSING_ID]}, headers=owner_headers)
        tools_after_missing = db.execute(
            sa.text("SELECT tool_id FROM agent_tools WHERE agent_id = :a"), {"a": target.agent_id}
        ).fetchall()
        hidden_resp = client.post(url, json={**body, "tool_ids": [hidden.agent_id]}, headers=owner_headers)
        tools_after_hidden = db.execute(
            sa.text("SELECT tool_id FROM agent_tools WHERE agent_id = :a"), {"a": target.agent_id}
        ).fetchall()

        assert_same(hidden_resp, missing)
        assert tools_after_missing == [] and tools_after_hidden == []
        assert snapshot(db, hidden.agent_id) == before_internal

        # Control: a standard tool agent in `tool_ids` IS attached.
        ok = client.post(url, json={**body, "tool_ids": [standard_agent.agent_id]}, headers=owner_headers)
        assert ok.status_code == 200, ok.text
        assert [r[0] for r in db.execute(sa.text("SELECT tool_id FROM agent_tools WHERE agent_id = :a"),
                                         {"a": target.agent_id})] == [standard_agent.agent_id]

    def test_omniadmin_member_cannot_see_or_edit(self, client, fake_app, internal_agent, standard_agent, role_headers):
        headers = role_headers["OMNIADMIN_MEMBER"]
        assert client.get(f"{_agents_base(fake_app)}/{internal_agent.agent_id}", headers=headers).status_code == 404
        listing = client.get(_agents_base(fake_app) + "/", headers=headers).json()
        assert internal_agent.agent_id not in [a["agent_id"] for a in listing]


class TestOmniadminWithoutCollaboration:
    """OMNIADMIN has no App-level bypass: App routes are 403 for the hidden and a missing agent alike."""

    def test_list_and_write_routes_are_403_for_both_ids(
        self, client, fake_app, standard_agent, internal_agent, role_headers
    ):
        headers = role_headers["OMNIADMIN"]
        base = _agents_base(fake_app)
        assert client.get(base + "/", headers=headers).status_code == 403
        for aid in (MISSING_ID, internal_agent.agent_id):
            assert client.post(f"{base}/{aid}", json=_UPDATE_BODY, headers=headers).status_code == 403
            assert client.get(f"{base}/{aid}", headers=headers).status_code == 403


# ---------------------------------------------------------------------------
# Public API (X-API-KEY) and OpenAI-compatible endpoint
# ---------------------------------------------------------------------------

_PDF = {"pdf": ("a.pdf", b"%PDF-1.4", "application/pdf")}
PUBLIC_CASES = [
    ("agent_detail", "get", "/agents/{aid}", {}),
    ("agent_update", "put", "/agents/{aid}", {"json": {"name": "renamed"}}),
    ("agent_update_is_tool", "put", "/agents/{aid}", {"json": {"name": "renamed", "is_tool": True}}),
    ("agent_delete", "delete", "/agents/{aid}", {}),
    ("agent_chat_filters", "get", "/agents/{aid}/chat-filters/foo", {}),
    ("chat_call", "post", "/chat/{aid}/call", {"data": {"message": "hi"}}),
    ("chat_call_stream", "post", "/chat/{aid}/call/stream", {"data": {"message": "hi"}}),
    ("chat_reset", "post", "/chat/{aid}/reset", {}),
    ("conversation_create", "post", "/chat/{aid}/conversations", {"json": {}}),
    ("conversation_list", "get", "/chat/{aid}/conversations", {}),
    ("files_attach", "post", "/files/{aid}/attach-file", {"files": {"file": ("a.txt", b"hello", "text/plain")}}),
    ("files_list", "get", "/files/{aid}/attached-files", {}),
    ("files_detach", "delete", "/files/{aid}/detach-file/abc", {}),
    ("ocr_process", "post", "/ocr/{aid}/process", {"files": _PDF}),
]
# Every case must answer 404 for a missing agent (so the filter, not a 422, is what is compared).
PUBLIC_MISSING_STATUS = {}  # no legitimate exception


class TestPublicApi:
    @pytest.fixture
    def ocr_agent(self, db, fake_app, fake_ai_service):
        from models.ocr_agent import OCRAgent

        agent = OCRAgent(
            name="ocr", description="", app_id=fake_app.app_id, service_id=fake_ai_service.service_id,
            vision_service_id=fake_ai_service.service_id, system_prompt="", has_memory=False, temperature=0.7,
        )
        db.add(agent)
        db.flush()
        return agent

    @pytest.mark.parametrize("case", PUBLIC_CASES, ids=[c[0] for c in PUBLIC_CASES])
    def test_rejection_matches_missing_agent_and_has_no_side_effect(
        self, client, db, fake_app, standard_agent, internal_agent, api_key, exec_mocks, case
    ):
        case_id, method, path, kwargs = case
        url = f"/public/v1/app/{fake_app.app_id}{path}"
        headers = {"X-API-KEY": api_key.key}
        before = snapshot(db, internal_agent.agent_id, standard_agent.agent_id)

        missing = getattr(client, method)(url.format(aid=MISSING_ID), headers=headers, **kwargs)
        hidden = getattr(client, method)(url.format(aid=internal_agent.agent_id), headers=headers, **kwargs)

        assert missing.status_code == PUBLIC_MISSING_STATUS.get(case_id, 404), missing.text
        assert_same(hidden, missing, internal_agent.agent_id)
        assert not exec_mocks.executed()  # never reached the execution layer
        assert snapshot(db, internal_agent.agent_id, standard_agent.agent_id) == before

    @pytest.mark.parametrize("case", PUBLIC_CASES, ids=[c[0] for c in PUBLIC_CASES])
    def test_control_route_and_api_key_work_for_a_standard_agent(
        self, client, db, fake_app, standard_agent, ocr_agent, internal_agent, api_key, exec_mocks, case
    ):
        """Proves the route, the API key and the body are valid: only the agent differs."""
        case_id, method, path, kwargs = case
        url = f"/public/v1/app/{fake_app.app_id}{path}"
        headers = {"X-API-KEY": api_key.key}
        agent = ocr_agent if case_id == "ocr_process" else standard_agent
        missing = getattr(client, method)(url.format(aid=MISSING_ID), headers=headers, **kwargs)
        control = getattr(client, method)(url.format(aid=agent.agent_id), headers=headers, **kwargs)
        assert control.status_code not in (401, 403, 422), control.text
        assert (control.status_code, control.text) != (missing.status_code, missing.text)
        if case_id == "chat_call":
            assert control.status_code == 200 and exec_mocks.chat.called
        if case_id == "chat_call_stream":
            assert control.status_code == 200 and exec_mocks.stream.called
        if case_id == "ocr_process":
            assert control.status_code == 200 and exec_mocks.ocr.called

    def test_list_excludes_internal_agent(self, client, fake_app, standard_agent, internal_agent, api_key):
        resp = client.get(f"/public/v1/app/{fake_app.app_id}/agents", headers={"X-API-KEY": api_key.key})
        assert resp.status_code == 200
        ids = [a["agent_id"] for a in resp.json()["agents"]]
        assert standard_agent.agent_id in ids
        assert internal_agent.agent_id not in ids

    def test_creating_agent_through_public_api_with_internal_tool_id_is_like_unknown_tool_id(
        self, client, db, fake_app, fake_ai_service, standard_agent, internal_agent, api_key
    ):
        url = f"/public/v1/app/{fake_app.app_id}/agents"
        headers = {"X-API-KEY": api_key.key}
        before = snapshot(db, internal_agent.agent_id)
        body = {"name": "pub-new", "service_id": fake_ai_service.service_id}
        missing = client.post(url, json={**body, "tool_ids": [MISSING_ID]}, headers=headers)
        hidden = client.post(url, json={**body, "name": "pub-new-2", "tool_ids": [internal_agent.agent_id]},
                             headers=headers)
        assert hidden.status_code == missing.status_code
        assert snapshot(db, internal_agent.agent_id) == before
        tool_rows = db.execute(sa.text(
            "SELECT count(*) FROM agent_tools WHERE tool_id IN (:a, :b)"), {"a": MISSING_ID, "b": internal_agent.agent_id}
        ).scalar()
        assert tool_rows == 0


@pytest.fixture
def openai_enabled(db, fake_app):
    fake_app.enable_openai_api = True
    db.flush()


class TestOpenAICompatible:
    def _base(self, app):
        return f"/public/v1/app/{app.app_id}/openai/v1"

    def test_models_list_excludes_internal_agent(
        self, client, fake_app, standard_agent, internal_agent, api_key, openai_enabled
    ):
        resp = client.get(self._base(fake_app) + "/models", headers={"X-API-KEY": api_key.key})
        assert resp.status_code == 200
        ids = [m["id"] for m in resp.json()["data"]]
        assert str(standard_agent.agent_id) in ids
        assert str(internal_agent.agent_id) not in ids

    @pytest.mark.parametrize("stream", [False, True])
    def test_chat_completions_matches_missing_agent_and_has_no_side_effect(
        self, client, db, fake_app, standard_agent, internal_agent, api_key, openai_enabled, exec_mocks, stream
    ):
        headers = {"X-API-KEY": api_key.key}
        before = snapshot(db, internal_agent.agent_id)

        def call(model):
            return client.post(
                self._base(fake_app) + "/chat/completions", headers=headers,
                json={"model": str(model), "messages": [{"role": "user", "content": "hi"}], "stream": stream},
            )

        missing, hidden = call(MISSING_ID), call(internal_agent.agent_id)
        assert missing.status_code == 404
        assert_same(hidden, missing)
        assert not exec_mocks.executed()
        assert snapshot(db, internal_agent.agent_id) == before

        # Control: the same request against a standard memoryless agent reaches the execution layer.
        # Non-streaming has no control: `openai.py` builds `AgentExecutionService(db)` but its __init__ takes
        # no argument, so every non-streaming call raises TypeError (pre-existing on the base branch, reported
        # separately) before it could execute.
        if stream:
            control = call(standard_agent.agent_id)
            assert control.status_code == 200, control.text
            assert exec_mocks.stream.called


# ---------------------------------------------------------------------------
# Generic /internal/conversations router (no App RBAC; AD-6.14)
# ---------------------------------------------------------------------------


class TestGenericConversationsRouter:
    def _conv(self, db, agent, fake_user, tag, source=ConversationSource.PLAYGROUND):
        conv = Conversation(
            agent_id=agent.agent_id, session_id=f"conv_{agent.agent_id}_{tag}", title=tag, message_count=0,
            user_id=fake_user.user_id, source=source,
        )
        db.add(conv)
        db.flush()
        return conv

    def test_create_with_internal_agent_matches_missing_agent(
        self, client, db, standard_agent, internal_agent, auth_headers
    ):
        before = snapshot(db, internal_agent.agent_id)
        missing = client.post(f"/internal/conversations?agent_id={MISSING_ID}", headers=auth_headers)
        hidden = client.post(f"/internal/conversations?agent_id={internal_agent.agent_id}", headers=auth_headers)
        assert missing.status_code == 404
        assert missing.json() == {"detail": "Agent not found"}
        assert_same(hidden, missing)
        assert snapshot(db, internal_agent.agent_id) == before

    def test_create_with_standard_agent_still_works(self, client, standard_agent, internal_agent, auth_headers):
        resp = client.post(f"/internal/conversations?agent_id={standard_agent.agent_id}", headers=auth_headers)
        assert resp.status_code == 200

    def test_list_with_internal_agent_is_empty(self, client, standard_agent, internal_agent, auth_headers):
        resp = client.get(f"/internal/conversations?agent_id={internal_agent.agent_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 0 and resp.json()["conversations"] == []

    @pytest.mark.parametrize("method,suffix,kwargs", [
        ("get", "", {}),
        ("get", "/history", {}),
        ("patch", "", {"json": {"title": "hijack"}}),
        ("delete", "", {}),
    ], ids=["get", "history", "patch", "delete"])
    def test_conversations_of_internal_agent_are_not_found(
        self, client, db, fake_user, standard_agent, internal_agent, auth_headers, method, suffix, kwargs
    ):
        internal_convs = db.query(Conversation).filter(Conversation.agent_id == internal_agent.agent_id).all()
        assert {c.source for c in internal_convs} == {ConversationSource.INTERNAL_CHAT, ConversationSource.PLAYGROUND}
        before = snapshot(db, internal_agent.agent_id)
        for conv in internal_convs:  # INTERNAL_CHAT source and another source of the same internal agent
            hidden = getattr(client, method)(f"/internal/conversations/{conv.conversation_id}{suffix}",
                                             headers=auth_headers, **kwargs)
            assert hidden.status_code == 404
            assert hidden.json() == {"detail": "Conversation not found"}
        missing = getattr(client, method)(f"/internal/conversations/{MISSING_ID}{suffix}", headers=auth_headers, **kwargs)
        assert_same(hidden, missing)
        assert snapshot(db, internal_agent.agent_id) == before

    def test_standard_agent_conversation_works_on_all_endpoints(
        self, client, db, fake_user, standard_agent, internal_agent, auth_headers
    ):
        conv = self._conv(db, standard_agent, fake_user, "std")
        cid = conv.conversation_id
        assert client.get(f"/internal/conversations/{cid}", headers=auth_headers).status_code == 200
        assert client.get(f"/internal/conversations/{cid}/history", headers=auth_headers).status_code == 200
        listed = client.get(f"/internal/conversations?agent_id={standard_agent.agent_id}", headers=auth_headers)
        assert listed.status_code == 200 and listed.json()["total"] == 1
        patched = client.patch(f"/internal/conversations/{cid}", json={"title": "new"}, headers=auth_headers)
        assert patched.status_code == 200 and patched.json()["title"] == "new"
        assert client.delete(f"/internal/conversations/{cid}", headers=auth_headers).status_code == 200


# ---------------------------------------------------------------------------
# Marketplace
# ---------------------------------------------------------------------------

MARKETPLACE_CASES = [
    ("detail", "get", "/agents/{aid}", {}),
    # conversation-starters / my-rating: dedicated test below (they answer 200 for a missing agent).
    ("rate", "post", "/agents/{aid}/rate", {"json": {"rating": 5}}),
    ("start_conversation", "post", "/agents/{aid}/conversations", {}),
]


class TestMarketplace:
    @pytest.fixture
    def published_standard(self, db, standard_agent, fake_user):
        """A published standard agent: the control that proves the marketplace routes work."""
        from datetime import timezone
        from models.agent import MarketplaceVisibility

        standard_agent.is_tool = False
        standard_agent.marketplace_visibility = MarketplaceVisibility.PUBLIC
        profile = AgentMarketplaceProfile(
            agent_id=standard_agent.agent_id, display_name="Std", published_at=datetime.now(timezone.utc))
        db.add(profile)
        db.flush()
        db.add(ConversationStarter(profile_id=profile.id, prompt="standard starter", order=0))
        db.add(AgentMarketplaceRating(profile_id=profile.id, user_id=fake_user.user_id, rating=3))
        db.flush()
        return standard_agent

    @pytest.mark.parametrize("case", MARKETPLACE_CASES, ids=[c[0] for c in MARKETPLACE_CASES])
    def test_rejection_matches_missing_agent_and_has_no_side_effect(
        self, client, db, standard_agent, internal_agent, auth_headers, case
    ):
        case_id, method, path, kwargs = case
        before = snapshot(db, internal_agent.agent_id)
        url = "/internal/marketplace" + path
        missing = getattr(client, method)(url.format(aid=MISSING_ID), headers=auth_headers, **kwargs)
        hidden = getattr(client, method)(url.format(aid=internal_agent.agent_id), headers=auth_headers, **kwargs)
        assert_same(hidden, missing, internal_agent.agent_id)
        assert snapshot(db, internal_agent.agent_id) == before

    @pytest.mark.parametrize("case", MARKETPLACE_CASES, ids=[c[0] for c in MARKETPLACE_CASES])
    def test_rejection_holds_even_if_the_agent_looked_published(
        self, client, db, fake_user, standard_agent, exposed, auth_headers, case
    ):
        """With the unexposed CHECK dropped and the agent forced PUBLIC, only ``visible_clause()`` hides it."""
        case_id, method, path, kwargs = case
        db.add(Conversation(  # a prior marketplace conversation, so `rate` is not refused for that reason
            agent_id=exposed.agent_id, user_id=fake_user.user_id, session_id=f"conv_{exposed.agent_id}_mkt",
            source=ConversationSource.MARKETPLACE, message_count=0))
        db.flush()
        before = snapshot(db, exposed.agent_id)
        url = "/internal/marketplace" + path
        missing = getattr(client, method)(url.format(aid=MISSING_ID), headers=auth_headers, **kwargs)
        hidden = getattr(client, method)(url.format(aid=exposed.agent_id), headers=auth_headers, **kwargs)
        assert_same(hidden, missing, exposed.agent_id)
        assert snapshot(db, exposed.agent_id) == before

    def test_control_published_standard_agent_is_served(self, client, db, fake_user, published_standard, auth_headers):
        aid = published_standard.agent_id
        assert client.get(f"/internal/marketplace/agents/{aid}", headers=auth_headers).status_code == 200
        starters = client.get(f"/internal/marketplace/agents/{aid}/conversation-starters", headers=auth_headers)
        assert [x["prompt"] for x in starters.json()] == ["standard starter"]
        assert client.get(f"/internal/marketplace/agents/{aid}/my-rating", headers=auth_headers).json()["rating"] == 3
        started = client.post(f"/internal/marketplace/agents/{aid}/conversations", headers=auth_headers)
        assert started.status_code == 201
        rated = client.post(f"/internal/marketplace/agents/{aid}/rate", json={"rating": 5}, headers=auth_headers)
        assert rated.status_code == 200

    @pytest.mark.parametrize("path", ["conversation-starters", "my-rating"])
    def test_starters_and_my_rating_do_not_expose_the_internal_agents_profile(
        self, client, db, published_standard, internal_agent, auth_headers, path
    ):
        """The internal agent's profile carries a starter and a rating by this user: neither may be returned
        (a missing agent yields an empty list / null rating)."""
        base = "/internal/marketplace/agents"
        missing = client.get(f"{base}/{MISSING_ID}/{path}", headers=auth_headers)
        hidden = client.get(f"{base}/{internal_agent.agent_id}/{path}", headers=auth_headers)
        assert missing.status_code == hidden.status_code == 200
        assert_same(hidden, missing)
        assert "internal starter" not in hidden.text

    def test_catalog_excludes_internal_agent(self, client, db, published_standard, internal_agent, auth_headers):
        resp = client.get("/internal/marketplace/agents", headers=auth_headers)
        assert resp.status_code == 200
        ids = [a["agent_id"] for a in resp.json()["agents"]]
        assert ids == [published_standard.agent_id]
        assert "__internal_chat__" not in resp.text

    def test_catalog_excludes_internal_agent_even_if_it_looked_published(
        self, client, db, published_standard, exposed, auth_headers
    ):
        db.execute(sa.text('UPDATE "Agent" SET is_tool = false, marketplace_visibility = \'PUBLIC\' '
                           "WHERE agent_id = :a"), {"a": exposed.agent_id})
        db.execute(sa.text('UPDATE "AgentMarketplaceProfile" SET published_at = now() WHERE agent_id = :a'),
                   {"a": exposed.agent_id})
        db.expire_all()
        resp = client.get("/internal/marketplace/agents", headers=auth_headers)
        assert resp.status_code == 200
        assert [a["agent_id"] for a in resp.json()["agents"]] == [published_standard.agent_id]


# ---------------------------------------------------------------------------
# Scheduled tasks
# ---------------------------------------------------------------------------


class TestScheduledTasks:
    def _body(self, agent_id):
        return {
            "name": "task", "agent_id": agent_id, "input": {"message": "hello"},
            "cron_expression": "*/5 * * * *", "timezone": "UTC", "conversation_mode": "new_per_run",
            "max_concurrent_runs": 1,
        }

    @pytest.mark.parametrize("role", ["OWNER", "ADMINISTRATOR", "OMNIADMIN_MEMBER"])
    def test_create_for_internal_agent_matches_unknown_agent(
        self, client, db, fake_app, standard_agent, internal_agent, role_headers, role
    ):
        url = f"/internal/apps/{fake_app.app_id}/scheduled-tasks"
        before = snapshot(db, internal_agent.agent_id)
        tasks_before = db.query(ScheduledTask).count()
        missing = client.post(url, json=self._body(MISSING_ID), headers=role_headers[role])
        hidden = client.post(url, json=self._body(internal_agent.agent_id), headers=role_headers[role])
        assert_same(hidden, missing)
        assert missing.status_code == hidden.status_code == 400, hidden.text
        assert hidden.json() == {"detail": "Agent not found"}
        assert db.query(ScheduledTask).count() == tasks_before
        assert snapshot(db, internal_agent.agent_id) == before

    def test_agent_selector_excludes_internal_agent(self, client, fake_app, standard_agent, internal_agent, owner_headers):
        resp = client.get(f"/internal/apps/{fake_app.app_id}/agents/", headers=owner_headers)
        assert resp.status_code == 200
        ids = [a["agent_id"] for a in resp.json()]
        assert standard_agent.agent_id in ids and internal_agent.agent_id not in ids


# ---------------------------------------------------------------------------
# MCP server (internal management router + JSON-RPC handler)
# ---------------------------------------------------------------------------


class TestMcpServer:
    def _url(self, app, suffix=""):
        return f"/internal/apps/{app.app_id}/mcp-servers{suffix}"

    def _associated(self, db, server_id):
        return sorted(r[0] for r in db.execute(
            sa.text("SELECT agent_id FROM mcp_server_agents WHERE server_id = :s"), {"s": server_id}))

    def test_tool_agents_selector_excludes_hidden(
        self, client, fake_app, standard_agent, hidden, owner_headers
    ):
        resp = client.get(self._url(fake_app, "/tool-agents"), headers=owner_headers)
        assert resp.status_code == 200
        assert "__internal_chat__" not in resp.text
        assert hidden.agent_id not in [a.get("agent_id", a.get("id")) for a in resp.json()]
        assert standard_agent.agent_id in [a.get("agent_id", a.get("id")) for a in resp.json()]

    def test_create_with_hidden_id_is_skipped_like_unknown_id(
        self, client, db, fake_app, standard_agent, hidden, owner_headers
    ):
        before = snapshot(db, hidden.agent_id)
        missing = client.post(self._url(fake_app, "/"), json={"name": "m1", "slug": "m1", "agent_ids": [MISSING_ID]},
                              headers=owner_headers)
        hidden_resp = client.post(self._url(fake_app, "/"),
                             json={"name": "m2", "slug": "m2", "agent_ids": [hidden.agent_id]},
                             headers=owner_headers)
        assert missing.status_code == hidden_resp.status_code == 201
        assert self._associated(db, missing.json()["server_id"]) == []
        assert self._associated(db, hidden_resp.json()["server_id"]) == []
        assert snapshot(db, hidden.agent_id) == before

    def test_update_with_hidden_id_is_skipped_like_unknown_id(
        self, client, db, fake_app, standard_agent, hidden, owner_headers
    ):
        created = client.post(self._url(fake_app, "/"),
                              json={"name": "m3", "slug": "m3", "agent_ids": [standard_agent.agent_id]},
                              headers=owner_headers).json()
        sid = created["server_id"]
        before = snapshot(db, hidden.agent_id)
        resp = client.put(self._url(fake_app, f"/{sid}"),
                          json={"agent_ids": [standard_agent.agent_id, hidden.agent_id, MISSING_ID]},
                          headers=owner_headers)
        assert resp.status_code == 200
        assert self._associated(db, sid) == [standard_agent.agent_id]
        assert snapshot(db, hidden.agent_id) == before

    @pytest.mark.asyncio
    async def test_tools_list_and_call_treat_a_direct_association_as_tool_not_found(
        self, db, fake_app, standard_agent, hidden
    ):
        from mcp_handler import server_handler as module
        from models.mcp_server import MCPServer, MCPServerAgent
        from tests.integration._eos_enforcement_helpers import SessionProxy

        server = MCPServer(name="excl-mcp", slug="excl-mcp", app_id=fake_app.app_id)
        db.add(server)
        db.flush()
        db.add(MCPServerAgent(server_id=server.server_id, agent_id=hidden.agent_id,
                              tool_name_override="internal_tool"))
        db.add(MCPServerAgent(server_id=server.server_id, agent_id=standard_agent.agent_id,
                              tool_name_override="std_tool"))
        db.flush()
        db.refresh(server)
        before = snapshot(db, hidden.agent_id)
        handler = module.MCPServerHandler(server.server_id, server.name, fake_app.app_id)
        execute = AsyncMock(return_value={"response": "ok"})

        with patch.object(module, "SessionLocal", return_value=SessionProxy(db)), \
                patch.object(handler.agent_execution_service, "execute_agent_chat_with_file_refs", execute):
            listed = await handler.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
            hidden_resp = await handler.handle_request({
                "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": "internal_tool", "arguments": {"message": "hi"}}})
            missing = await handler.handle_request({
                "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": "no_such_tool", "arguments": {"message": "hi"}}})

        names = [t["name"] for t in listed["result"]["tools"]]
        assert "internal_tool" not in names and "std_tool" in names
        assert "error" in hidden_resp and hidden_resp["error"]["code"] == missing["error"]["code"]
        assert hidden_resp["error"]["message"] == "Tool not found: internal_tool"
        assert missing["error"]["message"] == "Tool not found: no_such_tool"
        execute.assert_not_called()
        assert snapshot(db, hidden.agent_id) == before


# ---------------------------------------------------------------------------
# A2A (committed world: the router opens its own SessionLocal)
# ---------------------------------------------------------------------------

_A2A_HEADERS = {"A2A-Version": "1.0"}


@pytest.fixture
def a2a_internal_agent(a2a_committed_world):
    """A committed internal chat agent in the A2A world's App (removed with the App by the world cleanup)."""
    from db.database import SessionLocal

    session = SessionLocal()
    try:
        agent = Agent(
            name="__internal_chat__", app_id=a2a_committed_world.app_id, kind=AGENT_KIND_INTERNAL_CHAT,
            has_memory=True, type="agent",
        )
        session.add(agent)
        session.commit()
        return agent.agent_id
    finally:
        session.close()


class TestA2A:
    def _card(self, world, aid):
        return f"/a2a/v1/apps/{world.app_slug}/agents/{aid}/.well-known/agent-card.json"

    def test_card_matches_missing_and_non_enabled_agent(self, client, a2a_committed_world, a2a_internal_agent):
        world = a2a_committed_world
        missing = client.get(self._card(world, MISSING_ID))
        hidden = client.get(self._card(world, a2a_internal_agent))
        disabled = client.get(self._card(world, world.agent_disabled_id))
        assert hidden.status_code == 404
        assert_same(hidden, missing)
        assert_same(hidden, disabled)
        keyed = client.get(self._card(world, a2a_internal_agent), headers={"X-API-KEY": world.key_1_raw})
        assert_same(keyed, client.get(self._card(world, MISSING_ID), headers={"X-API-KEY": world.key_1_raw}))

    def test_catalog_excludes_internal_agent(self, client, a2a_committed_world, a2a_internal_agent):
        world = a2a_committed_world
        for headers in ({}, {"X-API-KEY": world.key_1_raw}):
            resp = client.get(f"/a2a/v1/apps/{world.app_slug}/agents", headers=headers)
            assert resp.status_code == 200
            assert str(a2a_internal_agent) not in json.dumps(resp.json())
            assert "__internal_chat__" not in resp.text

    def test_send_message_matches_missing_agent_and_creates_no_task(
        self, client, a2a_committed_world, a2a_internal_agent
    ):
        from db.database import SessionLocal
        from services.a2a_server.sdk_models import get_sdk_models

        world = a2a_committed_world
        payload = {
            "jsonrpc": "2.0", "id": 1, "method": "SendMessage",
            "params": {"message": {"messageId": "m1", "role": "ROLE_USER", "parts": [{"text": "hi"}]}},
        }

        def counts():
            session = SessionLocal()
            try:
                models = get_sdk_models()
                return (
                    session.query(models.task).count(),
                    session.query(Agent).filter(Agent.app_id == world.app_id).count(),
                    session.execute(sa.text("SELECT count(*) FROM a2a_context_link")).scalar(),
                    session.execute(sa.text('SELECT count(*) FROM "Conversation" WHERE agent_id = :a'),
                                    {"a": a2a_internal_agent}).scalar(),
                )
            finally:
                session.close()

        before = counts()
        url = lambda aid: f"/a2a/v1/apps/{world.app_slug}/agents/{aid}"
        headers = {**_A2A_HEADERS, "X-API-KEY": world.key_1_raw}
        missing = client.post(url(MISSING_ID), json=payload, headers=headers)
        hidden = client.post(url(a2a_internal_agent), json=payload, headers=headers)
        disabled = client.post(url(world.agent_disabled_id), json=payload, headers=headers)
        assert hidden.status_code == 404
        assert_same(hidden, missing)
        assert_same(hidden, disabled)
        assert counts() == before


class TestA2AVisibilityFilter:
    """Repository/service level, with the unexposed CHECK dropped and the agent forced ``a2a_enabled=true``:
    the HTTP tests above cannot tell ``visible_clause()`` from the "agent not enabled" branch, these can
    (the router uses its own committed SessionLocal, so it cannot see the ``db`` fixture's rows)."""

    @pytest.fixture(autouse=True)
    def _a2a_config(self):
        from utils.a2a_config import get_a2a_config

        get_a2a_config.cache_clear()
        yield
        get_a2a_config.cache_clear()

    @pytest.fixture
    def a2a_standard(self, db, standard_agent):
        standard_agent.a2a_enabled = True
        standard_agent.a2a_card_visibility = "public"
        db.flush()
        return standard_agent

    def test_repository_lookup_and_catalog_exclude_the_agent(self, db, fake_app, a2a_standard, exposed):
        from repositories.a2a_agent_repository import get_agent_for_app, list_enabled_agents_for_app

        assert db.query(Agent).filter(Agent.agent_id == exposed.agent_id, Agent.a2a_enabled.is_(True)).count() == 1
        assert get_agent_for_app(db, fake_app.app_id, exposed.agent_id) is None
        assert get_agent_for_app(db, fake_app.app_id, MISSING_ID) is None
        assert get_agent_for_app(db, fake_app.app_id, a2a_standard.agent_id) is not None
        assert [a.agent_id for a in list_enabled_agents_for_app(db, fake_app.app_id)] == [a2a_standard.agent_id]

    def test_visibility_service_resolves_it_like_a_missing_agent(self, db, fake_app, a2a_standard, exposed):
        from services.a2a_server import visibility_service as vis

        missing = vis.resolve(db, fake_app.slug, MISSING_ID)
        hidden = vis.resolve(db, fake_app.slug, exposed.agent_id)
        assert (hidden.outcome, hidden.reason) == (missing.outcome, missing.reason)
        assert hidden.outcome is vis.Outcome.NOT_FOUND and hidden.reason is vis.Reason.AGENT_MISSING
        control = vis.resolve(db, fake_app.slug, a2a_standard.agent_id)
        assert control.outcome is vis.Outcome.VISIBLE
        assert [snap.agent_id for snap in vis.list_visible(db, fake_app.slug)] == [a2a_standard.agent_id]

    def test_context_binding_rejects_it_and_creates_nothing(self, db, fake_app, fake_user, a2a_standard, internal_agent):
        from services.a2a_server import context_binding_service as binding
        from utils.security import hash_api_key

        raw = "k" * 64
        ctx = {"api_key": raw, "app_id": fake_app.app_id}
        before = snapshot(db, internal_agent.agent_id)
        with pytest.raises(binding.A2AContextBindingError) as missing:
            binding.bind_context(db, app_id=fake_app.app_id, agent_id=MISSING_ID, api_key_raw=raw,
                                 context_id="ctx-1", user_context=dict(ctx))
        with pytest.raises(binding.A2AContextBindingError) as hidden:
            binding.bind_context(db, app_id=fake_app.app_id, agent_id=internal_agent.agent_id, api_key_raw=raw,
                                 context_id="ctx-1", user_context=dict(ctx))
        assert str(hidden.value) == str(missing.value)
        assert snapshot(db, internal_agent.agent_id) == before
        assert db.execute(sa.text("SELECT count(*) FROM a2a_context_link WHERE agent_id = :a"),
                          {"a": internal_agent.agent_id}).scalar() == 0
        # Control: a standard agent binds fine with the same arguments.
        ok = binding.bind_context(db, app_id=fake_app.app_id, agent_id=a2a_standard.agent_id, api_key_raw=raw,
                                  context_id="ctx-1", user_context=dict(ctx))
        assert ok.created is True


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


class TestMetrics:
    @pytest.fixture
    def runs(self, db, fake_app, standard_agent, internal_agent):
        import uuid
        from datetime import timedelta
        from models.agent_execution_event import AgentExecutionEvent

        def event(agent, caller, status):
            ev = AgentExecutionEvent(
                event_id=uuid.uuid4(), app_id=fake_app.app_id, agent_id=agent.agent_id, caller_type=caller,
                started_at=datetime.utcnow() - timedelta(minutes=30), duration_ms=100, status=status,
                error_code="Boom" if status == "ERROR" else None,
                error_message="boom happened" if status == "ERROR" else None, llm_calls=1,
                input_tokens=10, output_tokens=5, total_tokens=15,
            )
            db.add(ev)
            return ev

        event(standard_agent, "INTERNAL_PLAYGROUND", "SUCCESS")
        event(internal_agent, "INTERNAL_CHAT", "SUCCESS")
        event(internal_agent, "INTERNAL_CHAT", "SUCCESS")
        event(internal_agent, "INTERNAL_CHAT", "ERROR")
        db.flush()

    @pytest.mark.parametrize("suffix", ["summary", "timeseries", "breakdown/model", "tools", "errors"])
    @pytest.mark.parametrize("role", ["OWNER", "ADMINISTRATOR", "OMNIADMIN_MEMBER"])
    def test_per_agent_endpoints_are_404(
        self, client, fake_app, standard_agent, internal_agent, runs, role_headers, role, suffix
    ):
        url = f"/internal/apps/{fake_app.app_id}/agents/{{aid}}/metrics/{suffix}"
        missing = client.get(url.format(aid=MISSING_ID), headers=role_headers[role])
        hidden = client.get(url.format(aid=internal_agent.agent_id), headers=role_headers[role])
        assert missing.status_code == 404
        assert missing.json() == {"detail": "Agent not found in this app."}
        assert_same(hidden, missing)

    def test_per_agent_endpoint_still_works_for_standard_agent(self, client, fake_app, standard_agent, internal_agent, runs, owner_headers):
        resp = client.get(f"/internal/apps/{fake_app.app_id}/agents/{standard_agent.agent_id}/metrics/summary",
                          headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["current"]["executions"] == 1

    def test_by_agent_breakdown_excludes_internal_agent_but_app_totals_count_its_runs(
        self, client, fake_app, standard_agent, internal_agent, runs, owner_headers
    ):
        base = f"/internal/apps/{fake_app.app_id}/metrics"
        breakdown = client.get(f"{base}/breakdown/agent", headers=owner_headers)
        assert breakdown.status_code == 200
        keys = [i["key"] for i in breakdown.json()["items"]]
        assert str(standard_agent.agent_id) in keys
        assert str(internal_agent.agent_id) not in keys
        assert "__internal_chat__" not in breakdown.text

        # App totals deliberately still count the internal agent's runs (1 standard + 3 internal).
        summary = client.get(f"{base}/summary", headers=owner_headers).json()["current"]
        assert summary["executions"] == 4
        assert summary["errors"] == 1
        assert summary["llm_calls"] == 4

    def test_recent_errors_keep_the_row_but_hide_the_internal_agent(
        self, client, fake_app, standard_agent, internal_agent, runs, owner_headers
    ):
        resp = client.get(f"/internal/apps/{fake_app.app_id}/metrics/errors", headers=owner_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert sum(g["count"] for g in body["groups"]) == 1
        assert len(body["recent"]) == 1
        row = body["recent"][0]
        assert row["agent_id"] is None and row["agent_name"] is None
        assert row["caller_type"] == "INTERNAL_CHAT"
        assert "__internal_chat__" not in resp.text


# ---------------------------------------------------------------------------
# Execution choke point (service level: the routers' own filters answer first over HTTP)
# ---------------------------------------------------------------------------


class TestExecutionChokePoint:
    """``AgentExecutionService._prepare_turn`` rejects an internal agent without a turn config, uniformly
    for every channel. The HTTP routers filter the agent before reaching it, so it is exercised through
    the execution service entry point the routers/MCP/A2A/scheduler all call, against the real DB."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("frozen", [False, True])
    async def test_execute_internal_agent_without_turn_config_is_404_like_missing(
        self, db, fake_app, fake_user, standard_agent, internal_agent, frozen
    ):
        from fastapi import HTTPException
        from services.agent_execution_service import AgentExecutionService

        internal_agent.is_frozen = frozen
        db.flush()
        before = snapshot(db, internal_agent.agent_id)
        ctx = {"user_id": fake_user.user_id, "email": fake_user.email, "app_id": fake_app.app_id, "oauth": True}

        async def run(agent_id):
            with pytest.raises(HTTPException) as exc:
                await AgentExecutionService().execute_agent_chat_with_file_refs(
                    agent_id=agent_id, message="hi", user_context=dict(ctx), db=db)
            return exc.value

        missing, hidden = await run(MISSING_ID), await run(internal_agent.agent_id)
        assert (hidden.status_code, hidden.detail) == (missing.status_code, missing.detail) == (404, "Agent not found")
        assert snapshot(db, internal_agent.agent_id) == before

    @pytest.mark.asyncio
    async def test_streaming_internal_agent_without_turn_config_ends_in_agent_not_found(
        self, db, fake_app, fake_user, standard_agent, internal_agent
    ):
        from services.agent_streaming_service import AgentStreamingService

        ctx = {"user_id": fake_user.user_id, "email": fake_user.email, "app_id": fake_app.app_id, "oauth": True}

        async def collect(agent_id):
            out = []
            try:
                async for chunk in AgentStreamingService().stream_agent_chat(
                    agent_id=agent_id, message="hi", user_context=dict(ctx), db=db,
                ):
                    out.append(chunk)
            except Exception as exc:  # HTTPException raised before the first event is also a rejection
                out.append(f"EXC {getattr(exc, 'status_code', '')} {getattr(exc, 'detail', exc)}")
            return "".join(str(c) for c in out)

        hidden = (await collect(internal_agent.agent_id)).replace(str(internal_agent.agent_id), "X")
        missing = (await collect(MISSING_ID)).replace(str(MISSING_ID), "X")
        # Same wire result as a missing agent (a single generic SSE error event, nothing streamed).
        assert '"type": "error"' in hidden
        assert hidden == missing


# ---------------------------------------------------------------------------
# HITL
# ---------------------------------------------------------------------------


class TestHitl:
    def _approval(self, db, agent, status):
        import uuid
        from datetime import timedelta, timezone
        from models.hitl_approval import HITLApproval

        conv = Conversation(agent_id=agent.agent_id, session_id=f"conv_{agent.agent_id}_{uuid.uuid4()}")
        db.add(conv)
        db.flush()
        now = datetime.now(timezone.utc)
        approval = HITLApproval(
            id=str(uuid.uuid4()), app_id=agent.app_id, agent_id=agent.agent_id, conversation_id=conv.conversation_id,
            thread_id=f"thread_{agent.agent_id}_{conv.session_id}", interrupt_id=uuid.uuid4().hex,
            channel="public_api", status=status, created_at=now, expires_at=now + timedelta(hours=1),
            actions=[{"action_id": "c1", "name": "t", "args": {}, "allowed_decisions": ["approve"]}],
        )
        db.add(approval)
        db.flush()
        return approval

    def test_cancel_pending_for_agents_ignores_internal_agent_and_warns(
        self, db, standard_agent, internal_agent, caplog
    ):
        from services import hitl_approval_service as svc

        internal_approval = self._approval(db, internal_agent, "pending")
        standard_approval = self._approval(db, standard_agent, "pending")
        svc.logger.addHandler(caplog.handler)
        caplog.set_level(logging.DEBUG)
        try:
            cancelled = svc.cancel_pending_for_agents(db, [internal_agent.agent_id], "approval_rules_changed")
        finally:
            svc.logger.removeHandler(caplog.handler)
        db.refresh(internal_approval)
        assert cancelled == 0
        assert internal_approval.status == "pending" and internal_approval.resolution_reason is None
        assert any(r.levelno == logging.WARNING and "internal chat agent" in r.getMessage() for r in caplog.records)

        # A mixed list still cancels the standard agent's approval only.
        assert svc.cancel_pending_for_agents(
            db, [internal_agent.agent_id, standard_agent.agent_id], "approval_rules_changed") == 1
        db.refresh(internal_approval)
        db.refresh(standard_approval)
        assert internal_approval.status == "pending"
        assert standard_approval.status == "cancelled"

    @pytest.mark.asyncio
    async def test_resume_against_unavailable_agent_ends_cancelled_not_pending(
        self, db, fake_app, fake_user, standard_agent, internal_agent
    ):
        from fastapi import HTTPException
        from models.hitl_approval import ApprovalChannel
        from services import hitl_approval_service as approvals
        from services.agent_execution_service import AgentExecutionService

        approval = self._approval(db, internal_agent, "deciding")
        resume = approvals.ResumeRequest(
            approval=approval, decisions=[{"type": "approve"}], final_status=approvals.ApprovalStatus.APPROVED)
        ctx = {"user_id": fake_user.user_id, "email": fake_user.email, "app_id": fake_app.app_id, "oauth": True}

        with pytest.raises(HTTPException) as exc:
            await AgentExecutionService().resume_approval(db, resume, ctx, ApprovalChannel.PUBLIC_API)
        assert exc.value.status_code == 404
        db.refresh(approval)
        assert approval.status == "cancelled"
        assert approval.resolution_reason == "agent_unavailable"


# ---------------------------------------------------------------------------
# Quota, freeze, export/import, "used by", delete App
# ---------------------------------------------------------------------------


class TestTierLimitAndFreeze:
    @pytest.fixture
    def limits(self, db):
        from models.tier_config import TierConfig

        def set_limit(tier, resource, value):
            row = db.query(TierConfig).filter(TierConfig.tier == tier, TierConfig.resource_type == resource).first()
            if row:
                row.limit_value = value
            else:
                db.add(TierConfig(tier=tier, resource_type=resource, limit_value=value))
            db.flush()

        return set_limit

    def test_internal_agent_does_not_count_against_the_agent_limit(
        self, db, fake_app, fake_ai_service, standard_agent, internal_agent, limits, monkeypatch
    ):
        from fastapi import HTTPException
        import services.tier_enforcement_service as tes

        monkeypatch.setattr(tes, "is_self_managed", lambda: False)
        configure_factories(db)
        AgentFactory(app=fake_app, ai_service=fake_ai_service, name="Second standard")
        limits("free", "agents", 2)  # = number of standard agents

        with pytest.raises(HTTPException) as exc:
            tes.TierEnforcementService.check_resource_limit(db, fake_app.app_id, "agents")
        assert exc.value.status_code == 403
        assert "(2/2)" in exc.value.detail  # the internal agent is not the third

        limits("free", "agents", 3)  # one free slot: still free even though the internal agent exists
        tes.TierEnforcementService.check_resource_limit(db, fake_app.app_id, "agents")

    def test_internal_agent_is_not_counted_when_the_tenant_is_exactly_at_the_limit(
        self, db, fake_app, fake_ai_service, standard_agent, limits, monkeypatch
    ):
        import services.tier_enforcement_service as tes

        monkeypatch.setattr(tes, "is_self_managed", lambda: False)
        limits("free", "agents", 1)  # at limit with the standard agent alone
        db.add(Agent(name="__internal_chat__", app_id=fake_app.app_id, kind=AGENT_KIND_INTERNAL_CHAT))
        db.flush()
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            tes.TierEnforcementService.check_resource_limit(db, fake_app.app_id, "agents")
        assert "(1/1)" in exc.value.detail

    def test_downgrade_freeze_does_not_freeze_the_internal_agent(
        self, db, fake_app, fake_user, fake_ai_service, standard_agent, limits
    ):
        from datetime import timedelta
        from services.freeze_service import FreezeService

        configure_factories(db)
        second = AgentFactory(app=fake_app, ai_service=fake_ai_service, name="Second standard")
        internal = Agent(name="__internal_chat__", app_id=fake_app.app_id, kind=AGENT_KIND_INTERNAL_CHAT)
        db.add(internal)
        db.flush()
        standard_agent.create_date = datetime(2025, 1, 1)
        second.create_date = datetime(2025, 1, 2)
        internal.create_date = datetime(2025, 1, 3)  # newest: would take the free slot if it counted
        limits("free", "apps", -1)
        limits("free", "agents", 1)

        FreezeService.apply_freeze(db, fake_user.user_id, "free")
        db.flush()
        db.refresh(internal)
        db.refresh(standard_agent)
        db.refresh(second)
        assert internal.is_frozen is False
        assert (standard_agent.is_frozen, second.is_frozen) == (True, False)


class TestExportImport:
    def test_full_app_export_does_not_contain_internal_agent(
        self, db, fake_app, fake_user, standard_agent, internal_agent
    ):
        from services.full_app_export_service import FullAppExportService

        export = FullAppExportService(db).export_full_app(fake_app.app_id, user_id=fake_user.user_id)
        names = [a.name for a in export.agents]
        assert "Standard Agent" in names
        assert "__internal_chat__" not in names
        assert len(export.agents) == 1

    def test_importing_an_agent_named_like_the_internal_one_creates_a_standard_agent(
        self, client, db, fake_app, fake_ai_service, standard_agent, internal_agent, owner_headers
    ):
        base = _agents_base(fake_app)
        exported = client.post(f"{base}/{standard_agent.agent_id}/export", headers=owner_headers)
        assert exported.status_code == 200, exported.text
        payload = exported.json()
        payload["agent"]["name"] = "__internal_chat__"
        before = snapshot(db, internal_agent.agent_id)

        resp = client.post(
            f"{base}/import", headers=owner_headers,
            params={"selected_ai_service_id": fake_ai_service.service_id},
            files={"file": ("agent.json", json.dumps(payload).encode(), "application/json")},
        )
        assert resp.status_code == 201, resp.text
        same_name = db.query(Agent).filter(Agent.app_id == fake_app.app_id, Agent.name == "__internal_chat__").all()
        assert sorted(a.kind for a in same_name) == ["internal_chat", "standard"]
        assert internal_agent.kind == AGENT_KIND_INTERNAL_CHAT
        assert snapshot(db, internal_agent.agent_id) == before
        listed = client.get(base + "/", headers=owner_headers).json()
        assert [a["agent_id"] for a in listed if a["name"] == "__internal_chat__"] != []
        assert internal_agent.agent_id not in [a["agent_id"] for a in listed]


    def _export_payload(self, client, fake_app, agent, headers, name):
        exported = client.post(f"{_agents_base(fake_app)}/{agent.agent_id}/export", headers=headers)
        assert exported.status_code == 200, exported.text
        payload = exported.json()
        payload["agent"]["name"] = name
        return payload

    def _import(self, client, fake_app, headers, payload, ai_service, **params):
        return client.post(
            f"{_agents_base(fake_app)}/import", headers=headers,
            params={"selected_ai_service_id": ai_service.service_id, **params},
            files={"file": ("agent.json", json.dumps(payload).encode(), "application/json")},
        )

    def test_override_by_name_never_picks_the_internal_agent(
        self, client, db, fake_app, fake_ai_service, standard_agent, internal_agent, owner_headers
    ):
        """Case 1: no standard agent has that name -> a new standard agent, the internal row is untouched."""
        payload = self._export_payload(client, fake_app, standard_agent, owner_headers, "__internal_chat__")
        payload["agent"]["system_prompt"] = "OVERWRITTEN"
        before = snapshot(db, internal_agent.agent_id)
        resp = self._import(client, fake_app, owner_headers, payload, fake_ai_service, conflict_mode="override")
        assert resp.status_code == 201, resp.text
        db.refresh(internal_agent)
        assert internal_agent.system_prompt == "" and internal_agent.kind == AGENT_KIND_INTERNAL_CHAT
        assert snapshot(db, internal_agent.agent_id) == before
        created = db.query(Agent).filter(Agent.app_id == fake_app.app_id, Agent.name == "__internal_chat__",
                                         Agent.kind == "standard").all()
        assert len(created) == 1 and created[0].system_prompt == "OVERWRITTEN"

        # Case 2: a standard agent with that name now exists -> OVERRIDE updates it, still not the internal one.
        payload["agent"]["system_prompt"] = "OVERWRITTEN AGAIN"
        resp = self._import(client, fake_app, owner_headers, payload, fake_ai_service, conflict_mode="override")
        assert resp.status_code == 201, resp.text
        db.refresh(created[0])
        db.refresh(internal_agent)
        assert created[0].system_prompt == "OVERWRITTEN AGAIN"
        assert internal_agent.system_prompt == ""
        assert snapshot(db, internal_agent.agent_id) == before
        assert db.query(Agent).filter(Agent.app_id == fake_app.app_id, Agent.name == "__internal_chat__").count() == 2

    def test_tool_reference_by_name_never_attaches_the_internal_agent(
        self, client, db, fake_app, fake_ai_service, standard_agent, internal_agent, owner_headers
    ):
        payload = self._export_payload(client, fake_app, standard_agent, owner_headers, "Importer")
        payload["agent"]["agent_tool_refs"] = [{"tool_agent_name": "__internal_chat__"}]
        payload["agent_tools"] = []
        before = snapshot(db, internal_agent.agent_id)
        resp = self._import(client, fake_app, owner_headers, payload, fake_ai_service,
                            import_bundled_agent_tools="false")
        assert resp.status_code == 201, resp.text
        importer = db.query(Agent).filter(Agent.app_id == fake_app.app_id, Agent.name == "Importer").one()
        tools = db.execute(sa.text("SELECT tool_id FROM agent_tools WHERE agent_id = :a"),
                           {"a": importer.agent_id}).fetchall()
        assert tools == []
        assert snapshot(db, internal_agent.agent_id) == before

        # Control: the same import referencing a standard tool agent by name does attach it.
        payload["agent"]["name"] = "Importer 2"
        payload["agent"]["agent_tool_refs"] = [{"tool_agent_name": "Standard Agent"}]
        resp = self._import(client, fake_app, owner_headers, payload, fake_ai_service,
                            import_bundled_agent_tools="false")
        assert resp.status_code == 201, resp.text
        importer2 = db.query(Agent).filter(Agent.app_id == fake_app.app_id, Agent.name == "Importer 2").one()
        assert [r[0] for r in db.execute(sa.text("SELECT tool_id FROM agent_tools WHERE agent_id = :a"),
                                         {"a": importer2.agent_id})] == [standard_agent.agent_id]


class TestServiceUsage:
    def test_used_by_and_move_agents_ignore_the_internal_agent(
        self, client, db, fake_app, fake_ai_service, standard_agent, internal_agent, owner_headers
    ):
        # Even if its service_id were set (it is NULL by design), the agent must not show up or move.
        internal_agent.service_id = fake_ai_service.service_id
        db.flush()
        base = f"/internal/apps/{fake_app.app_id}/ai-services/{fake_ai_service.service_id}"
        used = client.get(f"{base}/used-by", headers=owner_headers)
        assert used.status_code == 200, used.text
        assert "__internal_chat__" not in used.text
        assert str(standard_agent.name) in used.text

        target = AIServiceFactory(app=fake_app, name="target-svc")
        db.flush()
        moved = client.post(f"{base}/move-agents", headers=owner_headers,
                            json={"target_service_id": target.service_id, "expected_count": 1})
        assert moved.status_code == 200, moved.text
        db.refresh(internal_agent)
        db.refresh(standard_agent)
        assert internal_agent.service_id == fake_ai_service.service_id
        assert standard_agent.service_id == target.service_id


class TestServiceUsageEveryReference:
    """"Used by" and bulk moves of AI and sandbox services, with every reference the internal agent could hold
    forced on (service, sandbox, middleware, scheduled task): none of them may list or move it."""

    @pytest.fixture
    def world(self, db, fake_app, fake_user, fake_ai_service, standard_agent, internal_agent):
        from models.middleware import AgentMiddleware
        from tests.factories import SandboxServiceFactory
        from tests.integration.routers.internal._eos_helpers import (
            attach_middleware, make_summarization_middleware, make_task)

        configure_factories(db)
        sandbox = SandboxServiceFactory(app=fake_app)
        for agent in (standard_agent, internal_agent):
            agent.service_id = fake_ai_service.service_id
            agent.sandbox_service_id = sandbox.service_id
        db.flush()
        middleware = make_summarization_middleware(db, fake_app, fake_ai_service)
        attach_middleware(db, standard_agent, middleware)
        db.query(AgentMiddleware).filter(AgentMiddleware.agent_id == internal_agent.agent_id).delete()
        attach_middleware(db, internal_agent, middleware)
        std_task = make_task(db, fake_app, standard_agent, fake_user.user_id)
        # the fixture's own scheduled task of the internal agent is the one that must stay out
        internal_task = db.query(ScheduledTask).filter(ScheduledTask.agent_id == internal_agent.agent_id).one()
        return {"sandbox": sandbox, "middleware": middleware, "std_task": std_task, "internal_task": internal_task}

    def _agent_ids(self, usage):
        return sorted(a["agent_id"] for a in usage["agents"])

    def test_ai_service_used_by_lists_only_standard_agents_tasks_and_middleware_attachments(
        self, client, fake_app, fake_ai_service, standard_agent, internal_agent, world, owner_headers
    ):
        url = f"/internal/apps/{fake_app.app_id}/ai-services/{fake_ai_service.service_id}/used-by"
        usage = client.get(url, headers=owner_headers).json()
        assert self._agent_ids(usage) == [standard_agent.agent_id]
        assert [t["agent_id"] for t in usage["scheduled_tasks"]] == [standard_agent.agent_id]
        assert [m["agent_ids"] for m in usage["middlewares"]] == [[standard_agent.agent_id]]
        assert "__internal_chat__" not in json.dumps(usage)

    def test_sandbox_service_used_by_and_move_usage_ignore_the_internal_agent(
        self, client, db, fake_app, standard_agent, internal_agent, world, owner_headers
    ):
        from tests.factories import SandboxServiceFactory

        sandbox = world["sandbox"]
        base = f"/internal/apps/{fake_app.app_id}/sandbox-services/{sandbox.service_id}"
        usage = client.get(f"{base}/used-by", headers=owner_headers)
        assert usage.status_code == 200, usage.text
        usage = usage.json()
        assert self._agent_ids(usage) == [standard_agent.agent_id]
        assert [t["agent_id"] for t in usage["scheduled_tasks"]] == [standard_agent.agent_id]
        assert "__internal_chat__" not in json.dumps(usage)

        target = SandboxServiceFactory(app=fake_app, name="sb-target")
        db.flush()
        moved = client.post(f"{base}/move-usage", headers=owner_headers,
                            json={"target_service_id": target.service_id, "expected_agent_count": 1,
                                  "expected_app_count": 0})
        assert moved.status_code == 200, moved.text
        db.refresh(standard_agent)
        db.refresh(internal_agent)
        assert standard_agent.sandbox_service_id == target.service_id
        assert internal_agent.sandbox_service_id == sandbox.service_id


class TestSystemStats:
    def test_total_agents_excludes_internal_agents(self, client, db, fake_user, standard_agent, internal_agent, monkeypatch):
        from utils.local_auth_tokens import mint_access_token

        monkeypatch.setenv("AICT_OMNIADMINS", fake_user.email)
        db.flush()
        token, _ = mint_access_token(fake_user.user_id, fake_user.email, fake_user.name)
        resp = client.get("/internal/admin/stats", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, resp.text
        total = resp.json()["total_agents"]
        assert total == db.query(Agent).filter(Agent.kind == "standard").count()
        assert total < db.query(Agent).count()  # the internal agent exists and is not counted


class TestAgentToolRuntimeGuards:
    """backend/tools/agentTools.py skips an internal agent referenced as a tool, at the three places that walk
    ``tool_associations`` (root ``create_agent``, ``IACTTool`` and ``IACTOCRTool`` sub-agent builds). The
    ``agent_tools`` row is inserted directly: the FK allows it even though the API never creates one."""

    @pytest.fixture
    def parents(self, db, fake_app, fake_ai_service, standard_agent, internal_agent):
        from models.ocr_agent import OCRAgent

        configure_factories(db)
        other_tool = AgentFactory(app=fake_app, ai_service=fake_ai_service, name="Other tool", is_tool=True)
        ocr = OCRAgent(name="ocr parent", description="", app_id=fake_app.app_id, service_id=fake_ai_service.service_id,
                       vision_service_id=fake_ai_service.service_id, system_prompt="", has_memory=False,
                       temperature=0.7)
        db.add(ocr)
        db.flush()
        # The OCR parent only gets the internal agent: `IACTOCRTool._build` references an undefined
        # `caller_filter` when it recurses into a real nested tool (pre-existing on the base branch, reported).
        for parent, tools in ((standard_agent, (internal_agent, other_tool)), (ocr, (internal_agent,))):
            for tool in tools:
                db.execute(sa.text("INSERT INTO agent_tools (agent_id, tool_id) VALUES (:a, :t)"),
                           {"a": parent.agent_id, "t": tool.agent_id})
        db.flush()
        db.expire_all()
        return {"standard": standard_agent, "ocr": ocr, "other_tool": other_tool}

    @pytest.fixture
    def harness(self, monkeypatch, caplog):
        import tools.agentTools as agent_tools
        from langchain_core.tools import StructuredTool

        discovered = []

        async def fake_discover(sub_agent, **kwargs):
            discovered.append(sub_agent.agent_id)
            return StructuredTool.from_function(func=lambda q="": "x", name=f"tool_{sub_agent.agent_id}",
                                                description="d")

        client = MagicMock()
        client.get_client = AsyncMock(return_value=None)
        monkeypatch.setattr(agent_tools, "discover_tool", fake_discover)
        monkeypatch.setattr(agent_tools, "MCPClientManager", MagicMock(return_value=client))
        monkeypatch.setattr(agent_tools, "create_langchain_agent", MagicMock(return_value=MagicMock()))
        monkeypatch.setattr(agent_tools, "_resolve_skills_for_prompt", AsyncMock(return_value=(None, None)))
        monkeypatch.setattr("tools.aiServiceTools.create_llm_from_service", lambda *a, **k: MagicMock())
        monkeypatch.setattr("tools.middleware.factory.build_agent_middlewares", lambda *a, **k: [])
        agent_tools.logger.addHandler(caplog.handler)
        caplog.set_level(logging.DEBUG)
        yield discovered
        agent_tools.logger.removeHandler(caplog.handler)

    def _assert_skipped(self, discovered, parents, internal_agent, caplog, expected):
        assert discovered == expected
        errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
        assert any(f"Skipping internal chat agent {internal_agent.agent_id}" in m for m in errors), errors

    @pytest.mark.asyncio
    async def test_root_create_agent_skips_it(self, parents, internal_agent, harness, caplog):
        import tools.agentTools as agent_tools

        await agent_tools.create_agent(parents["standard"], session_id=None)
        self._assert_skipped(harness, parents, internal_agent, caplog, [parents["other_tool"].agent_id])

    @pytest.mark.asyncio
    async def test_agent_as_tool_build_skips_it(self, parents, internal_agent, harness, caplog):
        import tools.agentTools as agent_tools

        await agent_tools.IACTTool.create(parents["standard"], user_context={"app_id": 1})
        self._assert_skipped(harness, parents, internal_agent, caplog, [parents["other_tool"].agent_id])

    @pytest.mark.asyncio
    async def test_ocr_agent_as_tool_build_skips_it(self, parents, internal_agent, harness, caplog):
        import tools.agentTools as agent_tools

        await agent_tools.IACTOCRTool.create(parents["ocr"], user_context={"app_id": 1})
        self._assert_skipped(harness, parents, internal_agent, caplog, [])


class TestDeleteApp:
    def test_delete_app_removes_internal_agent_and_its_conversations(
        self, db, fake_app, standard_agent, internal_agent
    ):
        from services.app_service import AppService

        aid = internal_agent.agent_id
        app_id = fake_app.app_id
        assert db.query(Conversation).filter(Conversation.agent_id == aid).count() == 2

        assert AppService(db).delete_app(app_id) is True
        db.flush()
        db.expire_all()
        assert db.query(Agent).filter(Agent.app_id == app_id).count() == 0
        assert db.query(Conversation).filter(Conversation.agent_id == aid).count() == 0
        assert db.query(App).filter(App.app_id == app_id).count() == 0


# ---------------------------------------------------------------------------
# Platform chatbot / OCR (agent-id taking endpoints)
# ---------------------------------------------------------------------------


class TestOcrAndPlatformChatbot:
    def test_internal_ocr_endpoint_matches_missing_agent(
        self, client, db, fake_app, fake_ai_service, standard_agent, internal_agent, owner_headers, exec_mocks
    ):
        from models.ocr_agent import OCRAgent

        ocr_agent = OCRAgent(
            name="ocr", description="", app_id=fake_app.app_id, service_id=fake_ai_service.service_id,
            vision_service_id=fake_ai_service.service_id, system_prompt="", has_memory=False, temperature=0.7)
        db.add(ocr_agent)
        db.flush()
        url = f"/internal/apps/{fake_app.app_id}/ocr/{{aid}}/process"
        files = {"pdf_file": ("a.pdf", b"%PDF-1.4", "application/pdf")}
        before = snapshot(db, internal_agent.agent_id)

        missing = client.post(url.format(aid=MISSING_ID), headers=owner_headers, files=files)
        hidden = client.post(url.format(aid=internal_agent.agent_id), headers=owner_headers, files=files)
        assert missing.status_code == 404, missing.text
        assert_same(hidden, missing)
        assert not exec_mocks.ocr.called
        assert snapshot(db, internal_agent.agent_id) == before

        control = client.post(url.format(aid=ocr_agent.agent_id), headers=owner_headers, files=files)
        assert control.status_code == 200, control.text
        assert exec_mocks.ocr.called

    # ---- platform chatbot: the agent id comes from the `platform_chatbot_agent_id` system setting ----

    @pytest.fixture
    def configured(self, monkeypatch):
        """Point the platform chatbot at a given agent id."""
        def point_to(agent_id):
            monkeypatch.setattr("routers.internal.platform_chatbot._get_agent_id", lambda db: agent_id)
        return point_to

    def test_chatbot_configured_with_internal_agent_behaves_like_an_unknown_agent(
        self, client, db, standard_agent, internal_agent, auth_headers, configured, exec_mocks
    ):
        before = snapshot(db, internal_agent.agent_id)
        results = {}
        for label, agent_id in (("missing", MISSING_ID), ("hidden", internal_agent.agent_id)):
            configured(agent_id)
            results[label] = (
                client.get("/internal/platform-chatbot/config", headers=auth_headers),
                client.post("/internal/platform-chatbot/chat", json={"message": "hi", "session_id": "s"},
                            headers=auth_headers),
                client.post("/internal/platform-chatbot/chat/stream", json={"message": "hi", "session_id": "s"},
                            headers=auth_headers),
            )
        for hidden, missing in zip(results["hidden"], results["missing"]):
            assert_same(hidden, missing)
        assert results["hidden"][0].json()["enabled"] is False
        assert results["hidden"][1].status_code == 404 and results["hidden"][2].status_code == 404
        assert not exec_mocks.executed()
        assert snapshot(db, internal_agent.agent_id) == before

        configured(standard_agent.agent_id)  # control: a standard agent is served
        assert client.get("/internal/platform-chatbot/config", headers=auth_headers).json()["enabled"] is True
        assert client.post("/internal/platform-chatbot/chat", json={"message": "hi", "session_id": "s"},
                           headers=auth_headers).status_code == 200
        assert exec_mocks.chat.called

    def test_admin_setting_pointing_at_the_internal_agent_behaves_like_an_unknown_id(
        self, client, db, fake_user, standard_agent, internal_agent, monkeypatch, exec_mocks
    ):
        from utils.local_auth_tokens import mint_access_token

        monkeypatch.setenv("AICT_OMNIADMINS", fake_user.email)
        db.flush()
        token, _ = mint_access_token(fake_user.user_id, fake_user.email, fake_user.name)
        headers = {"Authorization": f"Bearer {token}"}
        outcomes = {}
        for label, agent_id in (("missing", MISSING_ID), ("hidden", internal_agent.agent_id)):
            put = client.put("/internal/admin/settings/platform_chatbot_agent_id",
                             json={"value": str(agent_id)}, headers=headers)
            chat = client.post("/internal/platform-chatbot/chat", json={"message": "hi", "session_id": "s"},
                               headers=headers)
            config = client.get("/internal/platform-chatbot/config", headers=headers)
            outcomes[label] = (put, chat, config)
        assert outcomes["hidden"][0].status_code == outcomes["missing"][0].status_code
        assert_same(outcomes["hidden"][1], outcomes["missing"][1])
        assert_same(outcomes["hidden"][2], outcomes["missing"][2])
        assert outcomes["hidden"][2].json()["enabled"] is False
        assert not exec_mocks.executed()


# ---------------------------------------------------------------------------
# DB CHECK constraints (AD-1)
# ---------------------------------------------------------------------------


class TestDbConstraints:
    @pytest.mark.parametrize("assignment", [
        "is_tool = true",
        "a2a_enabled = true",
        "marketplace_visibility = 'PUBLIC'",
        "marketplace_visibility = 'PRIVATE'",
        "enable_code_interpreter = true",
    ])
    def test_internal_agent_cannot_be_exposed(self, db, internal_agent, assignment):
        db.flush()
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.execute(sa.text(f'UPDATE "Agent" SET {assignment} WHERE agent_id = :a'),
                           {"a": internal_agent.agent_id})

    def test_orm_update_of_is_tool_is_rejected(self, db, internal_agent):
        internal_agent.is_tool = True
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    def test_second_internal_agent_in_the_same_app_is_rejected(self, db, fake_app, internal_agent):
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.add(Agent(name="__internal_chat__ 2", app_id=fake_app.app_id, kind=AGENT_KIND_INTERNAL_CHAT))
                db.flush()

    def test_internal_agent_in_another_app_is_allowed(self, db, internal_agent):
        from tests.factories import AppFactory

        configure_factories(db)
        other = AppFactory()
        db.add(Agent(name="__internal_chat__", app_id=other.app_id, kind=AGENT_KIND_INTERNAL_CHAT))
        db.flush()
        kinds = db.query(Agent.kind).filter(Agent.app_id.in_([internal_agent.app_id, other.app_id])).all()
        assert sorted(k for (k,) in kinds if k == AGENT_KIND_INTERNAL_CHAT) == [AGENT_KIND_INTERNAL_CHAT] * 2
        assert db.query(Agent).filter(Agent.app_id == other.app_id, Agent.kind == AGENT_KIND_INTERNAL_CHAT).count() == 1

    def test_unexposed_check_is_in_place(self, db):
        """Guards that the ``exposed`` fixture's transactional DROP CONSTRAINT never leaks to other tests."""
        names = {r[0] for r in db.execute(sa.text(
            "SELECT conname FROM pg_constraint WHERE conrelid = '\"Agent\"'::regclass"))}
        assert {"ck_agent_internal_chat_unexposed", "ck_agent_internal_chat_has_app", "ck_agent_kind"} <= names
