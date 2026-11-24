"""App default embedding service (the service the Chat indexes attachments with): API, used-by, warnings, delete."""
import pytest

from models.app import App
from models.app_collaborator import CollaborationRole
from tests.integration.routers.internal._eos_helpers import (
    embedding_service,
    make_app,
    member_headers,
    past,
    future,
)


def put(client, app, headers, **fields):
    return client.put(f"/internal/apps/{app.app_id}", json={"name": app.name, **fields}, headers=headers)


class TestAppApi:
    def test_default_is_null_then_set_read_and_cleared(self, client, fake_app, owner_headers, db):
        assert client.get(f"/internal/apps/{fake_app.app_id}", headers=owner_headers).json()[
            "default_embedding_service_id"] is None
        emb = embedding_service(db, fake_app, "emb-default")
        resp = put(client, fake_app, owner_headers, default_embedding_service_id=emb.service_id)
        assert resp.status_code == 200, resp.text
        assert resp.json()["default_embedding_service_id"] == emb.service_id
        assert client.get(f"/internal/apps/{fake_app.app_id}", headers=owner_headers).json()[
            "default_embedding_service_id"] == emb.service_id
        # omitted keeps
        resp = put(client, fake_app, owner_headers, enable_openai_api=True)
        assert resp.status_code == 200 and resp.json()["default_embedding_service_id"] == emb.service_id
        # explicit null clears
        resp = put(client, fake_app, owner_headers, default_embedding_service_id=None)
        assert resp.status_code == 200 and resp.json()["default_embedding_service_id"] is None

    def test_a_system_service_is_allowed(self, client, fake_app, owner_headers, db):
        system = embedding_service(db, None, "emb-system")
        resp = put(client, fake_app, owner_headers, default_embedding_service_id=system.service_id)
        assert resp.status_code == 200 and resp.json()["default_embedding_service_id"] == system.service_id

    def test_another_apps_service_and_a_missing_one_are_rejected_alike(self, client, fake_app, owner_headers, db):
        foreign = embedding_service(db, make_app(db), "emb-foreign")
        a = put(client, fake_app, owner_headers, default_embedding_service_id=foreign.service_id)
        b = put(client, fake_app, owner_headers, default_embedding_service_id=987654321)
        assert a.status_code == b.status_code == 422
        assert a.json()["detail"].split("'")[2] == b.json()["detail"].split("'")[2]
        db.refresh(fake_app)
        assert fake_app.default_embedding_service_id is None

    def test_a_retired_service_cannot_be_newly_selected_but_can_be_kept(self, client, fake_app, owner_headers, db):
        retired = embedding_service(db, fake_app, "emb-retired", eos=past(2))
        resp = put(client, fake_app, owner_headers, default_embedding_service_id=retired.service_id)
        assert resp.status_code == 422, resp.text
        fake_app.default_embedding_service_id = retired.service_id
        db.flush()
        resp = put(client, fake_app, owner_headers, default_embedding_service_id=retired.service_id)
        assert resp.status_code == 200 and resp.json()["default_embedding_service_id"] == retired.service_id

    def test_only_administrators_and_up_can_change_it(self, client, fake_app, owner_headers, db):
        emb = embedding_service(db, fake_app, "emb-role")
        for role in (CollaborationRole.VIEWER, CollaborationRole.EDITOR):
            headers = member_headers(db, fake_app, role)
            assert put(client, fake_app, headers, default_embedding_service_id=emb.service_id).status_code == 403
        db.refresh(fake_app)
        assert fake_app.default_embedding_service_id is None
        # administrators and above may update the App's settings (the role dependency is the whole rule)
        headers = member_headers(db, fake_app, CollaborationRole.ADMINISTRATOR)
        resp = put(client, fake_app, headers, default_embedding_service_id=emb.service_id)
        assert resp.status_code == 200, resp.text
        assert resp.json()["default_embedding_service_id"] == emb.service_id
        assert resp.json()["user_role"] == "administrator"
        assert put(client, fake_app, owner_headers, default_embedding_service_id=None).status_code == 200

    def test_an_administrator_cannot_change_ownership_or_delete_through_the_update(
        self, client, fake_app, owner_headers, db
    ):
        headers = member_headers(db, fake_app, CollaborationRole.ADMINISTRATOR)
        owner_before = fake_app.owner_id
        assert put(client, fake_app, headers, owner_id=999999).status_code == 200  # unknown field is ignored
        db.refresh(fake_app)
        assert fake_app.owner_id == owner_before
        assert client.delete(f"/internal/apps/{fake_app.app_id}", headers=headers).status_code == 403


