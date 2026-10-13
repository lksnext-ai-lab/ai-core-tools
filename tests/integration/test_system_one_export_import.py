"""Export / import of System One agents and services (real test DB, savepoint session).

Convention of the repo: an exported agent carries the NAME of its services; a single-agent import resolves them by
name in the target app. A full-app export also carries the System One services (never the token).
"""
import json
from datetime import datetime

import pytest

from models.agent import Agent
from models.ai_service import AIService
from models.system_one_agent import SystemOneAgent
from models.system_one_service import SystemOneService
from schemas.import_schemas import ConflictMode
from services.agent_export_service import AgentExportService
from services.agent_import_service import AgentImportService
from services.full_app_export_service import FullAppExportService
from services.full_app_import_service import FullAppImportService

pytestmark = pytest.mark.integration

TOKEN = "super-secret-token-123"  # pragma: allowlist secret
QUESTIONS = [
    {"key": "urgent", "type": "noul", "instructions": "Is it urgent?", "threshold": 0.8},
    {"key": "area", "type": "choice", "instructions": "Which area?", "min_probability": 0.6,
     "criteria": [{"key": "billing", "description": "Invoices"}, {"key": "tech"}]},
    {"key": "anger", "type": "score", "instructions": "How angry?", "criteria": ["Calm", "Angry"]},
]


@pytest.fixture
def world(db, fake_app):
    svc = SystemOneService(name="Nimble", endpoint="http://172.16.59.1:8100", api_key=TOKEN, description="nimble-latest",
                           extra_config='{"max_concurrency": 2}', app_id=fake_app.app_id, create_date=datetime.now())
    llm = AIService(name="Summarizer", provider="OpenAI", api_key="sk-x", description="gpt-x",  # pragma: allowlist secret
                    app_id=fake_app.app_id, create_date=datetime.now())
    db.add_all([svc, llm])
    db.flush()
    agent = SystemOneAgent(name="Triage", description="Classifies", app_id=fake_app.app_id,
                           system_one_service_id=svc.service_id, summarization_service_id=llm.service_id,
                           questions=QUESTIONS, max_state_chars=4000, is_tool=True, create_date=datetime.now())
    db.add(agent)
    db.commit()
    return type("World", (), {"service": svc, "llm": llm, "agent": agent})


def new_app(db, fake_user, name):
    from models.app import App

    app = App(name=name, slug=name.lower().replace(" ", "-"), owner_id=fake_user.user_id)
    db.add(app)
    db.commit()
    return app


# ------------------------------------------------------------- agent export

def test_agent_export_carries_questions_and_service_names_but_no_token(db, fake_app, world):
    export = AgentExportService(db).export_agent(world.agent.agent_id, fake_app.app_id)
    a = export.agent
    assert a.type == "system_one_agent" and a.max_state_chars == 4000
    assert a.system_one_service_name == "Nimble" and a.summarization_service_name == "Summarizer"
    assert [q["key"] for q in a.questions] == ["urgent", "area", "anger"]
    dumped = export.model_dump_json()
    assert TOKEN not in dumped and "sk-x" not in dumped                       # no secret anywhere
    assert export.ai_service is None                                         # nothing to bundle: no LLM service


def test_normal_agents_export_is_unchanged(db, fake_app, fake_agent):
    a = AgentExportService(db).export_agent(fake_agent.agent_id, fake_app.app_id).agent
    assert a.type is None and a.questions is None and a.system_one_service_name is None


# ------------------------------------------------------------- agent import

def _normalized(questions):
    """The questions as an import stores them: through the schema, so its defaults (e.g. color_start) are applied."""
    from pydantic import TypeAdapter
    from schemas.system_one_schemas import QuestionList
    return [q.model_dump(mode="json", exclude_none=True) for q in TypeAdapter(QuestionList).validate_python(questions)]


