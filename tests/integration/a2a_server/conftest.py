"""Fixtures for the a2a-sdk contract suite (step_002).

`a2a_sdk_tables` creates the `a2a_*` SDK tables on the test DB for the
duration of the session, using `get_sdk_metadata()` -- the same registry
`services/a2a_server/storage.py` binds the SDK store/stream to. After
step_007 lands (the Alembic migration that creates these tables for real),
this fixture degenerates to an existence check and no longer creates or
drops anything, so the two steps' table lifecycles never fight each other.
"""

from __future__ import annotations

import pytest
from services.a2a_server.sdk_models import TASKS_TABLE, get_sdk_metadata
from sqlalchemy import inspect


@pytest.fixture(scope="session")
def a2a_sdk_tables(test_engine):
    """Ensures the `a2a_tasks`/`a2a_task_events`/`a2a_task_versions` tables exist.

    `test_engine` is the session-scoped sync engine on the test DB defined in
    `tests/conftest.py`. Creates the tables only if absent (e.g. step_007's
    migration has not run against this test DB), and drops only what this
    fixture itself created -- never tables an Alembic migration or another
    fixture owns.
    """
    metadata = get_sdk_metadata()
    created_by_fixture = not inspect(test_engine).has_table(TASKS_TABLE)

    if created_by_fixture:
        metadata.create_all(bind=test_engine)

    yield

    if created_by_fixture:
        metadata.drop_all(bind=test_engine)
