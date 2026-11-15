"""Fixtures shared by the Chat integration tests (defined in ``_chat_support``)."""
import pytest

from tests.integration.internal_chat._chat_support import fakes, world  # noqa: F401


@pytest.fixture(autouse=True)
def _private_file_storage(tmp_path, monkeypatch):
    """Uploads go to a per-test folder.

    Conversation ids are reused across runs of the test DB, so a shared ``data/tmp`` hands a test the files of an
    earlier run (and the files of this one would outlive it).

    Limit: the ``/static`` route in ``backend/main.py`` captures the folder at import time, so a test that fetches a
    signed ``/static/...`` URL would still 404 (it would look in the real ``data/tmp``).
    """
    monkeypatch.setenv("TMP_BASE_FOLDER", str(tmp_path))