def test_roundtrip_in_the_same_app_with_rename(db, fake_app, world):
    export = AgentExportService(db).export_agent(world.agent.agent_id, fake_app.app_id)
    result = AgentImportService(db).import_agent(export, fake_app.app_id, ConflictMode.RENAME)
    assert result.created and result.component_name == "Triage (1)"
    copy = db.query(SystemOneAgent).filter(SystemOneAgent.agent_id == result.component_id).one()
    assert copy.questions == _normalized(world.agent.questions) and copy.max_state_chars == 4000
    assert copy.system_one_service_id == world.service.service_id and copy.summarization_service_id == world.llm.service_id
    assert copy.is_tool is True and copy.service_id is None and copy.type == "system_one_agent"


def test_import_into_another_app_needs_the_service_there_by_name(db, fake_user, fake_app, world):
    export = AgentExportService(db).export_agent(world.agent.agent_id, fake_app.app_id)
    other = new_app(db, fake_user, "Target App")
    with pytest.raises(ValueError) as e:
        AgentImportService(db).import_agent(export, other.app_id)
    assert "System One service 'Nimble'" in str(e.value) and "before importing" in str(e.value)
    db.add(SystemOneService(name="Nimble", endpoint="http://other", app_id=other.app_id, create_date=datetime.now()))
    db.commit()
    result = AgentImportService(db).import_agent(export, other.app_id)
    imported = db.query(SystemOneAgent).filter(SystemOneAgent.agent_id == result.component_id).one()
    assert imported.app_id == other.app_id and imported.system_one_service.endpoint == "http://other"
    assert imported.summarization_service_id is None                          # not in the target app: truncation
    assert any("summarization" in w.lower() for w in result.warnings)


def test_import_with_invalid_questions_is_rejected(db, fake_app, world):
    export = AgentExportService(db).export_agent(world.agent.agent_id, fake_app.app_id)
    export.agent.questions = [{"key": "Bad Key", "type": "noul", "instructions": "q"}]
    with pytest.raises(ValueError, match="questions"):
        AgentImportService(db).import_agent(export, fake_app.app_id, ConflictMode.RENAME)


def test_name_conflict_fails_by_default_and_overrides_on_request(db, fake_app, world):
    export = AgentExportService(db).export_agent(world.agent.agent_id, fake_app.app_id)
    with pytest.raises(ValueError, match="already exists"):
        AgentImportService(db).import_agent(export, fake_app.app_id)
    export.agent.max_state_chars = 2500
    export.agent.questions = [{"key": "only", "type": "noul", "instructions": "q"}]
    result = AgentImportService(db).import_agent(export, fake_app.app_id, ConflictMode.OVERRIDE)
    assert result.created is False and result.conflict_detected is True
    db.refresh(world.agent)
    assert world.agent.max_state_chars == 2500 and [q["key"] for q in world.agent.questions] == ["only"]


def test_override_never_turns_an_agent_of_another_type_into_system_one(db, fake_app, fake_agent, world):
    export = AgentExportService(db).export_agent(world.agent.agent_id, fake_app.app_id)
    export.agent.name = fake_agent.name
    with pytest.raises(ValueError, match="type"):
        AgentImportService(db).import_agent(export, fake_app.app_id, ConflictMode.OVERRIDE)
    assert db.query(Agent).filter(Agent.agent_id == fake_agent.agent_id).one().type != "system_one_agent"


def test_the_id_map_of_a_full_import_wins_over_the_name_lookup(db, fake_app, world):
    other = SystemOneService(name="Elsewhere", endpoint="http://x", app_id=fake_app.app_id, create_date=datetime.now())
    db.add(other)
    db.flush()
    export = AgentExportService(db).export_agent(world.agent.agent_id, fake_app.app_id)
    result = AgentImportService(db).import_agent(export, fake_app.app_id, ConflictMode.RENAME,
                                                 system_one_service_id_map={"Nimble": other.service_id})
    assert db.query(SystemOneAgent).get(result.component_id).system_one_service_id == other.service_id


# ------------------------------------------------------------ full app

