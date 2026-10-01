"""Integration tests for SkillPackageRepository / SkillRepository (real PostgreSQL, savepoint isolation)."""
import hashlib
import warnings

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import IntegrityError, SAWarning

from models.skill import Skill, SkillFile
from repositories.skill_package_repository import SkillPackageRepository as Pkg
from repositories.skill_repository import SkillRepository
from tests.factories import (
    AppFactory, SkillFactory, SkillFileFactory, SystemSkillFactory, configure_factories,
)

PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"

pytestmark = pytest.mark.integration


@pytest.fixture
def skill(db):
    configure_factories(db)
    return SkillFactory()


def _row(db, skill_id, path):
    db.expire_all()
    return Pkg.get_file(db, skill_id, path)


class TestReplaceFiles:
    def test_text_and_binary_rows(self, db, skill):
        n = Pkg.replace_files(db, skill.skill_id, [
            ("docs/a.md", "héllo".encode(), "text/markdown; charset=utf-8"),
            ("img/p.png", PNG, "IMAGE/PNG"),
        ])
        assert n == 2

        text_row = _row(db, skill.skill_id, "docs/a.md")
        assert text_row.content_text == "héllo"
        assert text_row.content_bytes is None
        assert text_row.media_type == "text/markdown"
        assert text_row.checksum_sha256 == hashlib.sha256("héllo".encode()).hexdigest()

        bin_row = _row(db, skill.skill_id, "img/p.png")
        assert bin_row.content_text is None
        assert bytes(bin_row.content_bytes) == PNG
        assert bin_row.media_type == "image/png"
        assert bin_row.checksum_sha256 == hashlib.sha256(PNG).hexdigest()

    def test_empty_text_file_stored_as_empty_string(self, db, skill):
        Pkg.replace_files(db, skill.skill_id, [("empty.txt", b"", "text/plain")])
        row = _row(db, skill.skill_id, "empty.txt")
        assert row.content_text == ""
        assert row.content_bytes is None
        assert row.checksum_sha256 == hashlib.sha256(b"").hexdigest()

    def test_replaces_previous_files(self, db, skill):
        Pkg.replace_files(db, skill.skill_id, [("a.md", b"1", None), ("b.md", b"2", None)])
        Pkg.replace_files(db, skill.skill_id, [("c.md", b"3", None)])
        assert [p[0] for p in Pkg.list_paths(db, skill.skill_id)] == ["c.md"]

    def test_case_insensitive_duplicate_in_batch_raises(self, db, skill):
        with pytest.raises(ValueError):
            Pkg.replace_files(db, skill.skill_id, [("A/B.md", b"1", None), ("a/b.md", b"2", None)])

    def test_exact_duplicate_in_batch_raises(self, db, skill):
        with pytest.raises(ValueError):
            Pkg.replace_files(db, skill.skill_id, [("a.md", b"1", None), ("./a.md", b"2", None)])

    def test_media_type_over_120_chars_raises(self, db, skill):
        with pytest.raises(ValueError):
            Pkg.replace_files(db, skill.skill_id, [("a.md", b"1", "a" * 121)])

    def test_invalid_path_raises_and_leaves_existing_files(self, db, skill):
        Pkg.replace_files(db, skill.skill_id, [("keep.md", b"1", None)])
        with pytest.raises(ValueError):
            Pkg.replace_files(db, skill.skill_id, [("ok.md", b"1", None), ("../x", b"2", None)])
        assert [p[0] for p in Pkg.list_paths(db, skill.skill_id)] == ["keep.md"]

    def test_integrity_failure_is_wrapped_in_value_error(self, db):
        # Unknown skill id -> FK violation at flush, wrapped without leaking DB details.
        with db.begin_nested():
            with pytest.raises(ValueError, match="Invalid skill package contents"):
                Pkg.replace_files(db, 999_999_999, [("a.md", b"1", None)])


class TestConstraints:
    def test_duplicate_skill_id_path_raises_integrity_error(self, db, skill):
        SkillFileFactory(skill=skill, path="dup.md")
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                SkillFileFactory(skill=skill, path="dup.md")
        # outer transaction survives
        assert Pkg.count_by_skill_ids(db, [skill.skill_id]) == {skill.skill_id: 1}

    def test_same_path_in_different_skills_is_fine(self, db, skill):
        other = SkillFactory()
        SkillFileFactory(skill=skill, path="same.md")
        SkillFileFactory(skill=other, path="same.md")

    @pytest.mark.parametrize("text_value, bytes_value", [
        (None, None),
        ("t", b"b"),
    ])
    def test_xor_constraint_rejects_both_or_neither(self, db, skill, text_value, bytes_value):
        with pytest.raises(IntegrityError) as exc:
            with db.begin_nested():
                db.add(SkillFile(skill_id=skill.skill_id, path="x.bin", content_text=text_value,
                                 content_bytes=bytes_value, checksum_sha256="0" * 64))
                db.flush()
        assert "ck_skillfile_content_xor" in str(exc.value)

    def test_factory_binary_variant_satisfies_xor(self, db, skill):
        f = SkillFileFactory(skill=skill, content_bytes=PNG, media_type="image/png", path="p.png")
        assert f.content_text is None and f.content_bytes == PNG
        assert f.checksum_sha256 == hashlib.sha256(PNG).hexdigest()


