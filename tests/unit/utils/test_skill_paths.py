"""Unit tests for utils.skill_paths (pure path rules shared by SkillPackageRepository and safe_zip)."""
import pytest

from repositories.skill_package_repository import SkillPackageRepository
from utils.skill_paths import (
    MAX_PATH_LENGTH, MAX_SEGMENT_BYTES, canonical_path, canonical_segments, is_absolute_or_drive, normalize_path,
)


class TestNormalizeAccepts:
    @pytest.mark.parametrize("raw, expected", [
        ("a/b.txt", "a/b.txt"),
        ("./a/b.txt", "a/b.txt"),
        ("a\\b.txt", "a/b.txt"),
        ("a//b.txt", "a/b.txt"),
        ("100%.md", "100%.md"),
        ("references/SKILL.md", "references/SKILL.md"),
        ("docs/ñandú/概要.md", "docs/ñandú/概要.md"),
        ("ｆｕｌｌ/ｗｉｄｔｈ.md", "full/width.md"),          # NFKC folds fullwidth letters
    ])
    def test_valid(self, raw, expected):
        assert normalize_path(raw) == expected

    def test_segment_of_255_bytes_ok(self):
        seg = "a" * MAX_SEGMENT_BYTES
        assert normalize_path(seg) == seg

    def test_path_of_exactly_max_length_ok(self):
        path = "/".join(["a" * 100] * 4)
        path += "/" + "b" * (MAX_PATH_LENGTH - len(path) - 1)
        assert len(path) == MAX_PATH_LENGTH
        assert normalize_path(path) == path


class TestNormalizeRejects:
    @pytest.mark.parametrize("raw", [
        "", "   ", "/etc/passwd", "a/../../b", "..", "a/..", "~/x", "C:\\x", "c:/x",
        "a" * (MAX_PATH_LENGTH + 1),
        "a\x00b", "a\tb", "a\nb", "a\x7fb",
        "%2e%2e/%2e%2e/etc/passwd", "a%2Fb",
        "．．／．．／etc/passwd",              # fullwidth
        "a/\u2024\u2024/b",                  # one-dot leader
        "a\u200bb", "a\u200db", "a\ufeffb", "a\u202eb",   # Cf characters
        "a" * 256 + "/x", "é" * 128,          # segment > 255 UTF-8 bytes
        "a/b./c", "a/b.", "a/b /c", "a/b ", "a/ b/c", "a/ /b",
        "./", "./.", "//",
    ])
    def test_invalid(self, raw):
        with pytest.raises(ValueError):
            normalize_path(raw)

    @pytest.mark.parametrize("raw", ["SKILL.md", "skill.md", "Skill.MD", "./SKILL.md", "ＳＫＩＬＬ.md"])
    def test_root_skill_md_reserved_by_default(self, raw):
        with pytest.raises(ValueError):
            normalize_path(raw)


class TestAllowRootSkillMd:
    @pytest.mark.parametrize("raw", ["SKILL.md", "skill.md", "Skill.MD", "./SKILL.md"])
    def test_returned_canonically(self, raw):
        assert normalize_path(raw, allow_root_skill_md=True) == "SKILL.md"

    def test_nested_skill_md_is_ordinary_either_way(self):
        assert normalize_path("references/SKILL.md") == "references/SKILL.md"
        assert normalize_path("references/skill.md", allow_root_skill_md=True) == "references/skill.md"

    @pytest.mark.parametrize("raw", ["../SKILL.md", "/SKILL.md", "SKILL.md.", "SKILL.md "])
    def test_flag_does_not_relax_other_rules(self, raw):
        with pytest.raises(ValueError):
            normalize_path(raw, allow_root_skill_md=True)


class TestHelpers:
    def test_canonical_path_nfkc_and_backslash(self):
        assert canonical_path("．．／a\\b") == "../a/b"

    @pytest.mark.parametrize("canon, expected", [
        ("/x", True), ("C:/x", True), ("c:x", True), ("a/b", False), ("~/x", False),
    ])
    def test_is_absolute_or_drive(self, canon, expected):
        assert is_absolute_or_drive(canon) is expected

    def test_canonical_segments(self):
        assert canonical_segments("/a/./b//c") == (True, ["a", "b", "c"])
        assert canonical_segments("．．／x") == (False, ["..", "x"])


class TestRepositoryDelegation:
    CASES = [
        "a/b.txt", "./a/b.txt", "a\\b.txt", "100%.md", "references/SKILL.md", "é/ñ",
        "", "/etc/passwd", "a/../../b", "~/x", "C:\\x", "a" * 501, "a\x00b",
        "%2e%2e/x", "．．／x", "a/\u2024\u2024/b", "a\u200bb", "SKILL.md", "skill.md", "./SKILL.md",
        "a" * 256, "a/b.", "a/b /c", "a/ b",
    ]

    @pytest.mark.parametrize("raw", CASES)
    def test_identical_results(self, raw):
        try:
            expected = normalize_path(raw)
        except ValueError as exc:
            with pytest.raises(ValueError) as got:
                SkillPackageRepository.normalize_path(raw)
            assert str(got.value) == str(exc)
        else:
            assert SkillPackageRepository.normalize_path(raw) == expected
