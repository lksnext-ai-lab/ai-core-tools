"""Integration tests for service end-of-service CRUD, RBAC, copy and export/import (step_011).

Covers AC-2, AC-4, AC-5, AC-20. Requires the test DB on port 5433.
"""

import json

import pytest

from models.app_collaborator import CollaborationRole
from tests.integration.routers.internal._eos_helpers import (
    WARNING_DAYS_ENV,
    ai_payload,
    ai_service,
    embedding_payload,
    embedding_service,
    future,
    headers_for,
    iso,
    make_app,
    member_headers,
    parse,
    past,
    same_instant,
)

pytestmark = pytest.mark.integration

KINDS = {
    "ai": {"app_path": "ai-services", "admin_path": "system-ai-services", "payload": ai_payload,
           "make": ai_service},
    "embedding": {"app_path": "embedding-services", "admin_path": "system-embedding-services",
                  "payload": embedding_payload, "make": embedding_service},
}
kinds = pytest.mark.parametrize("kind", list(KINDS))


def _base(app_id, kind):
    return f"/internal/apps/{app_id}/{KINDS[kind]['app_path']}"


class TestAppServiceRoundTrip:
    """AC-4: app AI / embedding services expose and round-trip the lifecycle fields."""

    @kinds
    def test_create_round_trips_fields_in_response_detail_and_list(self, client, fake_app, owner_headers, kind):
        eos = future(90)
        body = KINDS[kind]["payload"](end_of_service_at=iso(eos), deprecation_notice="Use the new model")
        resp = client.post(f"{_base(fake_app.app_id, kind)}/0", json=body, headers=owner_headers)
        assert resp.status_code == 200, resp.text
        created = resp.json()
        assert same_instant(created["end_of_service_at"], eos)
        assert created["deprecation_notice"] == "Use the new model"
        assert created["lifecycle_status"] == "active"
        sid = created["service_id"]

        detail = client.get(f"{_base(fake_app.app_id, kind)}/{sid}", headers=owner_headers).json()
        assert same_instant(detail["end_of_service_at"], eos)
        assert detail["deprecation_notice"] == "Use the new model"
        assert detail["lifecycle_status"] == "active"

        listed = {s["service_id"]: s for s in client.get(_base(fake_app.app_id, kind) + "/", headers=owner_headers).json()}
        assert same_instant(listed[sid]["end_of_service_at"], eos)
        assert listed[sid]["deprecation_notice"] == "Use the new model"
        assert listed[sid]["lifecycle_status"] == "active"

    @kinds
    def test_update_changes_clears_and_keeps_fields(self, client, fake_app, owner_headers, db, kind):
        svc = KINDS[kind]["make"](db, fake_app, eos=future(90), notice="old")
        url = f"{_base(fake_app.app_id, kind)}/{svc.service_id}"
        new_eos = future(5)

        resp = client.post(url, json=KINDS[kind]["payload"](end_of_service_at=iso(new_eos), deprecation_notice="new"),
                           headers=owner_headers)
        assert resp.status_code == 200, resp.text
        assert same_instant(resp.json()["end_of_service_at"], new_eos)
        assert resp.json()["deprecation_notice"] == "new"
        assert resp.json()["lifecycle_status"] == "deprecated"

        # Fields omitted -> kept as they are.
        resp = client.post(url, json=KINDS[kind]["payload"](name="renamed"), headers=owner_headers)
        assert resp.status_code == 200, resp.text
        assert same_instant(resp.json()["end_of_service_at"], new_eos)
        assert resp.json()["deprecation_notice"] == "new"

        # Explicit null -> cleared.
        resp = client.post(url, json=KINDS[kind]["payload"](end_of_service_at=None, deprecation_notice=None),
                           headers=owner_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["end_of_service_at"] is None
        assert resp.json()["deprecation_notice"] is None
        assert resp.json()["lifecycle_status"] == "active"

    @kinds
    def test_lifecycle_status_sent_by_client_is_ignored(self, client, fake_app, owner_headers, kind):
        body = KINDS[kind]["payload"](end_of_service_at=iso(future(90)), lifecycle_status="retired")
        resp = client.post(f"{_base(fake_app.app_id, kind)}/0", json=body, headers=owner_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["lifecycle_status"] == "active"

    @kinds
    def test_no_date_means_active_and_null_fields(self, client, fake_app, owner_headers, db, kind):
        svc = KINDS[kind]["make"](db, fake_app)
        detail = client.get(f"{_base(fake_app.app_id, kind)}/{svc.service_id}", headers=owner_headers).json()
        assert detail["end_of_service_at"] is None
        assert detail["deprecation_notice"] is None
        assert detail["lifecycle_status"] == "active"

    @kinds
    def test_retired_status_when_date_passed(self, client, fake_app, owner_headers, db, kind):
        svc = KINDS[kind]["make"](db, fake_app, eos=past(2), notice="gone")
        listed = client.get(_base(fake_app.app_id, kind) + "/", headers=owner_headers).json()
        assert [s["lifecycle_status"] for s in listed if s["service_id"] == svc.service_id] == ["retired"]

    @kinds
    def test_naive_datetime_is_stored_as_utc(self, client, fake_app, owner_headers, kind):
        body = KINDS[kind]["payload"](end_of_service_at="2099-01-02T03:04:05")
        resp = client.post(f"{_base(fake_app.app_id, kind)}/0", json=body, headers=owner_headers)
        assert resp.status_code == 200, resp.text
        assert parse(resp.json()["end_of_service_at"]).utcoffset().total_seconds() == 0


class TestSystemServicesAdmin:
    """AC-4: admin system-ai-services / system-embedding-services include and round-trip the fields."""

    @kinds
    def test_create_get_list_update_round_trip(self, client, admin_headers, kind):
        base = f"/internal/admin/{KINDS[kind]['admin_path']}"
        eos = future(90)
        resp = client.post(base, json=KINDS[kind]["payload"](end_of_service_at=iso(eos), deprecation_notice="sys"),
                           headers=admin_headers)
        assert resp.status_code == 201, resp.text
        sid = resp.json()["service_id"]
        assert same_instant(resp.json()["end_of_service_at"], eos)
        assert resp.json()["deprecation_notice"] == "sys"
        assert resp.json()["lifecycle_status"] == "active"

        listed = {s["service_id"]: s for s in client.get(base, headers=admin_headers).json()}
        assert same_instant(listed[sid]["end_of_service_at"], eos)
        assert listed[sid]["deprecation_notice"] == "sys"
        assert listed[sid]["lifecycle_status"] == "active"

        if kind == "ai":  # the embedding admin API has no single-GET
            got = client.get(f"{base}/{sid}", headers=admin_headers).json()
            assert same_instant(got["end_of_service_at"], eos)
            assert got["deprecation_notice"] == "sys"

        soon = future(3)
        resp = client.put(f"{base}/{sid}", json=KINDS[kind]["payload"](end_of_service_at=iso(soon),
                                                                         deprecation_notice="changed"),
                          headers=admin_headers)
        assert resp.status_code == 200, resp.text
        assert same_instant(resp.json()["end_of_service_at"], soon)
        assert resp.json()["deprecation_notice"] == "changed"
        assert resp.json()["lifecycle_status"] == "deprecated"

        resp = client.put(f"{base}/{sid}", json=KINDS[kind]["payload"](end_of_service_at=None, deprecation_notice=None),
                          headers=admin_headers)
        assert resp.json()["end_of_service_at"] is None
        assert resp.json()["lifecycle_status"] == "active"

    @kinds
    def test_lifecycle_status_in_payload_is_ignored(self, client, admin_headers, kind):
        base = f"/internal/admin/{KINDS[kind]['admin_path']}"
        resp = client.post(base, json=KINDS[kind]["payload"](end_of_service_at=iso(future(60)),
                                                              lifecycle_status="retired"), headers=admin_headers)
        assert resp.status_code == 201, resp.text
        assert resp.json()["lifecycle_status"] == "active"


class TestWarningDaysSetting:
    """AC-2: the warning window comes from the setting / env override."""

    def _status(self, client, app, headers, svc):
        return client.get(f"/internal/apps/{app.app_id}/ai-services/{svc.service_id}", headers=headers).json()[
            "lifecycle_status"]

    def test_env_seven_days(self, client, fake_app, owner_headers, db, monkeypatch):
        monkeypatch.setenv(WARNING_DAYS_ENV, "7")
        far = ai_service(db, fake_app, eos=future(10))
        near = ai_service(db, fake_app, eos=future(5))
        assert self._status(client, fake_app, owner_headers, far) == "active"
        assert self._status(client, fake_app, owner_headers, near) == "deprecated"

    def test_env_zero_has_no_deprecated_phase(self, client, fake_app, owner_headers, db, monkeypatch):
        monkeypatch.setenv(WARNING_DAYS_ENV, "0")
        svc = ai_service(db, fake_app, eos=future(1))
        assert self._status(client, fake_app, owner_headers, svc) == "active"
        gone = ai_service(db, fake_app, eos=past(1))
        assert self._status(client, fake_app, owner_headers, gone) == "retired"

    def test_default_is_thirty_days(self, client, fake_app, owner_headers, db):
        inside = ai_service(db, fake_app, eos=future(29))
        outside = ai_service(db, fake_app, eos=future(35))
        assert self._status(client, fake_app, owner_headers, inside) == "deprecated"
        assert self._status(client, fake_app, owner_headers, outside) == "active"

    def test_embedding_list_and_admin_use_same_window(self, client, fake_app, owner_headers, db, monkeypatch):
        monkeypatch.setenv(WARNING_DAYS_ENV, "7")
        svc = embedding_service(db, fake_app, eos=future(5))
        listed = client.get(f"/internal/apps/{fake_app.app_id}/embedding-services/", headers=owner_headers).json()
        assert [s["lifecycle_status"] for s in listed if s["service_id"] == svc.service_id] == ["deprecated"]


class TestRbac:
    """AC-5."""

    @kinds
    def test_editor_cannot_update_service(self, client, fake_app, app_editor_headers, db, kind):
        svc = KINDS[kind]["make"](db, fake_app)
        resp = client.post(f"{_base(fake_app.app_id, kind)}/{svc.service_id}",
                           json=KINDS[kind]["payload"](end_of_service_at=iso(future(10))), headers=app_editor_headers)
        assert resp.status_code == 403
        db.refresh(svc)
        assert svc.end_of_service_at is None

    @kinds
    def test_editor_cannot_create_service(self, client, fake_app, app_editor_headers, kind):
        resp = client.post(f"{_base(fake_app.app_id, kind)}/0", json=KINDS[kind]["payload"](),
                           headers=app_editor_headers)
        assert resp.status_code == 403

    @kinds
    def test_administrator_can_update_service(self, client, fake_app, app_admin_headers, db, kind):
        svc = KINDS[kind]["make"](db, fake_app)
        eos = future(10)
        resp = client.post(f"{_base(fake_app.app_id, kind)}/{svc.service_id}",
                           json=KINDS[kind]["payload"](end_of_service_at=iso(eos), deprecation_notice="n"),
                           headers=app_admin_headers)
        assert resp.status_code == 200, resp.text
        assert same_instant(resp.json()["end_of_service_at"], eos)

    @kinds
    def test_viewer_cannot_update_but_can_read(self, client, fake_app, app_viewer_headers, db, kind):
        svc = KINDS[kind]["make"](db, fake_app, eos=future(3))
        url = f"{_base(fake_app.app_id, kind)}/{svc.service_id}"
        assert client.post(url, json=KINDS[kind]["payload"](), headers=app_viewer_headers).status_code == 403
        assert client.get(url, headers=app_viewer_headers).status_code == 200

    @kinds
    def test_app_administrator_cannot_modify_system_service_through_app_endpoints(
        self, client, fake_app, app_admin_headers, db, kind
    ):
        system = KINDS[kind]["make"](db, None, name="rbac-system", eos=future(100))
        original_eos = system.end_of_service_at
        resp = client.post(f"{_base(fake_app.app_id, kind)}/{system.service_id}",
                           json=KINDS[kind]["payload"](end_of_service_at=iso(future(1))), headers=app_admin_headers)
        # Current behaviour: the app-scoped update does not find a system service.
        assert resp.status_code == 404, resp.text
        db.refresh(system)
        assert system.end_of_service_at == original_eos
        assert system.name == "rbac-system"

    @kinds
    def test_platform_admin_modifies_system_service_via_admin_endpoint(self, client, admin_headers, db, kind):
        system = KINDS[kind]["make"](db, None, eos=None)
        eos = future(20)
        resp = client.put(f"/internal/admin/{KINDS[kind]['admin_path']}/{system.service_id}",
                          json=KINDS[kind]["payload"](end_of_service_at=iso(eos), deprecation_notice="x"),
                          headers=admin_headers)
        assert resp.status_code == 200, resp.text
        assert same_instant(resp.json()["end_of_service_at"], eos)

    @kinds
    def test_app_administrator_gets_403_on_admin_endpoints(self, client, app_admin_headers, kind):
        assert client.get(f"/internal/admin/{KINDS[kind]['admin_path']}", headers=app_admin_headers).status_code == 403
        assert client.post(f"/internal/admin/{KINDS[kind]['admin_path']}", json=KINDS[kind]["payload"](),
                           headers=app_admin_headers).status_code == 403


def _upload(data: dict):
    return {"file": ("service.json", json.dumps(data), "application/json")}


class TestExportImportCopy:
    """AC-20."""

    @kinds
    def test_export_then_import_into_new_app_preserves_fields(self, client, fake_app, fake_user, owner_headers, db, kind):
        from models.app_collaborator import CollaborationStatus
        from tests.factories import AppCollaboratorFactory

        eos = future(45)
        svc = KINDS[kind]["make"](db, fake_app, eos=eos, notice="migrate to X")
        exported = client.post(f"{_base(fake_app.app_id, kind)}/{svc.service_id}/export", headers=owner_headers)
        assert exported.status_code == 200, exported.text
        data = exported.json()
        node = data["ai_service" if kind == "ai" else "embedding_service"]
        assert same_instant(node["end_of_service_at"], eos)
        assert node["deprecation_notice"] == "migrate to X"
        assert "lifecycle_status" not in node

        target = make_app(db)
        AppCollaboratorFactory(app=target, user=fake_user, role=CollaborationRole.OWNER,
                               status=CollaborationStatus.ACCEPTED, invited_by=fake_user.user_id)
        db.flush()
        resp = client.post(f"{_base(target.app_id, kind)}/import", files=_upload(data), headers=owner_headers)
        assert resp.status_code == 201, resp.text

        listed = client.get(_base(target.app_id, kind) + "/", headers=owner_headers).json()
        assert len(listed) == 1
        assert same_instant(listed[0]["end_of_service_at"], eos)
        assert listed[0]["deprecation_notice"] == "migrate to X"
        assert listed[0]["lifecycle_status"] == "active"

    @kinds
    def test_import_without_fields_yields_null_and_active(self, client, fake_app, owner_headers, db, kind):
        svc = KINDS[kind]["make"](db, fake_app, eos=future(2), notice="soon")
        data = client.post(f"{_base(fake_app.app_id, kind)}/{svc.service_id}/export", headers=owner_headers).json()
        node_key = "ai_service" if kind == "ai" else "embedding_service"
        data[node_key].pop("end_of_service_at", None)
        data[node_key].pop("deprecation_notice", None)

        resp = client.post(f"{_base(fake_app.app_id, kind)}/import", params={"conflict_mode": "rename"},
                           files=_upload(data), headers=owner_headers)
        assert resp.status_code == 201, resp.text
        listed = client.get(_base(fake_app.app_id, kind) + "/", headers=owner_headers).json()
        imported = [s for s in listed if s["service_id"] != svc.service_id]
        assert len(imported) == 1
        assert imported[0]["end_of_service_at"] is None
        assert imported[0]["deprecation_notice"] is None
        assert imported[0]["lifecycle_status"] == "active"

    def test_copy_ai_service_has_null_fields(self, client, fake_app, owner_headers, db):
        svc = ai_service(db, fake_app, eos=future(2), notice="soon")
        resp = client.post(f"{_base(fake_app.app_id, 'ai')}/{svc.service_id}/copy", headers=owner_headers)
        assert resp.status_code == 200, resp.text
        copy = resp.json()
        assert copy["service_id"] != svc.service_id
        assert copy["end_of_service_at"] is None
        assert copy["deprecation_notice"] is None
        assert copy["lifecycle_status"] == "active"
        db.refresh(svc)
        assert svc.end_of_service_at is not None
