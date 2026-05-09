"""
Unit tests — SkillPackageRepository
=====================================

Covers ``validate_package`` (pure unit, no DB) and basic import/export behaviour.
DB-dependent tests are marked ``skip`` here; run them via the integration suite.
"""
from __future__ import annotations

import io
import zipfile

import pytest

from repositories.skill_package_repository import (
    SkillPackageRepository,
    SkillPackageValidation,
    _validate_skill_file_path,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_zip(files: dict[str, str | bytes]) -> bytes:
    """Build an in-memory ZIP from a dict of path → content."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            if isinstance(content, str):
                content = content.encode()
            zf.writestr(name, content)
    return buf.getvalue()


VALID_SKILL_MD = """\
---
name: test-skill
description: A test skill for unit tests
---
Use this skill to test things.
"""


# ---------------------------------------------------------------------------
# _validate_skill_file_path
# ---------------------------------------------------------------------------


class TestValidateSkillFilePath:
    def test_valid_relative_path(self):
        _validate_skill_file_path("scripts/run.py")  # must not raise

    def test_valid_nested_path(self):
        _validate_skill_file_path("a/b/c/d.txt")  # must not raise

    def test_empty_path_raises(self):
        with pytest.raises(ValueError, match="empty"):
            _validate_skill_file_path("")

    def test_absolute_path_raises(self):
        with pytest.raises(ValueError, match="relative"):
            _validate_skill_file_path("/etc/passwd")

    def test_parent_traversal_raises(self):
        with pytest.raises(ValueError, match="package root"):
            _validate_skill_file_path("../escape.py")

    def test_deep_traversal_raises(self):
        with pytest.raises(ValueError, match="package root"):
            _validate_skill_file_path("a/../../etc/passwd")

    def test_leading_whitespace_raises(self):
        with pytest.raises(ValueError, match="whitespace"):
            _validate_skill_file_path(" scripts/run.py")

    def test_trailing_whitespace_raises(self):
        with pytest.raises(ValueError, match="whitespace"):
            _validate_skill_file_path("scripts/run.py ")


# ---------------------------------------------------------------------------
# validate_package — hard errors
# ---------------------------------------------------------------------------


class TestValidatePackageErrors:
    def test_not_a_zip_returns_error(self):
        result = SkillPackageRepository.validate_package(b"not a zip file")
        assert not result.is_valid
        assert any("zip" in e.lower() for e in result.errors)

    def test_missing_skill_md_returns_error(self):
        z = _make_zip({"not_skill.md": "hello"})
        result = SkillPackageRepository.validate_package(z)
        assert not result.is_valid
        assert any("SKILL.md" in e for e in result.errors)

    def test_missing_name_returns_error(self):
        content = "---\ndescription: no name\n---\nbody"
        z = _make_zip({"SKILL.md": content})
        result = SkillPackageRepository.validate_package(z)
        assert not result.is_valid
        assert any("name" in e.lower() for e in result.errors)

    def test_missing_description_returns_error(self):
        content = "---\nname: test\n---\nbody"
        z = _make_zip({"SKILL.md": content})
        result = SkillPackageRepository.validate_package(z)
        assert not result.is_valid
        assert any("description" in e.lower() for e in result.errors)

    def test_path_traversal_detected(self):
        z = _make_zip({"SKILL.md": VALID_SKILL_MD, "../escape.py": "bad"})
        result = SkillPackageRepository.validate_package(z)
        assert not result.is_valid
        assert any("traversal" in e.lower() for e in result.errors)

    def test_absolute_path_detected(self):
        # zipfile allows absolute entries on some systems; we catch them
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("SKILL.md", VALID_SKILL_MD)
            zf.writestr("/absolute/path.py", "bad")
        result = SkillPackageRepository.validate_package(buf.getvalue())
        assert not result.is_valid

    def test_duplicate_paths_after_normalization(self):
        z = _make_zip({
            "SKILL.md": VALID_SKILL_MD,
            "scripts/run.py": "a",
            "scripts/../scripts/run.py": "b",
        })
        result = SkillPackageRepository.validate_package(z)
        assert not result.is_valid
        assert any("duplicate" in e.lower() for e in result.errors)


# ---------------------------------------------------------------------------
# validate_package — valid packages
# ---------------------------------------------------------------------------


class TestValidatePackageValid:
    def test_minimal_valid_package(self):
        z = _make_zip({"SKILL.md": VALID_SKILL_MD})
        result = SkillPackageRepository.validate_package(z)
        assert result.is_valid
        assert result.errors == []

    def test_valid_package_with_files(self):
        z = _make_zip({
            "SKILL.md": VALID_SKILL_MD,
            "scripts/run.py": "print('hi')",
            "references/schema.md": "# Schema",
        })
        result = SkillPackageRepository.validate_package(z)
        assert result.is_valid

    def test_legacy_files_prefix_allowed_in_validation(self):
        """Legacy files/ layout must pass validation (stripped on import)."""
        z = _make_zip({
            "SKILL.md": VALID_SKILL_MD,
            "files/scripts/run.py": "print('hi')",
        })
        result = SkillPackageRepository.validate_package(z)
        assert result.is_valid


# ---------------------------------------------------------------------------
# validate_package — warnings
# ---------------------------------------------------------------------------


class TestValidatePackageWarnings:
    def test_warns_on_deprecated_dependencies(self):
        content = (
            "---\nname: test-skill\ndescription: x\n"
            "dependencies:\n  - pkg1\n---\nbody"
        )
        z = _make_zip({"SKILL.md": content})
        result = SkillPackageRepository.validate_package(z)
        assert result.is_valid  # warning, not error
        assert any("dependencies" in w.lower() for w in result.warnings)

    def test_warns_on_deprecated_runtime(self):
        content = (
            "---\nname: test-skill\ndescription: x\n"
            "runtime: python-sandbox\n---\nbody"
        )
        z = _make_zip({"SKILL.md": content})
        result = SkillPackageRepository.validate_package(z)
        assert result.is_valid
        assert any("runtime" in w.lower() for w in result.warnings)

    def test_warns_on_unknown_frontmatter_key(self):
        content = (
            "---\nname: test-skill\ndescription: x\n"
            "custom_future_field: value\n---\nbody"
        )
        z = _make_zip({"SKILL.md": content})
        result = SkillPackageRepository.validate_package(z)
        assert result.is_valid
        assert any("custom_future_field" in w for w in result.warnings)

    def test_warns_on_allowed_tools(self):
        content = (
            "---\nname: test-skill\ndescription: x\n"
            "allowed-tools:\n  - python_repl\n---\nbody"
        )
        z = _make_zip({"SKILL.md": content})
        result = SkillPackageRepository.validate_package(z)
        assert result.is_valid
        assert any("allowed-tools" in w.lower() for w in result.warnings)


# ---------------------------------------------------------------------------
# DB-dependent tests (skipped in unit suite — run via integration)
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="Requires DB fixtures — run in integration test suite")
def test_import_rejects_invalid_package(db_session, app):
    z = _make_zip({"not_skill.md": "hello"})
    with pytest.raises(ValueError, match="SKILL.md"):
        SkillPackageRepository.import_package(db_session, app.app_id, z)


@pytest.mark.skip(reason="Requires DB fixtures — run in integration test suite")
def test_import_strips_dependencies(db_session, app):
    content = (
        "---\nname: test-skill\ndescription: x\n"
        "dependencies:\n  - pkg1\n---\nbody"
    )
    z = _make_zip({"SKILL.md": content})
    skill = SkillPackageRepository.import_package(db_session, app.app_id, z)
    assert skill.dependencies is None or skill.dependencies == []


@pytest.mark.skip(reason="Requires DB fixtures — run in integration test suite")
def test_import_legacy_files_prefix(db_session, app):
    z = _make_zip({
        "SKILL.md": VALID_SKILL_MD,
        "files/scripts/run.py": "print('hi')",
    })
    skill = SkillPackageRepository.import_package(db_session, app.app_id, z)
    paths = [sf.path for sf in skill.files]
    assert "scripts/run.py" in paths
    assert not any(p.startswith("files/") for p in paths)


@pytest.mark.skip(reason="Requires DB fixtures — run in integration test suite")
def test_export_skill_md_at_root(db_session, app, skill_with_files):
    zip_bytes = SkillPackageRepository.export_package(
        db_session, app.app_id, skill_with_files.skill_id
    )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
    assert "SKILL.md" in names
    assert not any(n.startswith("files/") for n in names if n != "SKILL.md")


@pytest.mark.skip(reason="Requires DB fixtures — run in integration test suite")
def test_export_does_not_include_dependencies(db_session, app, skill_with_files):
    zip_bytes = SkillPackageRepository.export_package(
        db_session, app.app_id, skill_with_files.skill_id
    )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        skill_md = zf.read("SKILL.md").decode()
    assert "dependencies" not in skill_md


@pytest.mark.skip(reason="Requires DB fixtures — run in integration test suite")
def test_get_catalog_excludes_body_and_files(db_session, app, skill_with_files):
    catalog = SkillPackageRepository.get_catalog(db_session, app.app_id)
    for item in catalog:
        assert "content" not in item
        assert "body" not in item
        assert "skill_id" in item
        assert "name" in item