class TestUsedByAndWarnings:
    def test_the_default_shows_in_the_used_by_view(self, client, fake_app, owner_headers, db):
        emb = embedding_service(db, fake_app, "emb-used")
        other = make_app(db)
        fake_app.default_embedding_service_id = emb.service_id
        db.flush()
        url = f"/internal/apps/{fake_app.app_id}/embedding-services/{emb.service_id}/used-by"
        usage = client.get(url, headers=owner_headers).json()
        assert usage["apps_using_as_default"] == [{"app_id": fake_app.app_id, "app_name": fake_app.name}]
        assert other.app_id not in [a["app_id"] for a in usage["apps_using_as_default"]]

    def test_a_deprecated_or_retired_default_shows_a_lifecycle_warning_on_the_app(self, client, fake_app, owner_headers, db):
        emb = embedding_service(db, fake_app, "emb-warn", eos=future(5), notice="moving on")
        fake_app.default_embedding_service_id = emb.service_id
        db.flush()
        body = client.get(f"/internal/apps/{fake_app.app_id}", headers=owner_headers).json()
        assert [(w["kind"], w["role"], w["via"], w["lifecycle_status"], w["service_id"]) for w in body["lifecycle_warnings"]] == [
            ("embedding", "embedding", "app default", "deprecated", emb.service_id)]
        emb.end_of_service_at = past(1)
        db.flush()
        body = client.get(f"/internal/apps/{fake_app.app_id}", headers=owner_headers).json()
        assert body["lifecycle_warnings"][0]["lifecycle_status"] == "retired"

    def test_no_warning_without_a_default_or_for_an_active_service(self, client, fake_app, owner_headers, db):
        assert client.get(f"/internal/apps/{fake_app.app_id}", headers=owner_headers).json()["lifecycle_warnings"] == []
        emb = embedding_service(db, fake_app, "emb-ok")
        fake_app.default_embedding_service_id = emb.service_id
        db.flush()
        assert client.get(f"/internal/apps/{fake_app.app_id}", headers=owner_headers).json()["lifecycle_warnings"] == []


class TestDeleteClearsTheDefault:
    def test_deleting_the_embedding_service_clears_the_default(self, client, fake_app, owner_headers, db):
        emb = embedding_service(db, fake_app, "emb-delete")
        fake_app.default_embedding_service_id = emb.service_id
        db.commit()
        resp = client.delete(f"/internal/apps/{fake_app.app_id}/embedding-services/{emb.service_id}", headers=owner_headers)
        assert resp.status_code in (200, 204), resp.text
        db.expire_all()
        assert db.get(App, fake_app.app_id).default_embedding_service_id is None
        assert client.get(f"/internal/apps/{fake_app.app_id}", headers=owner_headers).json()[
            "default_embedding_service_id"] is None


class TestLangsmithKeyIsOwnerOnly:
    """[DECISION] Administrators update every App setting except the LangSmith key (OWNER role: ``App.owner_id`` or an
    accepted collaborator with role OWNER)."""

    KEY = "ls-secret-key-0123456789"  # pragma: allowlist secret

    def _owner_sets_key(self, client, fake_app, owner_headers):
        assert put(client, fake_app, owner_headers, langsmith_api_key=self.KEY).status_code == 200
        return client.get(f"/internal/apps/{fake_app.app_id}", headers=owner_headers).json()["langsmith_api_key"]

    def test_an_administrator_keeps_the_key_with_masked_omitted_or_equal_values(self, client, fake_app, owner_headers, db):
        masked = self._owner_sets_key(client, fake_app, owner_headers)
        assert masked != self.KEY
        admin = member_headers(db, fake_app, CollaborationRole.ADMINISTRATOR)
        for fields in ({"langsmith_api_key": masked}, {}, {"langsmith_api_key": self.KEY}):
            resp = put(client, fake_app, admin, agent_rate_limit=77, **fields)
            assert resp.status_code == 200, (fields, resp.text)
        db.refresh(fake_app)
        assert fake_app.langsmith_api_key == self.KEY and fake_app.agent_rate_limit == 77

    def test_an_administrator_cannot_change_or_clear_the_key_and_nothing_changes(self, client, fake_app, owner_headers, db):
        self._owner_sets_key(client, fake_app, owner_headers)
        admin = member_headers(db, fake_app, CollaborationRole.ADMINISTRATOR)
        for value in ("another-key-value-9999", ""):
            resp = put(client, fake_app, admin, langsmith_api_key=value, agent_rate_limit=55)
            assert resp.status_code == 403, (value, resp.text)
        db.refresh(fake_app)
        assert fake_app.langsmith_api_key == self.KEY and fake_app.agent_rate_limit != 55

    def test_the_owner_can_change_and_clear_it(self, client, fake_app, owner_headers, db):
        self._owner_sets_key(client, fake_app, owner_headers)
        assert put(client, fake_app, owner_headers, langsmith_api_key="new-key-value-123456").status_code == 200
        db.refresh(fake_app)
        assert fake_app.langsmith_api_key == "new-key-value-123456"
        assert put(client, fake_app, owner_headers, langsmith_api_key="").status_code == 200
        db.refresh(fake_app)
        assert not fake_app.langsmith_api_key

    def test_a_collaborator_with_role_owner_counts_as_owner(self, client, fake_app, owner_headers, db):
        self._owner_sets_key(client, fake_app, owner_headers)
        co_owner = member_headers(db, fake_app, CollaborationRole.OWNER)
        assert put(client, fake_app, co_owner, langsmith_api_key="co-owner-key-123456789").status_code == 200

    def test_the_test_endpoint_stores_nothing(self, client, fake_app, owner_headers, db, monkeypatch):
        """``POST /langsmith/test`` only validates a candidate key; it never writes the App."""
        from types import SimpleNamespace

        monkeypatch.setattr(
            "tools.langsmith_config.validate_langsmith_key",
            lambda key, endpoint: SimpleNamespace(valid=False, status="unauthorized", message="no"),
        )
        self._owner_sets_key(client, fake_app, owner_headers)
        admin = member_headers(db, fake_app, CollaborationRole.ADMINISTRATOR)
        client.post(f"/internal/apps/{fake_app.app_id}/langsmith/test", headers=admin, json={"api_key": "probe-key-123"})
        db.refresh(fake_app)
        assert fake_app.langsmith_api_key == self.KEY
