"""
Integration-style unit tests for SandboxServiceRepository.

Uses the shared `db`/`fake_app` fixtures (real test-DB connection, rolled
back after each test) rather than a real Alembic migration — the
SandboxService table is created via Base.metadata.create_all() in the
session-scoped test_engine fixture (see tests/conftest.py).
"""

from __future__ import annotations

from models.sandbox_service import SandboxService
from repositories.sandbox_service_repository import SandboxServiceRepository


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
