"""Unit tests for the pure functions of SkillPackageRepository (no database)."""
import hashlib

import pytest

from repositories.skill_package_repository import SkillPackageRepository as Repo

PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"


class TestNormalizePathAccepts:
    @pytest.mark.parametrize("raw, expected", [
        ("a/b.txt", "a/b.txt"),
        ("./a/b.txt", "a/b.txt"),
        ("a\\b.txt", "a/b.txt"),
        ("a//b.txt", "a/b.txt"),
        ("100%.md", "100%.md"),
        ("references/SKILL.md", "references/SKILL.md"),
        ("docs/ñandú/概要.md", "docs/ñandú/概要.md"),
        ("scripts/run.py", "scripts/run.py"),
    ])
    def test_valid_paths(self, raw, expected):
        assert Repo.normalize_path(raw) == expected

    def test_segment_of_exactly_255_bytes_is_accepted(self):
        seg = "a" * 255
        assert Repo.normalize_path(f"x/{seg}") == f"x/{seg}"

    def test_path_of_exactly_500_chars_is_accepted(self):
        path = "/".join(["a" * 100] * 4)          # 4*100 + 3 separators = 403
        path += "/" + "b" * (500 - len(path) - 1)
        assert len(path) == 500
        assert Repo.normalize_path(path) == path


class TestNormalizePathRejects:
    @pytest.mark.parametrize("raw", [
        "",
        "   ",
        "/etc/passwd",
        "a/../../b",
        "..",
        "a/..",
        "~/x",
        "C:\\x",
        "c:/x",
        "a" * 501,
        "a\x00b",
        "a\tb",
        "a\nb",
        "a\x7fb",
        "%2e%2e/%2e%2e/etc/passwd",
        "a%2Fb",
        "．．／．．／etc/passwd",          # fullwidth dots and slashes (NFKC -> ../..)
        "a/\u2024\u2024/b",              # one-dot leader (NFKC -> ..)
        "a\u200bb",                       # zero-width space
        "a\u200db",                       # zero-width joiner
        "a\ufeffb",                       # BOM / zero-width no-break space
        "a\u202eb",                       # right-to-left override
        "SKILL.md",
        "skill.md",
        "Skill.MD",
        "./SKILL.md",
        "a" * 256 + "/x",
        "é" * 128,                        # 256 UTF-8 bytes in one segment
        "a/b./c",
        "a/b /c",
        "a/b ",
        "a/b.",
        "a/ /b",
    ])
    def test_invalid_paths(self, raw):
        with pytest.raises(ValueError):
            Repo.normalize_path(raw)


class TestComputeChecksum:
    def test_known_vector(self):
        assert Repo.compute_checksum(b"abc") == (
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        )

    def test_empty(self):
        assert Repo.compute_checksum(b"") == hashlib.sha256(b"").hexdigest()


class TestClassify:
    def test_utf8_markdown_is_text(self):
        assert Repo.classify("a.md", "héllo".encode(), "text/markdown") == ("text", "héllo")

    def test_png_magic_is_binary(self):
        assert Repo.classify("img.png", PNG, "image/png") == ("binary", PNG)

    def test_png_magic_without_media_type_is_binary(self):
        assert Repo.classify("img", PNG, None)[0] == "binary"

    def test_txt_with_nul_is_binary(self):
        data = b"abc\x00def"
        assert Repo.classify("a.txt", data, "text/plain") == ("binary", data)

    def test_invalid_utf8_is_binary(self):
        data = b"\xff\xfe\xfa"
        assert Repo.classify("a.txt", data, "text/plain") == ("binary", data)

    def test_application_json_is_text(self):
        assert Repo.classify("data", b'{"a": 1}', "application/json") == ("text", '{"a": 1}')

    def test_media_type_params_and_case_are_ignored(self):
        assert Repo.classify("x", b"hi", "Text/Plain; charset=utf-8") == ("text", "hi")

    def test_structured_suffix_is_text(self):
        assert Repo.classify("x", b"{}", "application/ld+json")[0] == "text"

    def test_empty_text_file_is_text_empty_string(self):
        assert Repo.classify("a.txt", b"", "text/plain") == ("text", "")

    def test_extension_hint_without_media_type(self):
        assert Repo.classify("run.PY", b"print(1)", None) == ("text", "print(1)")

    def test_unknown_type_and_extension_is_binary(self):
        assert Repo.classify("blob.bin", b"plain ascii", "application/octet-stream")[0] == "binary"


class TestNormalizeMediaType:
    @pytest.mark.parametrize("raw, expected", [
        (None, None),
        ("", None),
        ("   ", None),
        (";charset=utf-8", None),
        ("text/plain; charset=utf-8", "text/plain"),
        ("  Text/Markdown  ", "text/markdown"),
        ("IMAGE/PNG", "image/png"),
    ])
    def test_normalisation(self, raw, expected):
        assert Repo._normalize_media_type(raw) == expected

    def test_120_chars_accepted(self):
        mt = "a" * 120
        assert Repo._normalize_media_type(mt) == mt

    def test_over_120_chars_raises(self):
        with pytest.raises(ValueError):
            Repo._normalize_media_type("a" * 121)

    def test_length_measured_after_params_stripped(self):
        assert Repo._normalize_media_type("text/plain;" + "x" * 300) == "text/plain"
