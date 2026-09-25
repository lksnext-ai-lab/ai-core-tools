"""Smoke tests for the admin `/internal/admin/system-skills` block (step_012).

Requires test DB on port 5433.
Run with: pytest tests/integration/routers/internal/test_system_skills_admin.py -v
"""
import io
import zipfile

import pytest

from tests.factories import SystemSkillFactory, configure_factories

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def admin_headers(fake_user, db, monkeypatch):
    """Auth headers for fake_user promoted to OMNIADMIN via monkeypatch."""
    from utils.local_auth_tokens import mint_access_token

    monkeypatch.setenv("AICT_OMNIADMINS", fake_user.email)
    db.flush()
    token, _ = mint_access_token(fake_user.user_id, fake_user.email, fake_user.name)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def system_skill(db):
    configure_factories(db)
    return SystemSkillFactory(name="smoke-system-skill")


def make_zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


def good_zip(name="imported-system-skill"):
    return make_zip({
        "SKILL.md": f"---\nname: {name}\ndescription: from import\n---\n# Body\nhello\n",
    })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSystemSkillsAdminAuthz:
    def test_non_admin_gets_403(self, auth_headers, client):
        response = client.get("/internal/admin/system-skills", headers=auth_headers)
        assert response.status_code == 403


class TestSystemSkillsAdminCrud:
    def test_list_includes_disabled(self, admin_headers, client, db):
        configure_factories(db)
        SystemSkillFactory(name="enabled-one", is_enabled=True)
        SystemSkillFactory(name="disabled-one", is_enabled=False)

        response = client.get("/internal/admin/system-skills", headers=admin_headers)
        assert response.status_code == 200, response.text
        names = {item["name"] for item in response.json()}
        assert {"enabled-one", "disabled-one"} <= names

    def test_get_detail_404_for_missing(self, admin_headers, client):
        response = client.get("/internal/admin/system-skills/999999", headers=admin_headers)
        assert response.status_code == 404

    def test_create_update_delete_cycle(self, admin_headers, client):
        create_payload = {"name": "Smoke Created Skill", "content": "# body\n", "description": "desc"}
        create_resp = client.post("/internal/admin/system-skills", json=create_payload, headers=admin_headers)
        assert create_resp.status_code == 201, create_resp.text
        data = create_resp.json()
        assert data["is_system"] is True
        assert data["source"] == "admin"
        skill_id = data["skill_id"]

        update_payload = {"name": "Smoke Created Skill", "content": "# body v2\n", "description": "desc v2"}
        update_resp = client.put(
            f"/internal/admin/system-skills/{skill_id}", json=update_payload, headers=admin_headers
        )
        assert update_resp.status_code == 200, update_resp.text
        assert update_resp.json()["content"] == "# body v2\n"
        # CreateUpdateSkillSchema has no `source` field: it cannot be changed by an update.
        assert update_resp.json()["source"] == "admin"

        toggle_resp = client.patch(
            f"/internal/admin/system-skills/{skill_id}/enabled",
            json={"is_enabled": False},
            headers=admin_headers,
        )
        assert toggle_resp.status_code == 200, toggle_resp.text
        assert toggle_resp.json()["is_enabled"] is False

        export_resp = client.get(f"/internal/admin/system-skills/{skill_id}/export", headers=admin_headers)
        assert export_resp.status_code == 200
        assert export_resp.headers["content-type"] == "application/zip"
        assert "attachment" in export_resp.headers["content-disposition"]
        assert export_resp.headers["x-content-type-options"] == "nosniff"
        names = zipfile.ZipFile(io.BytesIO(export_resp.content)).namelist()
        assert "SKILL.md" in names

        delete_resp = client.delete(f"/internal/admin/system-skills/{skill_id}", headers=admin_headers)
        assert delete_resp.status_code == 204

        get_after_delete = client.get(f"/internal/admin/system-skills/{skill_id}", headers=admin_headers)
        assert get_after_delete.status_code == 404

    def test_delete_yaml_source_skill_returns_409(self, admin_headers, client, db):
        configure_factories(db)
        yaml_skill = SystemSkillFactory(name="yaml-seeded", source="yaml")

        response = client.delete(f"/internal/admin/system-skills/{yaml_skill.skill_id}", headers=admin_headers)
        assert response.status_code == 409

    def test_import_system_skill(self, admin_headers, client):
        files = {"file": ("skill.zip", good_zip(), "application/zip")}
        response = client.post("/internal/admin/system-skills/import", files=files, headers=admin_headers)
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["name"] == "imported-system-skill"
        assert data["is_system"] is True
        # Security (review-round Finding 2): a system-skill import is platform-wide
        # (app_id IS NULL) and immediately selectable in every tenant's skill picker —
        # it must land disabled pending an explicit admin review-and-enable step, unlike
        # the app-scoped single-file /import route (which stays enabled by default).
        assert data["is_enabled"] is False

    def test_update_app_scoped_skill_via_admin_returns_404(self, admin_headers, client, db, fake_app):
        configure_factories(db)
        from tests.factories import SkillFactory

        app_skill = SkillFactory(app=fake_app, name="app-scoped-skill")
        response = client.put(
            f"/internal/admin/system-skills/{app_skill.skill_id}",
            json={"name": "app-scoped-skill", "content": "# x\n"},
            headers=admin_headers,
        )
        assert response.status_code == 404
