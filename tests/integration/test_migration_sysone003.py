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


def test_upgrade_reclassifies_the_old_system_one_llm_calls_as_summarization_calls(db, fake_app, fake_agent):
    # Before sysone003 a System One execution counted its summarization as llm_calls = 1 (tokens were never kept).
    migration = _load()
    _run(db, migration.downgrade)
    for provider, calls in (("system_one", 1), ("system_one", 0), ("openai", 1)):
        db.execute(text(
            "insert into agent_execution_event (event_id, app_id, agent_id, caller_type, started_at, status, provider, llm_calls) "
            "values (gen_random_uuid(), :a, :g, 'PUBLIC_API', now(), 'SUCCESS', :p, :c)"),
            {"a": fake_app.app_id, "g": fake_agent.agent_id, "p": provider, "c": calls})
    _run(db, migration.upgrade)
    rows = db.execute(text("select provider, llm_calls, summarization_calls from agent_execution_event "
                           "where agent_id = :g order by provider, llm_calls, summarization_calls"), {"g": fake_agent.agent_id}).all()
    assert [tuple(r) for r in rows] == [("openai", 1, 0), ("system_one", 0, 0), ("system_one", 0, 1)]


def test_downgrade_puts_the_summarization_calls_back_where_older_code_counted_them(db, fake_app, fake_agent):
    migration = _load()
    db.execute(text(
        "insert into agent_execution_event (event_id, app_id, agent_id, caller_type, started_at, status, provider, llm_calls, summarization_calls) "
        "values (gen_random_uuid(), :a, :g, 'PUBLIC_API', now(), 'SUCCESS', 'system_one', 0, 1)"),
        {"a": fake_app.app_id, "g": fake_agent.agent_id})
    _run(db, migration.downgrade)
    assert db.execute(text("select llm_calls from agent_execution_event where agent_id = :g"), {"g": fake_agent.agent_id}).scalar() == 1
