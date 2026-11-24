"""Fixtures shared by the Chat integration tests (defined in ``_chat_support``)."""
import pytest

from tests.integration.internal_chat._chat_support import (  # noqa: F401  (fixtures)
    debug_records,
    fakes,
    purge_leftovers_of_killed_runs,
    worker_session_on_test_db,
    world,
)


@pytest.fixture(scope="session", autouse=True)
def _remove_leftovers_of_killed_runs(test_engine):
    """A run killed in the middle of a concurrency test leaves its committed ``cc-...`` world behind: remove it."""
    purge_leftovers_of_killed_runs(test_engine)


@pytest.fixture(autouse=True)
def _private_file_storage(tmp_path, monkeypatch):
    """Uploads go to a per-test folder.

    Conversation ids are reused across runs of the test DB, so a shared ``data/tmp`` hands a test the files of an
    earlier run (and the files of this one would outlive it).

    Limit: the ``/static`` route in ``backend/main.py`` captures the folder at import time, so a test that fetches a
    signed ``/static/...`` URL would still 404 (it would look in the real ``data/tmp``).
    """
    monkeypatch.setenv("TMP_BASE_FOLDER", str(tmp_path))
