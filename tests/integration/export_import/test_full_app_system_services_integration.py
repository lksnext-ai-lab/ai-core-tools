"""Full-app export -> import where agents and a silo use SYSTEM services (app_id IS NULL).

System services are not bundled by the export (only the app's own are), so the import must
resolve them by name against the target installation's system services.
"""

from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from models.agent import Agent
from models.ai_service import AIService
from models.app import App
from models.embedding_service import EmbeddingService
from models.silo import Silo
from models.user import User
from schemas.import_schemas import ConflictMode
from services.full_app_export_service import FullAppExportService
from services.full_app_import_service import FullAppImportService


def _delete_app(db: Session, app_id: int) -> None:
    from repositories.agent_repository import AgentRepository

    for agent in db.query(Agent).filter(Agent.app_id == app_id).all():
        AgentRepository.delete_by_id(db, agent.agent_id)
    db.query(Silo).filter(Silo.app_id == app_id).delete()
    db.query(AIService).filter(AIService.app_id == app_id).delete()
    db.query(EmbeddingService).filter(EmbeddingService.app_id == app_id).delete()
    app = db.get(App, app_id)
    if app is not None:
        db.delete(app)
    db.commit()


@pytest.fixture
def system_setup(db_session: Session):
    ts = datetime.now().timestamp()
    owner = User(email=f"sys-owner-{ts}@test.com", name="Owner")
    db_session.add(owner)
    db_session.flush()
    source = App(name=f"Sys Source {ts}", slug=f"sys-source-{ts}", owner_id=owner.user_id)
    other = App(name=f"Other Tenant {ts}", slug=f"sys-other-{ts}", owner_id=owner.user_id)
    db_session.add_all([source, other])
    db_session.flush()

    system_llm = AIService(
        app_id=None, name=f"sys-llm-{ts}", provider="OpenAI", description="gpt-x",
        endpoint="https://api.openai.com/v1", api_key="k", api_version="v1",
    )
    system_emb = EmbeddingService(
        app_id=None, name=f"sys-emb-{ts}", provider="OpenAI", description="text-embedding-3-small",
        api_key="k", endpoint="https://api.openai.com/v1",
    )
    db_session.add_all([system_llm, system_emb])
    db_session.flush()

    silo = Silo(
        app_id=source.app_id, name="Sys Silo", description="d", silo_type="CUSTOM",
        embedding_service_id=system_emb.service_id,
    )
    db_session.add(silo)
    db_session.flush()
    agents = [
        Agent(
            app_id=source.app_id, name=f"Sys Agent {i}", description="d", system_prompt="p",
            service_id=system_llm.service_id, silo_id=silo.silo_id if i == 0 else None,
            has_memory=False, temperature=0.5,
        )
        for i in range(2)
    ]
    db_session.add_all(agents)
    db_session.commit()

    created_apps = [source.app_id, other.app_id]
    yield {"source": source, "other": other, "llm": system_llm, "emb": system_emb, "created_apps": created_apps}

    try:
        for app_id in created_apps:
            _delete_app(db_session, app_id)
        db_session.delete(system_llm)
        db_session.delete(system_emb)
        db_session.flush()
        db_session.delete(owner)
        db_session.commit()
    except Exception:
        db_session.rollback()


@pytest.mark.integration
class TestFullAppSystemServicesRoundTrip:
    def test_agents_and_silo_resolve_system_services_on_import(self, db_session: Session, system_setup: dict):
        source = system_setup["source"]
        export_data = FullAppExportService(db_session).export_full_app(source.app_id, user_id=source.owner_id)

        # System services are referenced by name only, never bundled.
        assert export_data.ai_services == []
        assert export_data.embedding_services == []

        summary = FullAppImportService(db_session).import_full_app(
            export_data=export_data,
            user_id=source.owner_id,
            conflict_mode=ConflictMode.FAIL,
            new_name=f"Sys Imported {datetime.now().timestamp()}",
        )
        system_setup["created_apps"].append(summary.app_id)

        assert len(summary.total_errors) == 0, summary.total_errors
        assert summary.components_imported.get("agents", 0) == 2
        assert summary.components_imported.get("silos", 0) == 1

        agents = db_session.query(Agent).filter(Agent.app_id == summary.app_id).all()
        assert len(agents) == 2
        assert {a.service_id for a in agents} == {system_setup["llm"].service_id}
        silo = db_session.query(Silo).filter(Silo.app_id == summary.app_id).one()
        assert silo.embedding_service_id == system_setup["emb"].service_id

    def test_own_service_with_same_name_preferred_over_system(self, db_session: Session, system_setup: dict):
        source = system_setup["source"]
        export_data = FullAppExportService(db_session).export_full_app(source.app_id, user_id=source.owner_id)

        from services.agent_import_service import AgentImportService
        from schemas.export_schemas import AgentExportFileSchema  # noqa: F401  (type reference only)

        target = system_setup["other"]
        own = AIService(
            app_id=target.app_id, name=system_setup["llm"].name, provider="OpenAI", description="own",
            endpoint="https://api.openai.com/v1", api_key="k", api_version="v1",
        )
        db_session.add(own)
        db_session.commit()

        svc = AgentImportService(db_session)
        assert svc._find_ai_service_by_name(system_setup["llm"].name, target.app_id).service_id == own.service_id
        assert svc._find_ai_service_by_name(system_setup["llm"].name, source.app_id).service_id == (
            system_setup["llm"].service_id
        )
        assert export_data.agents  # export built fine

    def test_other_apps_service_is_never_matched(self, db_session: Session, system_setup: dict):
        from services.agent_import_service import AgentImportService

        other = system_setup["other"]
        source = system_setup["source"]
        private = AIService(
            app_id=other.app_id, name=f"private-{datetime.now().timestamp()}", provider="OpenAI",
            description="x", endpoint="https://api.openai.com/v1", api_key="k", api_version="v1",
        )
        db_session.add(private)
        db_session.commit()

        assert AgentImportService(db_session)._find_ai_service_by_name(private.name, source.app_id) is None
