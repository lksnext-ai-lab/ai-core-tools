"""sysone003: the summarization usage columns of agent_execution_event (upgrade / downgrade with data)."""
import importlib.util
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, text

from tests.integration.system_one_helpers import platform_editor  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("platform_editor")]

PATH = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "sysone003_summarization_usage_on_events.py"
NEW = {"summarization_calls", "summarization_input_tokens", "summarization_output_tokens"}


def _load():
    spec = importlib.util.spec_from_file_location("sysone003", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, fn):
    db.flush()
    with Operations.context(MigrationContext.configure(db.connection())):
        fn()
    db.expire_all()


def _columns(db):
    return {c["name"] for c in inspect(db.connection()).get_columns("agent_execution_event")}


def test_the_models_match_the_migrated_schema(db):
    assert NEW <= _columns(db)


def test_downgrade_drops_only_the_new_columns_and_keeps_the_events(db, fake_app, fake_agent):
    db.execute(text(
        "insert into agent_execution_event (event_id, app_id, agent_id, caller_type, started_at, status, input_tokens) "
        "values (gen_random_uuid(), :a, :g, 'PUBLIC_API', now(), 'SUCCESS', 7)"), {"a": fake_app.app_id, "g": fake_agent.agent_id})
    _run(db, _load().downgrade)
    assert not (NEW & _columns(db))
    assert db.execute(text("select input_tokens from agent_execution_event where agent_id = :g"), {"g": fake_agent.agent_id}).scalar() == 7


def test_upgrade_after_downgrade_defaults_existing_rows_to_zero(db, fake_app, fake_agent):
    migration = _load()
    db.execute(text(
        "insert into agent_execution_event (event_id, app_id, agent_id, caller_type, started_at, status) "
        "values (gen_random_uuid(), :a, :g, 'PUBLIC_API', now(), 'SUCCESS')"), {"a": fake_app.app_id, "g": fake_agent.agent_id})
    _run(db, migration.downgrade)
    _run(db, migration.upgrade)
    row = db.execute(text("select summarization_calls, summarization_input_tokens, summarization_output_tokens "
                          "from agent_execution_event where agent_id = :g"), {"g": fake_agent.agent_id}).one()
    assert tuple(row) == (0, 0, 0)
