"""
Integration smoke tests for the app-scoped skills router (step_011).

Uses the shared transactional TestClient (real Postgres test DB): auth, routing, Pydantic and DB are
real; nothing is mocked. Exercises import -> export -> enable-toggle and the 403/404 cross-scope guards.
"""
import io
import zipfile

import pytest


def skills_url(app_id: int, suffix: str = "") -> str:
    return f"/internal/apps/{app_id}/skills{suffix}"


def _build_zip(name: str = "my-skill", body: str = "Do the thing.") -> bytes:
    """A minimal, valid skill package: SKILL.md at the root plus one resource file."""
    skill_md = f"---\nname: {name}\n---\n{body}\n"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SKILL.md", skill_md)
        zf.writestr("resources/notes.txt", "hello from the package")
    return buf.getvalue()


@pytest.fixture()
def fake_app_2(db):
    """A second, unrelated App (for cross-scope / 404 checks)."""
    from models.app import App

    app_obj = App(
        name="Other Workspace",
        slug="other-workspace-fixture",
        owner_id=None,
        agent_rate_limit=0,
        max_file_size_mb=10,
    )
    db.add(app_obj)
    db.flush()
    return app_obj


class TestSkillImportExportEnable:
    def test_import_then_export_then_toggle(self, client, fake_app, owner_headers, fake_user):
        # fake_user's platform_role defaults to 'viewer' (column default), which the separate,
        # unrelated global gate (require_editor_for_writes) blocks from ANY write regardless of
        # app-level role. Bump it so this test isolates the app-level RBAC being exercised here.
        fake_user.platform_role = 'editor'
        zip_bytes = _build_zip(name="import-export-skill")
        files = {"file": ("import-export-skill.zip", io.BytesIO(zip_bytes), "application/zip")}

        resp = client.post(
            skills_url(fake_app.app_id, "/import"), headers=owner_headers, files=files
        )
        assert resp.status_code == 201, resp.text
        detail = resp.json()
        assert detail["name"] == "import-export-skill"
        assert detail["is_system"] is False
        assert detail["is_enabled"] is True
        skill_id = detail["skill_id"]

        # Export round-trips as a real zip with SKILL.md at the root.
        export_resp = client.get(skills_url(fake_app.app_id, f"/{skill_id}/export"), headers=owner_headers)
        assert export_resp.status_code == 200
        assert export_resp.headers["content-type"] == "application/zip"
        assert "attachment" in export_resp.headers["content-disposition"].lower()
        assert "import-export-skill" in export_resp.headers["content-disposition"]
        assert export_resp.headers["x-content-type-options"] == "nosniff"
        exported = zipfile.ZipFile(io.BytesIO(export_resp.content))
        names = set(exported.namelist())
        assert "SKILL.md" in names
        assert "resources/notes.txt" in names

        # Disable, then re-enable.
        disable_resp = client.patch(
            skills_url(fake_app.app_id, f"/{skill_id}/enabled"),
            headers=owner_headers,
            json={"is_enabled": False},
        )
        assert disable_resp.status_code == 200, disable_resp.text
        assert disable_resp.json()["is_enabled"] is False

        enable_resp = client.patch(
            skills_url(fake_app.app_id, f"/{skill_id}/enabled"),
            headers=owner_headers,
            json={"is_enabled": True},
        )
        assert enable_resp.status_code == 200
        assert enable_resp.json()["is_enabled"] is True

        # Cleanup via DELETE — also exercises the app-scoped delete path.
        del_resp = client.delete(skills_url(fake_app.app_id, f"/{skill_id}"), headers=owner_headers)
        assert del_resp.status_code == 200

    def test_import_invalid_zip_is_400(self, client, fake_app, owner_headers, fake_user):
        fake_user.platform_role = 'editor'
        files = {"file": ("bad.zip", io.BytesIO(b"not a zip"), "application/zip")}
        resp = client.post(skills_url(fake_app.app_id, "/import"), headers=owner_headers, files=files)
        assert resp.status_code == 400

    def test_import_duplicate_name_is_409(self, client, fake_app, owner_headers, fake_user):
        fake_user.platform_role = 'editor'
        zip_bytes = _build_zip(name="dup-skill")
        files = {"file": ("dup-skill.zip", io.BytesIO(zip_bytes), "application/zip")}
        first = client.post(skills_url(fake_app.app_id, "/import"), headers=owner_headers, files=files)
        assert first.status_code == 201

        files2 = {"file": ("dup-skill.zip", io.BytesIO(_build_zip(name="dup-skill")), "application/zip")}
        second = client.post(skills_url(fake_app.app_id, "/import"), headers=owner_headers, files=files2)
        assert second.status_code == 409


