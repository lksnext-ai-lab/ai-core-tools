"""
Unit tests for SandboxServiceRepository.

Uses an in-memory SQLite database (same pattern as test_credential_service.py
and test_refresh_service.py) so no real PostgreSQL connection is required.
This overrides conftest.py's `db` fixture for this module only; `fake_app`/
`fake_user` (defined in conftest.py against the `db` fixture) transparently
pick up this SQLite-backed session instead.
"""

from __future__ import annotations

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-32chars-minimum-ok")
os.environ.setdefault("SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.database import Base
from models.sandbox_service import SandboxService
from repositories.sandbox_service_repository import SandboxServiceRepository

_SQLITE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def engine():
    eng = create_engine(_SQLITE_URL, connect_args={"check_same_thread": False})
    import models  # noqa: F401 — registers all ORM models with Base.metadata

    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture()
def db(engine):
    """Per-test session with rollback isolation (no FOR UPDATE needed on SQLite)."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", autoflush=True)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


def _make_service(app_id, name="Test Sandbox Service", provider="opensandbox", api_key="secret-key"):
    return SandboxService(
        app_id=app_id,
        name=name,
        provider=provider,
        api_key=api_key,
    )


class TestGetByAppId:
    def test_returns_only_services_for_app(self, db, fake_app):
        svc1 = _make_service(fake_app.app_id, name="Svc 1")
        svc2 = _make_service(fake_app.app_id, name="Svc 2")
        other_app_svc = _make_service(None, name="System Svc")
        db.add_all([svc1, svc2, other_app_svc])
        db.flush()

        result = SandboxServiceRepository.get_by_app_id(db, fake_app.app_id)

        names = {s.name for s in result}
        assert names == {"Svc 1", "Svc 2"}

    def test_returns_empty_list_for_app_with_no_services(self, db, fake_app):
        assert SandboxServiceRepository.get_by_app_id(db, fake_app.app_id) == []


class TestGetById:
    def test_returns_service_by_id(self, db, fake_app):
        svc = SandboxServiceRepository.create(db, _make_service(fake_app.app_id))
        found = SandboxServiceRepository.get_by_id(db, svc.service_id)
        assert found is not None
        assert found.service_id == svc.service_id

    def test_returns_none_for_missing_id(self, db):
        assert SandboxServiceRepository.get_by_id(db, 999999) is None


class TestGetByIdAndAppId:
    def test_returns_service_scoped_to_app(self, db, fake_app):
        svc = SandboxServiceRepository.create(db, _make_service(fake_app.app_id))
        found = SandboxServiceRepository.get_by_id_and_app_id(db, svc.service_id, fake_app.app_id)
        assert found is not None

    def test_returns_none_for_wrong_app_id(self, db, fake_app):
        svc = SandboxServiceRepository.create(db, _make_service(fake_app.app_id))
        found = SandboxServiceRepository.get_by_id_and_app_id(db, svc.service_id, fake_app.app_id + 999)
        assert found is None


class TestCreateUpdateDelete:
    def test_create_persists_and_assigns_id(self, db, fake_app):
        svc = SandboxServiceRepository.create(db, _make_service(fake_app.app_id))
        assert svc.service_id is not None

    def test_update_persists_changes(self, db, fake_app):
        svc = SandboxServiceRepository.create(db, _make_service(fake_app.app_id))
        svc.name = "Renamed"
        updated = SandboxServiceRepository.update(db, svc)
        assert updated.name == "Renamed"

        reloaded = SandboxServiceRepository.get_by_id(db, svc.service_id)
        assert reloaded.name == "Renamed"

    def test_delete_removes_service(self, db, fake_app):
        svc = SandboxServiceRepository.create(db, _make_service(fake_app.app_id))
        service_id = svc.service_id

        SandboxServiceRepository.delete(db, svc)

        assert SandboxServiceRepository.get_by_id(db, service_id) is None


class TestGetSystemServices:
    def test_returns_only_null_app_id_services(self, db, fake_app):
        app_scoped = SandboxServiceRepository.create(db, _make_service(fake_app.app_id, name="App scoped"))
        system_scoped = SandboxServiceRepository.create(db, _make_service(None, name="System scoped"))

        result = SandboxServiceRepository.get_system_services(db)

        names = {s.name for s in result}
        assert "System scoped" in names
        assert "App scoped" not in names


class TestDeleteByAppId:
    def test_deletes_all_services_for_app_only(self, db, fake_app):
        SandboxServiceRepository.create(db, _make_service(fake_app.app_id, name="Svc 1"))
        SandboxServiceRepository.create(db, _make_service(fake_app.app_id, name="Svc 2"))
        system_svc = SandboxServiceRepository.create(db, _make_service(None, name="System Svc"))

        SandboxServiceRepository.delete_by_app_id(db, fake_app.app_id)

        assert SandboxServiceRepository.get_by_app_id(db, fake_app.app_id) == []
        # System-scoped service is untouched.
        assert SandboxServiceRepository.get_by_id(db, system_svc.service_id) is not None
