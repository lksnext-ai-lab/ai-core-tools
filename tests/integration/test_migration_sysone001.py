"""sysone001 round trip WITH data (the migration's upgrade/downgrade run through an Operations context).

Older code cannot load an ``Agent`` row whose ``type`` it does not know (the model is polymorphic on ``type``), so
the downgrade must not leave System One agents behind, nor rows that point at them.
"""
import importlib.util
from datetime import datetime
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, text

from models.agent import Agent, AgentTool
from tests.integration.system_one_helpers import platform_editor  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("platform_editor")]

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "sysone001_system_one_service_and_agent.py"
)
SYSTEM_ONE_TABLES = {"SystemOneService", "SystemOneAgent", "agent_system_one_answer"}


def _load():
    spec = importlib.util.spec_from_file_location("sysone001", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, fn):
    db.flush()
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        fn()
    db.expire_all()


def _tables(db):
    return set(inspect(db.connection()).get_table_names())


@pytest.fixture
def populated(db, fake_app, fake_agent):
    from models.agent_execution_event import AgentExecutionEvent
    from models.agent_system_one_answer import AgentSystemOneAnswer
    from models.system_one_agent import SystemOneAgent
    from models.system_one_service import SystemOneService

    svc = SystemOneService(name="Nimble", endpoint="http://so.test", app_id=fake_app.app_id, create_date=datetime.now())
    db.add(svc)
    db.flush()
    so = SystemOneAgent(name="Triage", app_id=fake_app.app_id, system_one_service_id=svc.service_id, is_tool=True,
                        questions=[{"key": "u", "type": "noul", "instructions": "q"}], create_date=datetime.now())
    db.add(so)
    db.flush()
    db.add(AgentTool(agent_id=fake_agent.agent_id, tool_id=so.agent_id))     # the normal agent uses it as a tool
    event = AgentExecutionEvent(app_id=fake_app.app_id, agent_id=so.agent_id, caller_type="PUBLIC_API",
                                started_at=datetime.now(), status="SUCCESS")
    db.add(event)
    db.flush()
    db.add(AgentSystemOneAnswer(event_id=event.event_id, question_key="u", question_type="noul",
                                decision="true", probability=0.9, state_reduction="none"))
    db.flush()
    return so


def test_downgrade_leaves_no_system_one_agents_nor_rows_pointing_at_them(db, fake_agent, populated):
    so_id = populated.agent_id
    _run(db, _load().downgrade)

    assert not (SYSTEM_ONE_TABLES & _tables(db))
    assert db.execute(text('select count(*) from "Agent" where type = \'system_one_agent\'')).scalar() == 0
    assert db.execute(text("select count(*) from agent_tools where tool_id = :i or agent_id = :i"), {"i": so_id}).scalar() == 0
    assert db.execute(text("select count(*) from agent_execution_event where agent_id = :i"), {"i": so_id}).scalar() == 0


def test_the_other_agents_survive_and_stay_loadable_for_older_code(db, fake_agent, populated):
    _run(db, _load().downgrade)
    survivors = db.query(Agent).all()                  # raises "No such polymorphic_identity" if a System One row remained
    assert fake_agent.agent_id in {a.agent_id for a in survivors}
    assert {a.type for a in survivors} <= {"agent", "ocr_agent"}


def test_upgrade_after_downgrade_recreates_the_tables(db, populated):
    migration = _load()
    _run(db, migration.downgrade)
    _run(db, migration.upgrade)
    assert SYSTEM_ONE_TABLES <= _tables(db)