class TestListAndCount:
    def test_list_paths_returns_sizes_and_is_text(self, db, skill):
        Pkg.replace_files(db, skill.skill_id, [
            ("a.md", "héllo".encode(), "text/markdown"),   # 6 bytes in UTF-8
            ("b.png", PNG, "image/png"),
            ("e.txt", b"", "text/plain"),
        ])
        db.expire_all()
        rows = {r[0]: r for r in Pkg.list_paths(db, skill.skill_id)}
        assert list(rows) == sorted(rows)  # ordered by path
        assert rows["a.md"][1:] == ("text/markdown", 6, hashlib.sha256("héllo".encode()).hexdigest(), True)
        assert rows["b.png"][1:] == ("image/png", len(PNG), hashlib.sha256(PNG).hexdigest(), False)
        assert rows["e.txt"][2] == 0 and rows["e.txt"][4] is True

    def test_list_paths_does_not_materialise_entities(self, db, skill):
        Pkg.replace_files(db, skill.skill_id, [("a.md", b"x", None)])
        db.expire_all()
        rows = Pkg.list_paths(db, skill.skill_id)
        assert all(isinstance(r, tuple) for r in rows)
        assert not any(isinstance(o, SkillFile) for o in db.identity_map.values())

    def test_content_columns_are_deferred_on_plain_queries(self, db, skill):
        Pkg.replace_files(db, skill.skill_id, [("a.md", b"x", None)])
        db.expire_all()
        obj = db.query(SkillFile).filter(SkillFile.skill_id == skill.skill_id).one()
        unloaded = sa_inspect(obj).unloaded
        assert {"content_text", "content_bytes"} <= unloaded

    def test_get_file_and_list_files_load_content(self, db, skill):
        Pkg.replace_files(db, skill.skill_id, [("a.md", b"x", None), ("b.png", PNG, "image/png")])
        db.expire_all()
        got = Pkg.get_file(db, skill.skill_id, "a.md")
        assert not ({"content_text", "content_bytes"} & sa_inspect(got).unloaded)
        assert Pkg.get_file(db, skill.skill_id, "missing.md") is None
        files = Pkg.list_files(db, skill.skill_id)
        assert [f.path for f in files] == ["a.md", "b.png"]

    def test_count_by_skill_ids_grouped(self, db, skill):
        other = SkillFactory()
        empty = SkillFactory()
        Pkg.replace_files(db, skill.skill_id, [("a.md", b"1", None), ("b.md", b"2", None)])
        Pkg.replace_files(db, other.skill_id, [("a.md", b"1", None)])
        counts = Pkg.count_by_skill_ids(db, [skill.skill_id, other.skill_id, empty.skill_id])
        assert counts == {skill.skill_id: 2, other.skill_id: 1}

    def test_count_by_skill_ids_empty_input(self, db):
        assert Pkg.count_by_skill_ids(db, []) == {}


class TestDeletion:
    def test_delete_all_for_skill_no_warning_with_preloaded_files(self, db, skill):
        Pkg.replace_files(db, skill.skill_id, [("a.md", b"1", None), ("b.md", b"2", None)])
        db.commit()
        assert len(skill.files) == 2  # preload the collection
        with warnings.catch_warnings():
            warnings.simplefilter("error", SAWarning)
            deleted = Pkg.delete_all_for_skill(db, skill.skill_id)
            db.flush()
            assert skill.files == []
        assert deleted == 2

    def test_skill_repository_delete_removes_files_no_warning(self, db, skill):
        Pkg.replace_files(db, skill.skill_id, [("a.md", b"1", None), ("b.md", b"2", None)])
        db.commit()
        skill_id = skill.skill_id
        assert len(skill.files) == 2  # preload
        with warnings.catch_warnings():
            warnings.simplefilter("error", SAWarning)
            SkillRepository.delete(db, skill)
        assert db.query(Skill).filter(Skill.skill_id == skill_id).count() == 0
        assert db.query(SkillFile).filter(SkillFile.skill_id == skill_id).count() == 0

    def test_delete_by_id_and_app_id(self, db, skill):
        Pkg.replace_files(db, skill.skill_id, [("a.md", b"1", None)])
        assert SkillRepository.delete_by_id_and_app_id(db, skill.skill_id, skill.app_id) is True
        assert SkillRepository.delete_by_id_and_app_id(db, skill.skill_id, skill.app_id) is False

    def test_delete_by_other_app_does_not_delete(self, db, skill):
        other_app = AppFactory()
        assert SkillRepository.delete_by_id_and_app_id(db, skill.skill_id, other_app.app_id) is False
        assert db.query(Skill).filter(Skill.skill_id == skill.skill_id).count() == 1


