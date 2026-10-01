"""
Integration tests — step_038 (P6 verification gate), AC-34.

``POST /internal/apps/{app_id}/skills/import-claude-plugin`` (backend/routers/internal/skills.py,
backed by backend/services/claude_plugin_import_service.py, step_035). No prior test module existed
for this endpoint/service — see step_038's task note that step_035's review rounds only added
unit-level fixes, not dedicated tests.

Uses the shared transactional TestClient (real Postgres test DB), matching
tests/integration/routers/internal/test_skills_router.py's pattern.
"""
import io
import stat
import zipfile

import pytest


def import_url(app_id: int) -> str:
    return f"/internal/apps/{app_id}/skills/import-claude-plugin"


def _build_plugin_zip(skills: dict, *, wrapper: str = "") -> bytes:
    """Build a Claude Code plugin ZIP: ``[<wrapper>/]skills/<name>/SKILL.md`` per entry.

    ``skills`` maps skill directory name -> SKILL.md body text (frontmatter+content).
    """
    buf = io.BytesIO()
    prefix = f"{wrapper}/" if wrapper else ""
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, skill_md_body in skills.items():
            zf.writestr(f"{prefix}skills/{name}/SKILL.md", skill_md_body)
    return buf.getvalue()


def _skill_md(name: str, body: str = "Do the thing.") -> str:
    return f"---\nname: {name}\n---\n{body}\n"