def test_full_export_includes_services_without_token_and_does_not_skip_the_agent(db, fake_app, world):
    export = FullAppExportService(db).export_full_app(fake_app.app_id)
    assert [s.name for s in export.system_one_services] == ["Nimble"]
    svc = export.system_one_services[0]
    assert (svc.endpoint, svc.model_name, svc.max_concurrency, svc.api_key) == ("http://172.16.59.1:8100", "nimble-latest", 2, None)
    assert [a.name for a in export.agents if a.type == "system_one_agent"] == ["Triage"]   # not "skipped: no AI service"
    assert TOKEN not in export.model_dump_json()


def test_full_roundtrip_creates_the_service_and_links_the_agent(db, fake_user, world, fake_app):
    export = FullAppExportService(db).export_full_app(fake_app.app_id)
    payload = json.loads(export.model_dump_json())                           # through JSON, as a real file would
    from schemas.export_schemas import AppExportFileSchema

    summary = FullAppImportService(db).import_full_app(
        AppExportFileSchema(**payload), fake_user.user_id, ConflictMode.RENAME, new_name="Imported copy")
    assert not summary.total_errors, summary.total_errors
    assert summary.components_imported["system_one_services"] == 1 and summary.components_imported["agents"] >= 1
    assert any("System One service 'Nimble'" in w and "token" in w.lower() for w in summary.total_warnings)
    svc = db.query(SystemOneService).filter(SystemOneService.app_id == summary.app_id).one()
    assert svc.api_key is None and svc.endpoint == "http://172.16.59.1:8100" and svc.description == "nimble-latest"
    assert json.loads(svc.extra_config) == {"max_concurrency": 2}
    agent = db.query(SystemOneAgent).filter(SystemOneAgent.app_id == summary.app_id).one()
    assert agent.system_one_service_id == svc.service_id and agent.questions == _normalized(world.agent.questions)


def test_full_import_applies_a_supplied_token(db, fake_user, world, fake_app):
    export = FullAppExportService(db).export_full_app(fake_app.app_id)
    summary = FullAppImportService(db).import_full_app(export, fake_user.user_id, ConflictMode.RENAME,
                                                       new_name="With token", api_keys={"Nimble": "typed-by-user"})
    svc = db.query(SystemOneService).filter(SystemOneService.app_id == summary.app_id).one()
    assert svc.api_key == "typed-by-user"


def test_deselecting_the_service_leaves_the_agent_reported_not_half_imported(db, fake_user, world, fake_app):
    export = FullAppExportService(db).export_full_app(fake_app.app_id)
    summary = FullAppImportService(db).import_full_app(
        export, fake_user.user_id, ConflictMode.RENAME, new_name="No service",
        component_selection={"agent": ["Triage"]})
    assert db.query(SystemOneAgent).filter(SystemOneAgent.app_id == summary.app_id).count() == 0
    assert any("Triage" in w and "System One service" in w for w in summary.total_warnings)


def test_preview_lists_the_system_one_services(db, fake_user, world, fake_app):
    export = FullAppExportService(db).export_full_app(fake_app.app_id)
    preview = FullAppImportService(db).preview_import(export, fake_user.user_id)
    assert [(i.component_name, i.component_type.value) for i in preview.system_one_services] == [("Nimble", "system_one_service")]
    assert preview.component_counts["system_one_services"] == 1


def test_a_selection_with_the_service_and_the_agent_imports_both_linked(db, fake_user, world, fake_app):
    """What the import wizard sends when everything is selected (it now lists System One services)."""
    export = FullAppExportService(db).export_full_app(fake_app.app_id)
    summary = FullAppImportService(db).import_full_app(
        export, fake_user.user_id, ConflictMode.RENAME, new_name="Wizard import",
        component_selection={"system_one_service": ["Nimble"], "agent": ["Triage"]})
    assert not summary.total_errors and summary.components_imported["system_one_services"] == 1
    agent = db.query(SystemOneAgent).filter(SystemOneAgent.app_id == summary.app_id).one()
    assert agent.system_one_service.name == "Nimble"