class TestSystemSkills:
    def test_by_name_case_insensitive(self, db):
        configure_factories(db)
        s = SystemSkillFactory(name="Mixed-Case")
        assert SkillRepository.get_system_skill_by_name(db, "mixed-case").skill_id == s.skill_id
        assert SkillRepository.get_system_skill_by_name(db, "  MIXED-CASE ").skill_id == s.skill_id
        assert SkillRepository.get_system_skill_by_name(db, "other") is None

    def test_by_name_ignores_app_skills(self, db):
        configure_factories(db)
        SkillFactory(name="only-app")
        assert SkillRepository.get_system_skill_by_name(db, "only-app") is None

    def test_enabled_only_semantics(self, db):
        configure_factories(db)
        s = SystemSkillFactory(name="off-skill", is_enabled=False)
        assert SkillRepository.get_system_skill_by_name(db, "off-skill").skill_id == s.skill_id
        assert SkillRepository.get_system_skill_by_name(db, "off-skill", enabled_only=True) is None
        assert SkillRepository.get_system_skill_by_id(db, s.skill_id).skill_id == s.skill_id
        assert SkillRepository.get_system_skill_by_id(db, s.skill_id, enabled_only=True) is None
        assert s.skill_id not in {x.skill_id for x in SkillRepository.get_system_skills(db)}
        assert s.skill_id in {x.skill_id for x in SkillRepository.get_system_skills(db, enabled_only=False)}

    def test_system_by_id_ignores_app_skill(self, db, skill):
        assert SkillRepository.get_system_skill_by_id(db, skill.skill_id) is None

    def test_by_name_uses_canonical_whitespace_folding_not_plain_lower(self, db):
        """Review-round Finding 4: get_system_skill_by_name must use the same
        whitespace-folding rule (utils.skill_names.fold_name / _fold_col) as every
        other skill-name collision check, not a bare `func.lower(name)` — otherwise
        "data analysis" and "data-analysis" would be treated as distinct names here
        while `resolve_agent_skills`'s Python-side fold_name dedupe treats them as the
        same, causing one to be silently dropped from an agent's prompt.
        """
        configure_factories(db)
        s = SystemSkillFactory(name="data analysis")
        # A differently-whitespaced variant that folds to the exact same canonical name
        # must still be found by this collision check.
        assert SkillRepository.get_system_skill_by_name(db, "data-analysis").skill_id == s.skill_id
        assert SkillRepository.get_system_skill_by_name(db, "data   analysis").skill_id == s.skill_id

    def test_system_names_unique_case_insensitively(self, db):
        configure_factories(db)
        SystemSkillFactory(name="X")
        with pytest.raises(IntegrityError) as exc:
            with db.begin_nested():
                SystemSkillFactory(name="x")
        assert "uq_skill_system_name" in str(exc.value)

    def test_app_skill_may_share_name_with_system_skill(self, db):
        configure_factories(db)
        SystemSkillFactory(name="shared")
        app_skill = SkillFactory(name="shared")
        assert app_skill.skill_id is not None

    def test_same_name_in_two_apps_is_fine(self, db):
        configure_factories(db)
        SkillFactory(name="dup")
        SkillFactory(name="dup")


class TestScoping:
    def test_app_id_none_raises(self, db):
        with pytest.raises(ValueError):
            SkillRepository.get_all_by_app_id(db, None)
        with pytest.raises(ValueError):
            SkillRepository.get_by_id_and_app_id(db, 1, None)

    def test_get_by_id_and_app_id_is_scoped(self, db, skill):
        other_app = AppFactory()
        assert SkillRepository.get_by_id_and_app_id(db, skill.skill_id, skill.app_id).skill_id == skill.skill_id
        assert SkillRepository.get_by_id_and_app_id(db, skill.skill_id, other_app.app_id) is None

    def test_get_all_by_app_excludes_system_skills(self, db, skill):
        SystemSkillFactory()
        assert [s.skill_id for s in SkillRepository.get_all_by_app_id(db, skill.app_id)] == [skill.skill_id]
