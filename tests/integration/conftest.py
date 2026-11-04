"""Shared fixtures for integration tests of the service end-of-service feature (steps 011/012).

Builders live in ``routers/internal/_eos_helpers.py`` and ``_eos_enforcement_helpers.py``.
"""

import pytest

from models.app_collaborator import CollaborationRole
from tests.factories import UserFactory, configure_factories
from tests.integration.routers.internal._eos_helpers import WARNING_DAYS_ENV, headers_for, member_headers


@pytest.fixture(autouse=True)
def _clean_warning_days_env(monkeypatch):
    """A developer's local .env must not change the 30-day default."""
    monkeypatch.delenv(WARNING_DAYS_ENV, raising=False)


@pytest.fixture
def factories(db):
    configure_factories(db)
    return db


@pytest.fixture
def admin_headers(db, monkeypatch):
    """Headers of a platform admin (OMNIADMIN) who is NOT a collaborator of any app."""
    configure_factories(db)
    user = UserFactory(email="eos-platform-admin@mattin-test.com")
    monkeypatch.setenv("AICT_OMNIADMINS", user.email)
    db.flush()
    return headers_for(user)


@pytest.fixture
def app_admin_headers(db, fake_app):
    return member_headers(db, fake_app, CollaborationRole.ADMINISTRATOR)


@pytest.fixture
def app_editor_headers(db, fake_app):
    return member_headers(db, fake_app, CollaborationRole.EDITOR)


@pytest.fixture
def app_viewer_headers(db, fake_app):
    return member_headers(db, fake_app, CollaborationRole.VIEWER)