def _make_zip(entries) -> bytes:
    """Low-level zip builder (mirrors tests/unit/utils/test_safe_zip.py's ``make_zip``) for
    entries ``iter_safe_zip``'s metadata checks must reject: raw ``ZipInfo`` names/attrs
    that ``zipfile.ZipFile.writestr(name, ...)`` alone can't produce (path traversal,
    symlink external_attr, case-variant duplicates written past the writer's own checks).

    entries: iterable of ``(name, data)`` or ``(name, data, external_attr)``.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for entry in entries:
            name, data = entry[0], entry[1]
            zi = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            if len(entry) > 2:
                zi.external_attr = entry[2]
            zf.writestr(zi, data)
    return buf.getvalue()


class TestClaudePluginImportHappyPath:
    def test_multi_skill_plugin_creates_app_scoped_skills_with_per_skill_report(
        self, client, fake_app, owner_headers, fake_user
    ):
        fake_user.platform_role = "editor"
        zip_bytes = _build_plugin_zip(
            {
                "alpha-skill": _skill_md("alpha-skill", "Alpha body."),
                "beta-skill": _skill_md("beta-skill", "Beta body."),
            },
            wrapper="my-plugin",
        )
        files = {"file": ("plugin.zip", io.BytesIO(zip_bytes), "application/zip")}

        resp = client.post(import_url(fake_app.app_id), headers=owner_headers, files=files)
        assert resp.status_code == 200, resp.text
        payload = resp.json()

        assert payload["imported_count"] == 2
        assert payload["skipped_count"] == 0
        assert payload["failed_count"] == 0
        by_name = {s["name"]: s for s in payload["skills"]}
        assert set(by_name) == {"alpha-skill", "beta-skill"}
        for entry in by_name.values():
            assert entry["status"] == "imported"
            assert entry["skill_id"] is not None

        # Each imported skill is app-scoped (not a system skill) and starts disabled pending review.
        list_resp = client.get(f"/internal/apps/{fake_app.app_id}/skills/", headers=owner_headers)
        assert list_resp.status_code == 200
        by_list_name = {s["name"]: s for s in list_resp.json()}
        for name in ("alpha-skill", "beta-skill"):
            assert name in by_list_name
            assert by_list_name[name]["is_system"] is False
            assert by_list_name[name]["is_enabled"] is False

    def test_duplicate_name_in_target_app_is_reported_as_skipped_not_silently_overwritten(
        self, client, fake_app, owner_headers, fake_user
    ):
        fake_user.platform_role = "editor"
        # Pre-existing app skill with the same name as a plugin candidate.
        pre_zip = io.BytesIO()
        with zipfile.ZipFile(pre_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("SKILL.md", _skill_md("dup-plugin-skill", "Original body."))
        pre_files = {"file": ("pre.zip", io.BytesIO(pre_zip.getvalue()), "application/zip")}
        pre_resp = client.post(
            f"/internal/apps/{fake_app.app_id}/skills/import", headers=owner_headers, files=pre_files
        )
        assert pre_resp.status_code == 201, pre_resp.text
        original_skill_id = pre_resp.json()["skill_id"]

        plugin_zip = _build_plugin_zip({"dup-plugin-skill": _skill_md("dup-plugin-skill", "Plugin body.")})
        files = {"file": ("plugin.zip", io.BytesIO(plugin_zip), "application/zip")}
        resp = client.post(import_url(fake_app.app_id), headers=owner_headers, files=files)
        assert resp.status_code == 200, resp.text
        payload = resp.json()

        assert payload["imported_count"] == 0
        assert payload["skipped_count"] == 1
        entry = payload["skills"][0]
        assert entry["status"] == "skipped"
        assert entry["reason"] == "duplicate name"

        # The original skill's content was never touched.
        detail_resp = client.get(
            f"/internal/apps/{fake_app.app_id}/skills/{original_skill_id}", headers=owner_headers
        )
        assert detail_resp.status_code == 200
        assert detail_resp.json()["content"].strip() == "Original body."

    def test_missing_skill_md_candidate_is_reported_failed_others_still_import(
        self, client, fake_app, owner_headers, fake_user
    ):
        fake_user.platform_role = "editor"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            # A skill directory with no SKILL.md at all.
            zf.writestr("skills/no-manifest/helper.txt", "orphaned resource file")
            zf.writestr("skills/ok-skill/SKILL.md", _skill_md("ok-skill", "Fine body."))
        files = {"file": ("plugin.zip", io.BytesIO(buf.getvalue()), "application/zip")}

        resp = client.post(import_url(fake_app.app_id), headers=owner_headers, files=files)
        assert resp.status_code == 200, resp.text
        payload = resp.json()

        by_name = {s["name"]: s for s in payload["skills"]}
        assert by_name["no-manifest"]["status"] == "failed"
        assert by_name["no-manifest"]["reason"] == "missing SKILL.md"
        assert by_name["ok-skill"]["status"] == "imported"
        assert payload["imported_count"] == 1
        assert payload["failed_count"] == 1


class TestClaudePluginImportArchiveLimits:
    def test_archive_violating_safe_zip_file_size_limit_is_rejected_400(
        self, client, fake_app, owner_headers, fake_user, monkeypatch
    ):
        """A plugin archive violating a shared safe-zip limit (FR-8) fails the whole request with
        the same 400/SkillImportError semantics as the single-skill /import endpoint — no per-skill
        report is produced because the archive itself is invalid."""
        import config as settings

        monkeypatch.setattr(settings, "SKILL_IMPORT_MAX_FILE_BYTES", 10)
        fake_user.platform_role = "editor"

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("skills/big-skill/SKILL.md", _skill_md("big-skill", "x" * 500))
        files = {"file": ("plugin.zip", io.BytesIO(buf.getvalue()), "application/zip")}

        resp = client.post(import_url(fake_app.app_id), headers=owner_headers, files=files)
        assert resp.status_code == 400, resp.text

    def test_archive_with_no_skills_prefix_entries_is_rejected_400(
        self, client, fake_app, owner_headers, fake_user
    ):
        fake_user.platform_role = "editor"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("README.md", "not a skill at all")
        files = {"file": ("plugin.zip", io.BytesIO(buf.getvalue()), "application/zip")}

        resp = client.post(import_url(fake_app.app_id), headers=owner_headers, files=files)
        assert resp.status_code == 400, resp.text

    def test_archive_exceeding_max_plugin_skills_is_rejected_400(
        self, client, fake_app, owner_headers, fake_user, monkeypatch
    ):
        import config as settings

        monkeypatch.setattr(settings, "SKILL_IMPORT_MAX_PLUGIN_SKILLS", 2)
        fake_user.platform_role = "editor"

        zip_bytes = _build_plugin_zip(
            {
                "one": _skill_md("one"),
                "two": _skill_md("two"),
                "three": _skill_md("three"),
            }
        )
        files = {"file": ("plugin.zip", io.BytesIO(zip_bytes), "application/zip")}

        resp = client.post(import_url(fake_app.app_id), headers=owner_headers, files=files)
        assert resp.status_code == 400, resp.text

    def test_invalid_zip_bytes_are_rejected_400(self, client, fake_app, owner_headers, fake_user):
        fake_user.platform_role = "editor"
        files = {"file": ("bad.zip", io.BytesIO(b"not a zip"), "application/zip")}
        resp = client.post(import_url(fake_app.app_id), headers=owner_headers, files=files)
        assert resp.status_code == 400


class TestClaudePluginImportHostileZipMembers:
    """This route's ``iter_safe_zip(..., require_skill_md=False)`` call (step_035) is relied on
    to still enforce zip-slip/symlink/duplicate protections even though it relaxes the
    "SKILL.md at the archive root" requirement of the single-skill ``/import`` endpoint. These
    pin the specific rejection ``reason`` (from ``utils/safe_zip.py``) in the 400 body, not just
    the bare status code, so a future regression in that shared module is caught here too."""

    def test_path_traversal_member_is_rejected_with_traversal_reason(
        self, client, fake_app, owner_headers, fake_user
    ):
        from utils.safe_zip import REASON_TRAVERSAL

        fake_user.platform_role = "editor"
        zip_bytes = _make_zip(
            [
                ("skills/ok-skill/SKILL.md", _skill_md("ok-skill").encode("utf-8")),
                ("skills/ok-skill/../../../etc/passwd", b"evil"),
            ]
        )
        files = {"file": ("plugin.zip", io.BytesIO(zip_bytes), "application/zip")}

        resp = client.post(import_url(fake_app.app_id), headers=owner_headers, files=files)
        assert resp.status_code == 400, resp.text
        assert REASON_TRAVERSAL in resp.json()["detail"]

    def test_symlink_member_is_rejected_with_symlink_reason(
        self, client, fake_app, owner_headers, fake_user
    ):
        from utils.safe_zip import REASON_SYMLINK

        fake_user.platform_role = "editor"
        zip_bytes = _make_zip(
            [
                ("skills/ok-skill/SKILL.md", _skill_md("ok-skill").encode("utf-8")),
                ("skills/ok-skill/evil-link", b"/etc/passwd", (stat.S_IFLNK | 0o777) << 16),
            ]
        )
        files = {"file": ("plugin.zip", io.BytesIO(zip_bytes), "application/zip")}

        resp = client.post(import_url(fake_app.app_id), headers=owner_headers, files=files)
        assert resp.status_code == 400, resp.text
        assert REASON_SYMLINK in resp.json()["detail"]

    def test_case_variant_duplicate_entry_is_rejected_with_duplicate_reason(
        self, client, fake_app, owner_headers, fake_user
    ):
        from utils.safe_zip import REASON_DUPLICATE

        fake_user.platform_role = "editor"
        zip_bytes = _make_zip(
            [
                ("skills/ok-skill/SKILL.md", _skill_md("ok-skill").encode("utf-8")),
                ("skills/ok-skill/notes.txt", b"original"),
                ("skills/ok-skill/NOTES.txt", b"case-variant collision"),
            ]
        )
        files = {"file": ("plugin.zip", io.BytesIO(zip_bytes), "application/zip")}

        resp = client.post(import_url(fake_app.app_id), headers=owner_headers, files=files)
        assert resp.status_code == 400, resp.text
        assert REASON_DUPLICATE in resp.json()["detail"]


class TestClaudePluginImportRBAC:
    def test_editor_role_forbidden_administrator_required(self, client, fake_app, db, fake_user):
        """Two distinct 403-raising guards sit on this route: the platform-level
        ``require_editor_for_writes`` (rejects any user whose ``User.platform_role`` is the
        default ``'viewer'``, detail "Viewer role cannot create or modify resources") and the
        app-level ``require_min_role("administrator")`` (detail "Insufficient permissions").
        This test targets the SECOND one specifically -- an app EDITOR collaborator must not be
        able to bulk-import skills (which can carry executable bootstrap scripts). ``platform_role
        ="editor"`` below is required so the user clears the platform-level gate first and the
        app-role gate is what's actually exercised; asserting the exact ``detail`` (not just the
        403 status code) pins which guard fired, so this test can't silently start passing against
        the wrong guard if either one is ever refactored."""
        from models.user import User
        from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
        from utils.local_auth_tokens import mint_access_token
        from datetime import datetime

        editor_user = User(email="editor@mattin-test.com", name="Editor User", is_active=True, platform_role="editor")
        db.add(editor_user)
        db.flush()
        collab = AppCollaborator(
            app_id=fake_app.app_id,
            user_id=editor_user.user_id,
            role=CollaborationRole.EDITOR,
            invited_by=editor_user.user_id,
            status=CollaborationStatus.ACCEPTED,
            accepted_at=datetime.now(),
        )
        db.add(collab)
        db.flush()
        token, _ = mint_access_token(editor_user.user_id, editor_user.email, editor_user.name)
        editor_headers = {"Authorization": f"Bearer {token}"}

        zip_bytes = _build_plugin_zip({"one": _skill_md("one")})
        files = {"file": ("plugin.zip", io.BytesIO(zip_bytes), "application/zip")}
        resp = client.post(import_url(fake_app.app_id), headers=editor_headers, files=files)
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Insufficient permissions"
