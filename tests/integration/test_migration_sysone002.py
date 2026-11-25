"""sysone002: a deleted System One service leaves its agents inoperative (SET NULL) instead of being refused."""
import importlib.util
from datetime import datetime
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, text

from models.agent import Agent
from tests.integration.system_one_helpers import platform_editor  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("platform_editor")]

PATH = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "sysone002_system_one_service_set_null.py"


def _load():
    spec = importlib.util.spec_from_file_location("sysone002", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, fn):
    db.flush()
    with Operations.context(MigrationContext.configure(db.connection())):
        fn()
    db.expire_all()


def _fk(db):
    insp = inspect(db.connection())
    (fk,) = [f for f in insp.get_foreign_keys("SystemOneAgent") if f["constrained_columns"] == ["system_one_service_id"]]
    nullable = {c["name"]: c["nullable"] for c in insp.get_columns("SystemOneAgent")}["system_one_service_id"]
    return fk["options"].get("ondelete"), nullable


@pytest.fixture
def agents(db, fake_app, fake_agent):
    from models.system_one_agent import SystemOneAgent
    from models.system_one_service import SystemOneService

    svc = SystemOneService(name="Nimble", endpoint="http://so.test", app_id=fake_app.app_id, create_date=datetime.now())
    db.add(svc)
    db.flush()
    make = lambda name, sid: SystemOneAgent(name=name, app_id=fake_app.app_id, system_one_service_id=sid, is_tool=True,
                                            questions=[{"key": "u", "type": "noul", "instructions": "q"}],
                                            create_date=datetime.now())
    live, orphan = make("Live", svc.service_id), make("Orphan", None)
    db.add_all([live, orphan])
    db.flush()
    return live, orphan


def test_models_match_the_migrated_schema(db):
    assert _fk(db) == ("SET NULL", True)


def test_downgrade_restores_restrict_not_null_and_drops_only_the_orphans(db, agents):
    live, orphan = agents
    live_id, orphan_id = live.agent_id, orphan.agent_id
    _run(db, _load().downgrade)

    assert _fk(db) == ("RESTRICT", False)
    ids = {a.agent_id for a in db.query(Agent).all()}
    assert live_id in ids and orphan_id not in ids


def test_upgrade_after_downgrade_is_set_null_again(db, agents):
    migration = _load()
    _run(db, migration.downgrade)
    _run(db, migration.upgrade)
    assert _fk(db) == ("SET NULL", True)
