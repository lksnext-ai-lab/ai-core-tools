"""Fixtures for the a2a-sdk contract suite (step_002).

`a2a_sdk_tables` asserts the `a2a_*` SDK tables exist on the test DB. As of
step_007, `tests/conftest.py`'s session-scoped `test_engine` fixture is the
sole owner of their lifecycle: it creates them (via
`services.a2a_server.sdk_models.get_sdk_metadata()`, the same registry
`services/a2a_server/storage.py` binds the SDK store/stream to) right after
`Base.metadata.create_all`, and drops them at session teardown. This fixture
therefore no longer creates or drops anything itself (RB-10) -- that would
race with `test_engine`'s ownership of the same tables.
"""

from __future__ import annotations

import pytest
from services.a2a_server.sdk_models import EVENTS_TABLE, TASKS_TABLE, VERSIONS_TABLE
from sqlalchemy import inspect


@pytest.fixture(scope="session")
def a2a_sdk_tables(test_engine):
    """Asserts the `a2a_tasks`/`a2a_task_events`/`a2a_task_versions` tables exist.

    `test_engine` (session-scoped, `tests/conftest.py`) already created them.
    This fixture is purely a guard so a test that depends on it fails with a
    clear message rather than a confusing "relation does not exist" error if
    that assumption ever breaks.
    """
    inspector = inspect(test_engine)
    for table in (TASKS_TABLE, EVENTS_TABLE, VERSIONS_TABLE):
        assert inspector.has_table(table), (
            f"{table!r} does not exist on the test DB; tests/conftest.py's test_engine "
            "fixture should have created it via get_sdk_metadata()"
        )
    yield
