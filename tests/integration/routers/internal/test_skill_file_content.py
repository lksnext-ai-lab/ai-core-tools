"""Integration tests for the on-demand skill file preview routes.

Covers `GET /internal/apps/{app_id}/skills/{skill_id}/files/content` and its admin-scoped
system-skill counterpart. Uses the shared transactional TestClient (real Postgres test DB).
"""
import io
import zipfile
from datetime import datetime

import pytest

from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
from tests.factories import UserFactory, configure_factories

pytestmark = pytest.mark.integration


def skills_url(app_id: int, suffix: str = "") -> str:
    return f"/internal/apps/{app_id}/skills{suffix}"


def _build_zip(name: str = "preview-skill") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SKILL.md", f"---\nname: {name}\n---\nDo the thing.\n")
        zf.writestr("resources/notes.txt", "hello from the package")
        # 1x1 transparent PNG (binary, no valid utf-8 decode)
        zf.writestr("resources/pixel.png", bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x01]))
    return buf.getvalue()


@pytest.fixture
def viewer_headers(db, fake_app, fake_user):
    """Auth headers for a separate user with VIEWER role on fake_app."""
    from utils.local_auth_tokens import mint_access_token

    configure_factories(db)
    viewer_user = UserFactory(email="viewer-skill-preview@mattin-test.com", name="Skill Preview Viewer")
    collab = AppCollaborator(
        app_id=fake_app.app_id,
        user_id=viewer_user.user_id,
        role=CollaborationRole.VIEWER,
        invited_by=fake_user.user_id,
        status=CollaborationStatus.ACCEPTED,
        invited_at=datetime.now(),
        accepted_at=datetime.now(),
    )
    db.add(collab)
    db.flush()
    token, _ = mint_access_token(viewer_user.user_id, viewer_user.email, viewer_user.name)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(fake_user, db, monkeypatch):
    from utils.local_auth_tokens import mint_access_token

    monkeypatch.setenv("AICT_OMNIADMINS", fake_user.email)
    db.flush()
    token, _ = mint_access_token(fake_user.user_id, fake_user.email, fake_user.name)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def imported_skill(client, fake_app, owner_headers, fake_user):
    fake_user.platform_role = 'editor'
    zip_bytes = _build_zip()
    files = {"file": ("preview-skill.zip", io.BytesIO(zip_bytes), "application/zip")}
    resp = client.post(skills_url(fake_app.app_id, "/import"), headers=owner_headers, files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestAppScopedSkillFileContent:
    def test_text_file_content_returns_decoded_text(self, client, fake_app, owner_headers, imported_skill):
        skill_id = imported_skill["skill_id"]
        resp = client.get(
            skills_url(fake_app.app_id, f"/{skill_id}/files/content"),
            headers=owner_headers,
            params={"path": "resources/notes.txt"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["path"] == "resources/notes.txt"
        assert body["content"] == "hello from the package"
        assert body["truncated"] is False

    def test_binary_file_is_rejected(self, client, fake_app, owner_headers, imported_skill):
        skill_id = imported_skill["skill_id"]
        resp = client.get(
            skills_url(fake_app.app_id, f"/{skill_id}/files/content"),
            headers=owner_headers,
            params={"path": "resources/pixel.png"},
        )
        assert resp.status_code == 400, resp.text

    def test_path_traversal_is_rejected(self, client, fake_app, owner_headers, imported_skill):
        skill_id = imported_skill["skill_id"]
        resp = client.get(
            skills_url(fake_app.app_id, f"/{skill_id}/files/content"),
            headers=owner_headers,
            params={"path": "../../etc/passwd"},
        )
        assert resp.status_code == 400, resp.text

    def test_viewer_role_can_read(self, client, fake_app, viewer_headers, imported_skill):
        skill_id = imported_skill["skill_id"]
        resp = client.get(
            skills_url(fake_app.app_id, f"/{skill_id}/files/content"),
            headers=viewer_headers,
            params={"path": "resources/notes.txt"},
        )
        assert resp.status_code == 200, resp.text

    def test_missing_file_is_404(self, client, fake_app, owner_headers, imported_skill):
        skill_id = imported_skill["skill_id"]
        resp = client.get(
            skills_url(fake_app.app_id, f"/{skill_id}/files/content"),
            headers=owner_headers,
            params={"path": "resources/nope.txt"},
        )
        assert resp.status_code == 404, resp.text

    def test_path_belonging_to_different_skill_is_404(
        self, client, fake_app, owner_headers, fake_user, imported_skill
    ):
        # A second skill, with a file at the same path but different content.
        zip_bytes = _build_zip(name="other-skill")
        files = {"file": ("other-skill.zip", io.BytesIO(zip_bytes), "application/zip")}
        other_resp = client.post(skills_url(fake_app.app_id, "/import"), headers=owner_headers, files=files)
        assert other_resp.status_code == 201, other_resp.text
        other_skill_id = other_resp.json()["skill_id"]
        assert other_skill_id != imported_skill["skill_id"]

        # Fetching the first skill's file via the SECOND skill's id must not resolve.
        resp = client.get(
            skills_url(fake_app.app_id, f"/{other_skill_id}/files/content"),
            headers=owner_headers,
            params={"path": "resources/notes.txt"},
        )
        assert resp.status_code == 200  # both skills have this path; content must be scoped correctly
        assert resp.json()["content"] == "hello from the package"

    def test_unknown_skill_id_is_404(self, client, fake_app, owner_headers):
        resp = client.get(
            skills_url(fake_app.app_id, "/999999/files/content"),
            headers=owner_headers,
            params={"path": "resources/notes.txt"},
        )
        assert resp.status_code == 404, resp.text


class TestSystemSkillFileContentAdmin:
    def test_admin_can_read_system_skill_file(self, client, db, admin_headers):
        from tests.factories import SystemSkillFactory
        from repositories.skill_package_repository import SkillPackageRepository

        configure_factories(db)
        skill = SystemSkillFactory(name="admin-preview-system-skill")
        SkillPackageRepository.replace_files(
            db, skill.skill_id, [("resources/notes.txt", b"system skill text", "text/plain")]
        )
        db.flush()

        resp = client.get(
            f"/internal/admin/system-skills/{skill.skill_id}/files/content",
            headers=admin_headers,
            params={"path": "resources/notes.txt"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["content"] == "system skill text"

    def test_non_admin_gets_403(self, client, db, auth_headers):
        from tests.factories import SystemSkillFactory

        configure_factories(db)
        skill = SystemSkillFactory(name="admin-preview-system-skill-403")
        resp = client.get(
            f"/internal/admin/system-skills/{skill.skill_id}/files/content",
            headers=auth_headers,
            params={"path": "resources/notes.txt"},
        )
        assert resp.status_code == 403, resp.text