class TestSkillCrossScopeGuards:
    def test_export_cross_app_is_404(self, client, fake_app, fake_app_2, owner_headers, fake_user):
        fake_user.platform_role = 'editor'
        zip_bytes = _build_zip(name="cross-scope-skill")
        files = {"file": ("cross-scope-skill.zip", io.BytesIO(zip_bytes), "application/zip")}
        created = client.post(skills_url(fake_app.app_id, "/import"), headers=owner_headers, files=files)
        assert created.status_code == 201
        skill_id = created.json()["skill_id"]

        # fake_app_2 has no collaborator record for this user -> 403 before the skill is even resolved.
        resp = client.get(skills_url(fake_app_2.app_id, f"/{skill_id}/export"), headers=owner_headers)
        assert resp.status_code == 403

    def test_get_cross_app_is_404_for_a_collaborator(self, client, fake_app, fake_app_2, owner_headers, fake_user, db):
        """A user who IS a collaborator of app 2 still can't see app 1's skill by id."""
        from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
        from datetime import datetime

        fake_user.platform_role = 'editor'
        zip_bytes = _build_zip(name="isolated-skill")
        files = {"file": ("isolated-skill.zip", io.BytesIO(zip_bytes), "application/zip")}
        created = client.post(skills_url(fake_app.app_id, "/import"), headers=owner_headers, files=files)
        assert created.status_code == 201
        skill_id = created.json()["skill_id"]

        collab = AppCollaborator(
            app_id=fake_app_2.app_id,
            user_id=fake_user.user_id,
            role=CollaborationRole.OWNER,
            invited_by=fake_user.user_id,
            status=CollaborationStatus.ACCEPTED,
            accepted_at=datetime.now(),
        )
        db.add(collab)
        db.flush()

        resp = client.get(skills_url(fake_app_2.app_id, f"/{skill_id}"), headers=owner_headers)
        assert resp.status_code == 404

    def test_enable_toggle_forbidden_below_administrator(self, client, fake_app, db):
        """A VIEWER collaborator (NOT the app owner — ownership would outrank the collaborator role)
        gets 403 on the enable toggle (administrator required)."""
        from models.user import User
        from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
        from utils.local_auth_tokens import mint_access_token
        from datetime import datetime

        viewer_user = User(email="viewer@mattin-test.com", name="Viewer User", is_active=True, platform_role='editor')
        db.add(viewer_user)
        db.flush()
        collab = AppCollaborator(
            app_id=fake_app.app_id,
            user_id=viewer_user.user_id,
            role=CollaborationRole.VIEWER,
            invited_by=viewer_user.user_id,
            status=CollaborationStatus.ACCEPTED,
            accepted_at=datetime.now(),
        )
        db.add(collab)
        db.flush()
        token, _ = mint_access_token(viewer_user.user_id, viewer_user.email, viewer_user.name)
        viewer_headers = {"Authorization": f"Bearer {token}"}

        resp = client.patch(
            skills_url(fake_app.app_id, "/999999/enabled"),
            headers=viewer_headers,
            json={"is_enabled": False},
        )
        assert resp.status_code == 403
