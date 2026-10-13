"""AgentService.create_or_update_agent for System One agents (repositories mocked: no database)."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from models.agent import Agent
from models.system_one_agent import SystemOneAgent
from services.agent_service import AgentService

QUESTIONS = [
    {"key": "urgent", "type": "noul", "instructions": "Is this urgent?"},
    {"key": "area", "type": "choice", "instructions": "Which area?",
     "criteria": [{"key": "billing"}, {"key": "tech"}], "min_probability": 0.6},
]


def data(**kw):
    base = {"agent_id": 0, "app_id": 1, "name": "Triage", "description": "d", "is_tool": True,
            "system_one_service_id": 7, "questions": QUESTIONS, "summarization_service_id": None,
            "max_state_chars": 6000,
            # fields a normal form would send; they must be neutralized for this type
            "service_id": 99, "has_memory": True, "silo_id": 5, "output_parser_id": 3,
            "enable_code_interpreter": True, "sandbox_service_id": None, "temperature": 0.7}
    return {**base, **kw}


@pytest.fixture
def repos(mocker):
    created = {}

    def create(db, agent):
        agent.agent_id = 42
        created["agent"] = agent
        return agent

    # Upstream's ownership check of referenced ids is not what these tests are about (they send stray ids on purpose).
    mocker.patch.object(AgentService, "_validate_referenced_resource_ids")
    r = SimpleNamespace(
        created=created,
        by_type=mocker.patch("services.agent_service.AgentRepository.get_agent_by_id_and_type", return_value=None),
        get_by_id=mocker.patch("services.agent_service.AgentRepository.get_by_id", return_value=None),
        create=mocker.patch("services.agent_service.AgentRepository.create", side_effect=create),
        update=mocker.patch("services.agent_service.AgentRepository.update", side_effect=lambda db, a: a),
        so_service=mocker.patch("services.agent_service.SystemOneServiceRepository.get_by_id_and_app_id",
                                return_value=MagicMock(service_id=7, app_id=1)),
        ai_services=mocker.patch("services.agent_service.AgentRepository.get_ai_services_by_app_id",
                                 return_value=[MagicMock(service_id=11, app_id=1), MagicMock(service_id=12, app_id=None)]),
    )
    return r


def run(repos, payload, agent_type="system_one_agent"):
    return AgentService().create_or_update_agent(MagicMock(), payload, agent_type)


def test_creates_a_system_one_agent_with_its_fields(repos):
    assert run(repos, data()) == 42
    agent = repos.created["agent"]
    assert isinstance(agent, SystemOneAgent) and agent.type == "system_one_agent"
    assert agent.system_one_service_id == 7 and agent.max_state_chars == 6000 and agent.is_tool is True
    assert [q["key"] for q in agent.questions] == ["urgent", "area"]
    assert agent.questions[0]["threshold"] == 0.5 and agent.questions[1]["min_probability"] == 0.6
    repos.so_service.assert_called_once()
    assert repos.so_service.call_args[0][1:] == (7, 1)          # looked up in the agent's own app


def test_columns_that_do_not_apply_are_neutralized(repos):
    run(repos, data())
    a = repos.created["agent"]
    assert (a.service_id, a.silo_id, a.output_parser_id, a.sandbox_service_id) == (None, None, None, None)
    assert a.has_memory is False and a.enable_code_interpreter is False and a.skill_router_enabled is False
    assert a.server_tools == []


@pytest.mark.parametrize("missing", ["system_one_service_id", "questions"])
def test_service_and_questions_are_required_on_create(repos, missing):
    with pytest.raises(ValueError, match=missing):
        run(repos, data(**{missing: None}))
    repos.create.assert_not_called()


def test_service_of_another_app_or_unknown_is_rejected(repos):
    repos.so_service.return_value = None
    with pytest.raises(ValueError, match="System One service"):
        run(repos, data())
    repos.create.assert_not_called()


def test_summarization_llm_must_belong_to_the_app_not_be_a_platform_one(repos):
    """A platform-level (app_id NULL) LLM would bypass the SaaS usage metering the chat path applies to it."""
    run(repos, data(summarization_service_id=11))                       # the app's own
    assert repos.created["agent"].summarization_service_id == 11
    for foreign in (12, 999):                                           # platform-level, or another app's
        with pytest.raises(ValueError, match="summarization"):
            run(repos, data(summarization_service_id=foreign))
    run(repos, data(summarization_service_id=None))
    assert repos.created["agent"].summarization_service_id is None


@pytest.mark.parametrize("bad,match", [
    ([{"key": "a", "type": "noul", "instructions": "q"}, {"key": "a", "type": "noul", "instructions": "q"}], "duplicate"),
    ([], "questions"),
    ([{"key": "Bad Key", "type": "noul", "instructions": "q"}], "key"),
    ([{"key": "a", "type": "choice", "instructions": "q", "criteria": [{"key": "only"}]}], "criteria"),
])
def test_invalid_questions_are_rejected_with_a_readable_message(repos, bad, match):
    with pytest.raises(ValueError, match=match):
        run(repos, data(questions=bad))


@pytest.mark.parametrize("value", [0, 499, -5])
def test_max_state_chars_below_the_minimum_is_rejected(repos, value):
    with pytest.raises(ValueError, match="max_state_chars"):
        run(repos, data(max_state_chars=value))


def test_partial_update_keeps_what_is_not_sent(repos):
    existing = SystemOneAgent()
    existing.agent_id = 5
    existing.app_id = 1
    existing.type = "system_one_agent"
    existing.system_one_service_id = 7
    existing.questions = QUESTIONS
    existing.max_state_chars = 3000
    repos.by_type.return_value = existing
    repos.get_by_id.return_value = existing
    payload = data(agent_id=5)
    for key in ("system_one_service_id", "questions", "max_state_chars", "summarization_service_id"):
        payload.pop(key)
    run(repos, payload)
    assert existing.system_one_service_id == 7 and existing.questions == QUESTIONS and existing.max_state_chars == 3000
    repos.update.assert_called_once()


def test_update_can_replace_the_questions(repos):
    existing = SystemOneAgent()
    existing.agent_id = 5
    existing.app_id = 1
    existing.type = "system_one_agent"
    existing.system_one_service_id = 7
    existing.questions = QUESTIONS
    repos.by_type.return_value = existing
    repos.get_by_id.return_value = existing
    run(repos, data(agent_id=5, questions=[{"key": "only", "type": "noul", "instructions": "q"}]))
    assert [q["key"] for q in existing.questions] == ["only"]


@pytest.mark.parametrize("existing_type,requested", [("agent", "system_one_agent"), ("system_one_agent", "agent"),
                                                      ("ocr_agent", "system_one_agent")])
def test_the_type_of_an_existing_agent_cannot_be_changed(repos, existing_type, requested):
    existing = Agent()
    existing.agent_id = 5
    existing.app_id = 1
    existing.type = existing_type
    repos.get_by_id.return_value = existing
    with pytest.raises(ValueError, match="type"):
        run(repos, data(agent_id=5), agent_type=requested)
    repos.create.assert_not_called()
    repos.update.assert_not_called()



def test_a_question_must_leave_room_for_the_text_in_the_prompt_budget(repos):
    # The server counts the text PLUS one question per prompt; max_state_chars is that per-prompt budget.
    long_question = {"key": "u", "type": "noul", "instructions": "x" * 5600}
    with pytest.raises(ValueError, match="needs at least 500"):
        run(repos, data(questions=[long_question], max_state_chars=6000))


def test_the_same_question_is_fine_with_a_bigger_budget(repos):
    long_question = {"key": "u", "type": "noul", "instructions": "x" * 5600}
    assert run(repos, data(questions=[long_question], max_state_chars=12000)) == 42


def test_raising_the_questions_on_update_is_checked_against_the_stored_budget(repos):
    existing = SystemOneAgent(agent_id=42, app_id=1, name="Triage", system_one_service_id=7, max_state_chars=6000,
                              questions=QUESTIONS, is_tool=True)
    repos.by_type.return_value = existing
    long_question = {"key": "u", "type": "noul", "instructions": "x" * 5600}
    with pytest.raises(ValueError, match="needs at least 500"):
        run(repos, data(agent_id=42, questions=[long_question], max_state_chars=None))


@pytest.mark.parametrize("value", [20001, 50000])
def test_there_is_no_upper_limit_on_the_text_length_the_server_enforces_its_own_budget(repos, value):
    assert run(repos, data(max_state_chars=value, questions=QUESTIONS)) == 42


def test_a_system_one_agent_cannot_be_exposed_through_a2a(repos):
    # A2A drives the chat pipeline, which a System One agent refuses: advertising it would only fail every message.
    with pytest.raises(ValueError, match="A2A"):
        run(repos, data(a2a_enabled=True))
    run(repos, data(a2a_enabled=False))
    assert repos.created["agent"].a2a_enabled is False


def test_the_agents_list_carries_the_system_one_service_of_a_system_one_agent(mocker):
    # The list shows one column for whichever service the agent uses: AI service for LLM agents, S1 service for System One.
    from models.system_one_service import SystemOneService
    s1 = SystemOneService(service_id=7, name="System One lab", endpoint="http://so.test", description="nimble-latest", app_id=1)
    so = SystemOneAgent(agent_id=5, app_id=1, name="Triage", system_one_service_id=7, questions=QUESTIONS, is_tool=True)
    so.system_one_service = s1
    so.type = "system_one_agent"
    mocker.patch("services.agent_service.AgentRepository.get_by_app_id", return_value=[so])
    mocker.patch("services.agent_service.AgentRepository.get_ai_services_dict_by_app_id", return_value={})
    (item,) = AgentService().get_agents_list(MagicMock(), 1)
    assert item.system_one_service == {"service_id": 7, "name": "System One lab", "model": "nimble-latest"}
    assert item.ai_service is None
