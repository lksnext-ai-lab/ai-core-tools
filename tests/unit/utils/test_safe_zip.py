"""Unit tests for utils.safe_zip (hardened in-memory zip reader). Archives are built in memory; no DB."""
import io
import os
import stat
import struct
import time
import zipfile

import pytest

from utils import safe_zip
from utils.safe_zip import (
    REASON_ABSOLUTE_PATH, REASON_ARCHIVE_TOO_LARGE, REASON_DUPLICATE, REASON_ENCRYPTED, REASON_FILE_TOO_LARGE,
    REASON_INVALID_ARCHIVE, REASON_INVALID_PATH, REASON_NO_SKILL_MD, REASON_RATIO, REASON_SYMLINK,
    REASON_TOO_MANY_ENTRIES, REASON_TOO_MANY_FILES, REASON_TOTAL_TOO_LARGE, REASON_TRAVERSAL,
    REASON_UNSUPPORTED_COMPRESSION, SafeZipError, SafeZipPackage, find_package_root, find_plugin_root,
    iter_safe_zip, read_safe_zip, strip_package_root,
)

SKILL = b"---\nname: x\n---\nbody\n"


def make_zip(entries, compression=zipfile.ZIP_DEFLATED, comment=b"") -> bytes:
    """entries: iterable of (name, data) or (name, data, external_attr)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression) as zf:
        for entry in entries:
            name, data = entry[0], entry[1]
            zi = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            zi.compress_type = compression
            if len(entry) > 2:
                zi.external_attr = entry[2]
            zf.writestr(zi, data)
        zf.comment = comment
    return buf.getvalue()


def reason_of(data: bytes, **limits) -> str:
    with pytest.raises(SafeZipError) as exc:
        list(iter_safe_zip(data, **limits))
    return exc.value.reason


def mark_encrypted(data: bytes) -> bytes:
    b = bytearray(data)
    pos = b.find(b"PK\x01\x02")
    while pos != -1:
        flags = struct.unpack_from("<H", b, pos + 8)[0]
        struct.pack_into("<H", b, pos + 8, flags | 0x1)
        pos = b.find(b"PK\x01\x02", pos + 4)
    return bytes(b)


def eocd(entries=1, cd_size=0, cd_off=0, comment_len=0, disk=0) -> bytes:
    return b"PK\x05\x06" + struct.pack("<HHHHIIH", disk, disk, entries, entries, cd_size, cd_off, comment_len)


def zip64_rec(entries: int, cd_size: int = 0, cd_off: int = 0) -> bytes:
    return b"PK\x06\x06" + struct.pack("<QHHIIQQQQ", 44, 45, 45, 0, 0, entries, entries, cd_size, cd_off)


def zip64_locator(rec_offset: int) -> bytes:
    return b"PK\x06\x07" + struct.pack("<IQI", 0, rec_offset, 1)


class TestErrorType:
    def test_not_a_value_error(self):
        assert not issubclass(SafeZipError, ValueError)

    def test_message_repr_escapes_entry_and_limit(self):
        e = SafeZipError("r", limit="5", entry="a\nb\u2028\x1b")
        s = str(e)
        assert all(ord(c) >= 0x20 for c in s) and "\u2028" not in s
        assert "(limit 5)" in s and e.limit == "5"

    def test_entry_truncated(self):
        assert len(SafeZipError("r", entry="a" * 1000).entry) == 200


class TestValidArchives:
    def test_without_package_root(self):
        pkg = read_safe_zip(make_zip([("SKILL.md", SKILL), ("a.py", b"print(1)"), ("d/b.txt", b"b")]))
        assert isinstance(pkg, SafeZipPackage)
        assert pkg.skill_md == SKILL
        assert pkg.files == {"a.py": b"print(1)", "d/b.txt": b"b"}

    def test_with_package_root_is_stripped(self):
        pkg = read_safe_zip(make_zip([("pkg/SKILL.md", SKILL), ("pkg/a.py", b"1"), ("pkg/d/b", b"2")]))
        assert pkg.skill_md == SKILL
        assert pkg.files == {"a.py": b"1", "d/b": b"2"}

    def test_junk_and_directory_entries_skipped(self):
        data = make_zip([
            ("pkg/", b""), ("pkg/SKILL.md", SKILL), ("pkg/sub/", b""), ("pkg/a.py", b"1"),
            ("__MACOSX/pkg/._a.py", b"junk"), ("pkg/.DS_Store", b"junk"), (".git/config", b"junk"),
            ("pkg/.git/HEAD", b"junk"),
        ])
        assert read_safe_zip(data).files == {"a.py": b"1"}

    def test_iter_yields_normalised_names(self):
        names = [n for n, _ in iter_safe_zip(make_zip([("./pkg\\SKILL.md", SKILL), ("pkg//a.py", b"1")]))]
        assert names == ["pkg/SKILL.md", "pkg/a.py"]

    def test_root_skill_md_any_case(self):
        assert read_safe_zip(make_zip([("skill.md", SKILL)])).skill_md == SKILL

    def test_only_root_skill_md_excluded_from_files(self):
        pkg = read_safe_zip(make_zip([
            ("pkg/SKILL.md", SKILL), ("pkg/references/SKILL.md", b"nested"), ("pkg/skill.md.bak", b"x"),
        ]))
        assert pkg.files == {"references/SKILL.md": b"nested", "skill.md.bak": b"x"}

    def test_empty_file_content(self):
        assert read_safe_zip(make_zip([("SKILL.md", SKILL), ("empty", b"")])).files == {"empty": b""}

    def test_stored_compression_ok(self):
        assert read_safe_zip(make_zip([("SKILL.md", SKILL)], zipfile.ZIP_STORED)).skill_md == SKILL


class TestPathRejections:
    CASES = {
        "absolute": ("/etc/passwd", REASON_ABSOLUTE_PATH),
        "drive": ("C:/x/y", REASON_ABSOLUTE_PATH),
        "dotdot": ("a/../../b", REASON_TRAVERSAL),
        "backslash_traversal": ("a\\..\\..\\b", REASON_TRAVERSAL),
        "fullwidth": ("．．／．．／etc/passwd", REASON_TRAVERSAL),
        "one_dot_leader": ("a/\u2024\u2024/b", REASON_TRAVERSAL),
        "percent": ("a/%2e%2e/b", REASON_INVALID_PATH),
        "control": ("a/b\nc", REASON_INVALID_PATH),
        "trailing_dot": ("a/b.", REASON_INVALID_PATH),
    }

    @pytest.mark.parametrize("name, expected", list(CASES.values()), ids=list(CASES))
    def test_rejected_with_expected_reason(self, name, expected):
        assert reason_of(make_zip([("SKILL.md", SKILL), (name, b"x")])) == expected

    def test_traversal_hidden_behind_package_root(self):
        assert reason_of(make_zip([("pkg/../SKILL.md", SKILL)])) == REASON_TRAVERSAL
        assert reason_of(make_zip([("pkg/SKILL.md", SKILL), ("pkg/../../x", b"x")])) == REASON_TRAVERSAL

    def test_error_message_repr_escapes_hostile_names(self):
        with pytest.raises(SafeZipError) as exc:
            list(iter_safe_zip(make_zip([("SKILL.md", SKILL), ("a\x1b[31m\nb\u202e", b"x")])))
        msg = str(exc.value)
        assert all(ord(c) >= 0x20 for c in msg) and "\u202e" not in msg
        assert "\\x1b" in msg or "\\n" in msg


class TestEntryRejections:
    def test_symlink(self):
        data = make_zip([("SKILL.md", SKILL), ("link", b"/etc/passwd", (stat.S_IFLNK | 0o777) << 16)])
        assert reason_of(data) == REASON_SYMLINK

    def test_regular_file_mode_not_symlink(self):
        data = make_zip([("SKILL.md", SKILL), ("f", b"x", (stat.S_IFREG | 0o644) << 16)])
        assert "f" in read_safe_zip(data).files

    def test_encrypted_flag(self):
        assert reason_of(mark_encrypted(make_zip([("SKILL.md", SKILL)]))) == REASON_ENCRYPTED

    def test_duplicate_names_case_insensitive(self):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # zipfile warns about the exact duplicate
            data = make_zip([("SKILL.md", SKILL), ("a/B.txt", b"1"), ("a/b.TXT", b"2")])
        assert reason_of(data) == REASON_DUPLICATE

    def test_duplicate_after_normalisation(self):
        assert reason_of(make_zip([("SKILL.md", SKILL), ("a/b", b"1"), ("./a\\b", b"2")])) == REASON_DUPLICATE

    @pytest.mark.parametrize("method", [zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA])
    def test_unsupported_compression(self, method):
        assert reason_of(make_zip([("SKILL.md", SKILL)], method)) == REASON_UNSUPPORTED_COMPRESSION

    def test_all_failure_reasons_are_distinct(self):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            reasons = {
                reason_of(make_zip([("SKILL.md", SKILL), ("/x", b"1")])),
                reason_of(make_zip([("SKILL.md", SKILL), ("../x", b"1")])),
                reason_of(make_zip([("SKILL.md", SKILL), ("l", b"1", (stat.S_IFLNK | 0o777) << 16)])),
                reason_of(mark_encrypted(make_zip([("SKILL.md", SKILL)]))),
                reason_of(make_zip([("SKILL.md", SKILL), ("a", b"1"), ("A", b"2")])),
                reason_of(make_zip([("SKILL.md", SKILL)], zipfile.ZIP_BZIP2)),
                reason_of(make_zip([("a", b"1")])),
                reason_of(b"not a zip at all" * 5),
            }
        assert len(reasons) == 8

    def test_garbage_is_invalid_archive(self):
        assert reason_of(b"x" * 100) == REASON_INVALID_ARCHIVE
        assert reason_of(b"") == REASON_INVALID_ARCHIVE

    def test_truncated_archive_is_invalid(self):
        data = make_zip([("SKILL.md", SKILL), ("a", b"x" * 100)])
        assert reason_of(data[: len(data) // 2]) == REASON_INVALID_ARCHIVE

    def test_corrupt_member_data_is_invalid_archive_not_raw_exception(self):
        raw = bytearray(make_zip([("SKILL.md", SKILL), ("a.bin", os.urandom(200))], zipfile.ZIP_STORED))
        i = raw.find(b"a.bin") + 5 + 10
        raw[i] ^= 0xFF
        with pytest.raises(SafeZipError) as exc:
            read_safe_zip(bytes(raw))
        assert exc.value.reason == REASON_INVALID_ARCHIVE


class TestCountAndSizeLimits:
    @staticmethod
    def _files(n, first=SKILL):
        return [("SKILL.md", first)] + [(f"f{i}.txt", b"x") for i in range(n - 1)]

    def test_500_files_accepted(self):
        assert len(read_safe_zip(make_zip(self._files(500)), max_files=500).files) == 499

    def test_501_files_rejected(self):
        assert reason_of(make_zip(self._files(501)), max_files=500) == REASON_TOO_MANY_FILES

    def test_directories_and_junk_do_not_count(self):
        entries = self._files(3) + [(f"d{i}/", b"") for i in range(6)] + [("__MACOSX/x", b"")]
        assert len(read_safe_zip(make_zip(entries), max_files=3).files) == 2

    def test_entry_count_hard_cap(self):
        entries = self._files(2) + [(f"d{i}/", b"") for i in range(50)]
        assert reason_of(make_zip(entries), max_files=5) == REASON_TOO_MANY_ENTRIES

    def test_per_file_limit_exact_boundary(self):
        ok = make_zip([("SKILL.md", SKILL), ("f", os.urandom(1000))], zipfile.ZIP_STORED)
        assert len(read_safe_zip(ok, max_file_bytes=1000).files["f"]) == 1000
        bad = make_zip([("SKILL.md", SKILL), ("f", os.urandom(1001))], zipfile.ZIP_STORED)
        assert reason_of(bad, max_file_bytes=1000) == REASON_FILE_TOO_LARGE

    def test_total_limit_exact_boundary(self):
        skill = b"s" * 100
        ok = make_zip([("SKILL.md", skill), ("a", b"a" * 450), ("b", b"b" * 450)], zipfile.ZIP_STORED)
        assert len(read_safe_zip(ok, max_total_bytes=1000).files) == 2
        bad = make_zip([("SKILL.md", skill), ("a", b"a" * 450), ("b", b"b" * 451)], zipfile.ZIP_STORED)
        assert reason_of(bad, max_total_bytes=1000) == REASON_TOTAL_TOO_LARGE

    def test_archive_size_cap(self):
        data = make_zip([("SKILL.md", SKILL)], zipfile.ZIP_STORED)
        assert read_safe_zip(data, max_archive_bytes=len(data)).skill_md == SKILL
        assert reason_of(data, max_archive_bytes=len(data) - 1) == REASON_ARCHIVE_TOO_LARGE

    def test_archive_cap_checked_before_any_parsing(self):
        assert reason_of(b"garbage" * 100, max_archive_bytes=10) == REASON_ARCHIVE_TOO_LARGE

    def test_limits_default_to_settings(self, monkeypatch):
        monkeypatch.setattr(safe_zip.settings, "SKILL_IMPORT_MAX_FILES", 1)
        assert reason_of(make_zip(self._files(2))) == REASON_TOO_MANY_FILES


class TestRatio:
    def test_honest_bomb_rejected(self):
        data = make_zip([("SKILL.md", SKILL), ("zeros", b"\x00" * (5 * 1024 * 1024))])
        assert len(data) < 20_000
        assert reason_of(data, max_file_bytes=10**9, max_total_bytes=10**9) == REASON_RATIO

    def test_floor_lets_small_repetitive_file_pass(self):
        data = make_zip([("SKILL.md", SKILL), ("divider.md", b"=" * 3000)])
        assert len(read_safe_zip(data).files["divider.md"]) == 3000

    def test_ballast_is_bounded_by_absolute_caps(self):
        # Incompressible ballast inflates the archive so the ratio stays low; absolute caps still bind.
        data = make_zip(
            [("SKILL.md", SKILL), ("ballast", os.urandom(300_000)), ("zeros", b"\x00" * (3 * 1024 * 1024))]
        )
        assert len(data) / 1 * 100 > 3 * 1024 * 1024  # ratio check alone would let this through
        assert reason_of(data, max_total_bytes=1024 * 1024, max_file_bytes=10**9) == REASON_TOTAL_TOO_LARGE
        assert reason_of(data, max_file_bytes=1024 * 1024, max_total_bytes=10**9) == REASON_FILE_TOO_LARGE

    def test_ratio_override(self):
        data = make_zip([("SKILL.md", SKILL), ("zeros", b"\x00" * (2 * 1024 * 1024))])
        assert reason_of(data, max_ratio=2.0) == REASON_RATIO
        assert len(read_safe_zip(data, max_ratio=100000.0).files["zeros"]) == 2 * 1024 * 1024


class TestEocdChecks:
    def test_zip64_count_lying_against_32bit_entries_rejected_fast(self):
        blob = zip64_rec(2**40)
        blob += zip64_locator(0)
        blob += eocd(entries=1, cd_size=46, cd_off=0)
        start = time.monotonic()
        assert reason_of(blob) == REASON_TOO_MANY_ENTRIES
        assert time.monotonic() - start < 1.0

    def test_zip64_cd_size_lying_rejected(self):
        blob = zip64_rec(1, cd_size=2**40) + zip64_locator(0) + eocd(entries=1, cd_size=46)
        assert reason_of(blob) == REASON_TOO_MANY_ENTRIES

    def test_32bit_entry_count_over_cap_rejected(self):
        assert reason_of(eocd(entries=60000, cd_size=10), max_files=500) == REASON_TOO_MANY_ENTRIES

    def test_32bit_cd_size_over_cap_rejected(self):
        assert reason_of(eocd(entries=1, cd_size=0xFFFFFFF0), max_files=500) == REASON_TOO_MANY_ENTRIES

    def test_sentinel_without_zip64_record_rejected(self):
        assert reason_of(eocd(entries=0xFFFF, cd_size=0xFFFFFFFF, cd_off=0xFFFFFFFF)) == REASON_INVALID_ARCHIVE
        assert reason_of(eocd(entries=1, cd_size=0xFFFFFFFF)) == REASON_INVALID_ARCHIVE

    def test_no_eocd_rejected(self):
        assert reason_of(b"PK\x03\x04" + b"\x00" * 100) == REASON_INVALID_ARCHIVE

    def test_spec_valid_always_zip64_archive_accepted(self):
        base = make_zip([("SKILL.md", SKILL), ("a.txt", b"hello")])
        idx = base.rfind(b"PK\x05\x06")
        entries, cd_size, cd_off = struct.unpack_from("<HII", base, idx + 10)
        assert entries == 2
        body = base[:idx]
        rec_off = len(body)
        tail = zip64_rec(entries, cd_size, cd_off) + zip64_locator(rec_off) + eocd(0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF)
        data = body + tail
        with zipfile.ZipFile(io.BytesIO(data)) as zf:  # sanity: the stdlib itself reads it
            assert sorted(zf.namelist()) == ["SKILL.md", "a.txt"]
        pkg = read_safe_zip(data)
        assert pkg.skill_md == SKILL and pkg.files == {"a.txt": b"hello"}

    def test_locator_pointing_at_fake_small_record_still_rejected(self):
        fake_small = zip64_rec(1)
        visible_huge = zip64_rec(2**40)
        blob = fake_small + visible_huge + zip64_locator(0) + eocd(entries=1)
        assert reason_of(blob) == REASON_TOO_MANY_ENTRIES

    def test_fake_eocd_in_comment_field(self):
        fake = eocd(entries=60000, cd_size=10)
        data = make_zip([("SKILL.md", SKILL)], comment=b"x" + fake)
        assert reason_of(data, max_files=500) in (REASON_TOO_MANY_ENTRIES, REASON_INVALID_ARCHIVE)

    def test_legitimate_comment_accepted(self):
        data = make_zip([("SKILL.md", SKILL)], comment=b"just a comment")
        assert read_safe_zip(data).skill_md == SKILL


class TestNoSkillMd:
    def test_missing_skill_md(self):
        assert reason_of(make_zip([("a.txt", b"x")])) == REASON_NO_SKILL_MD

    def test_empty_archive(self):
        assert reason_of(make_zip([])) == REASON_NO_SKILL_MD

    def test_only_junk_and_dirs(self):
        assert reason_of(make_zip([("d/", b""), ("__MACOSX/x", b"y")])) == REASON_NO_SKILL_MD

    def test_two_top_level_dirs(self):
        assert reason_of(make_zip([("a/SKILL.md", SKILL), ("b/x", b"y")])) == REASON_NO_SKILL_MD

    def test_skill_md_not_directly_under_single_root(self):
        assert reason_of(make_zip([("pkg/sub/SKILL.md", SKILL)])) == REASON_NO_SKILL_MD

    def test_rooted_but_stray_root_level_file(self):
        assert reason_of(make_zip([("pkg/SKILL.md", SKILL), ("README", b"x")])) == REASON_NO_SKILL_MD

    def test_rejected_before_any_decompression(self):
        # A ratio bomb that would only trip during streaming: the metadata-phase error must win.
        data = make_zip([("zeros", b"\x00" * (5 * 1024 * 1024))])
        assert reason_of(data) == REASON_NO_SKILL_MD


class TestEagerSemantics:
    def test_phase1_failure_raises_at_call_not_first_iteration(self):
        bad = make_zip([("SKILL.md", SKILL), ("/abs", b"x")])
        with pytest.raises(SafeZipError):
            iter_safe_zip(bad)  # no iteration

    def test_no_skill_md_raises_at_call(self):
        with pytest.raises(SafeZipError):
            iter_safe_zip(make_zip([("a", b"x")]))

    def test_archive_cap_raises_at_call(self):
        with pytest.raises(SafeZipError):
            iter_safe_zip(make_zip([("SKILL.md", SKILL)]), max_archive_bytes=1)

    def test_success_returns_iterator_lazily(self):
        it = iter_safe_zip(make_zip([("SKILL.md", SKILL)]))
        assert iter(it) is it
        assert list(it) == [("SKILL.md", SKILL)]

    def test_streaming_failure_only_surfaces_on_iteration(self):
        data = make_zip([("SKILL.md", SKILL), ("z", b"\x00" * (5 * 1024 * 1024))])
        it = iter_safe_zip(data, max_file_bytes=10**9, max_total_bytes=10**9)  # does not raise yet
        with pytest.raises(SafeZipError) as exc:
            list(it)
        assert exc.value.reason == REASON_RATIO

    @pytest.fixture
    def opened(self, monkeypatch):
        instances = []
        real = zipfile.ZipFile

        class Recording(real):
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                instances.append(self)

        monkeypatch.setattr(safe_zip.zipfile, "ZipFile", Recording)
        return instances

    def test_zipfile_closed_on_phase1_failure(self, opened):
        data = make_zip([("SKILL.md", SKILL), ("/abs", b"x")])
        opened.clear()
        with pytest.raises(SafeZipError):
            iter_safe_zip(data)
        assert len(opened) == 1 and opened[0].fp is None

    def test_zipfile_closed_on_missing_skill_md(self, opened):
        data = make_zip([("a", b"x")])
        opened.clear()
        with pytest.raises(SafeZipError):
            iter_safe_zip(data)
        assert opened[0].fp is None

    def test_zipfile_closed_after_full_iteration(self, opened):
        data = make_zip([("SKILL.md", SKILL)])
        opened.clear()
        list(iter_safe_zip(data))
        assert opened[0].fp is None

    def test_zipfile_closed_after_streaming_failure(self, opened):
        data = make_zip([("SKILL.md", SKILL), ("f", b"x" * 100)])
        opened.clear()
        with pytest.raises(SafeZipError):
            list(iter_safe_zip(data, max_file_bytes=10))
        assert opened[0].fp is None

    def test_zipfile_closed_when_generator_abandoned(self, opened):
        data = make_zip([("SKILL.md", SKILL), ("a", b"1")])
        opened.clear()
        it = iter_safe_zip(data)
        next(it)
        it.close()
        assert opened[0].fp is None


class TestFindAndStripRoot:
    @pytest.mark.parametrize("paths, expected", [
        (["SKILL.md", "a.py"], ""),
        (["skill.md"], ""),
        (["pkg/SKILL.md", "pkg/a.py"], "pkg"),
        (["PKG/skill.md", "PKG/x/y"], "PKG"),
        (["SKILL.md", "other/x"], ""),
    ])
    def test_find(self, paths, expected):
        assert find_package_root(paths) == expected

    @pytest.mark.parametrize("paths", [
        [], ["a.py"], ["pkg/a.py"], ["a/SKILL.md", "b/SKILL.md"], ["pkg/SKILL.md", "README"], ["pkg/sub/SKILL.md"],
    ])
    def test_find_raises(self, paths):
        with pytest.raises(SafeZipError) as exc:
            find_package_root(paths)
        assert exc.value.reason == REASON_NO_SKILL_MD

    @pytest.mark.parametrize("name, root, expected", [
        ("pkg/a.py", "pkg", "a.py"),
        ("pkg/d/e.txt", "pkg", "d/e.txt"),
        ("pkg/SKILL.md", "pkg", None),
        ("pkg/skill.md", "pkg", None),
        ("pkg/references/SKILL.md", "pkg", "references/SKILL.md"),
        ("SKILL.md", "", None),
        ("a.py", "", "a.py"),
        ("references/SKILL.md", "", "references/SKILL.md"),
    ])
    def test_strip(self, name, root, expected):
        assert strip_package_root(name, root) == expected

    @pytest.mark.parametrize("name, root", [("other/a", "pkg"), ("pkgx/a", "pkg"), ("pkg", "pkg"), ("pkg/x.", "pkg")])
    def test_strip_raises(self, name, root):
        with pytest.raises(SafeZipError) as exc:
            strip_package_root(name, root)
        assert exc.value.reason == REASON_INVALID_PATH

    def test_strip_error_repr_escapes(self):
        with pytest.raises(SafeZipError) as exc:
            strip_package_root("evil\nname/a", "pkg")
        assert "\n" not in str(exc.value)


class TestFindPluginRoot:
    """Regression coverage for the three real-world Claude plugin archive shapes (step_035 review fix)."""

    def test_bare_skills_dir_needs_no_stripping(self):
        paths = ["skills/alpha/SKILL.md", "skills/alpha/refs/notes.md", "skills/beta/SKILL.md"]
        assert find_plugin_root(paths) == ""

    def test_wrapped_top_level_directory_is_stripped(self):
        # zip -r plugin.zip my-plugin/  (or a GitHub "Download ZIP" of a plugin repo)
        paths = [
            "my-plugin/skills/alpha/SKILL.md",
            "my-plugin/skills/alpha/refs/notes.md",
            "my-plugin/.claude-plugin/plugin.json",
        ]
        assert find_plugin_root(paths) == "my-plugin"

    def test_case_insensitive_skills_directory_needs_no_stripping(self):
        paths = ["Skills/alpha/SKILL.md", "Skills/alpha/refs/notes.md"]
        assert find_plugin_root(paths) == ""

    def test_case_insensitive_wrapped_skills_directory_is_stripped(self):
        paths = ["repo-main/Skills/alpha/SKILL.md"]
        assert find_plugin_root(paths) == "repo-main"

    def test_no_skills_directory_returns_empty_without_raising(self):
        assert find_plugin_root(["agents/foo.md", "README.md"]) == ""
        assert find_plugin_root([]) == ""

    def test_multiple_top_level_segments_without_common_wrapper_returns_empty(self):
        # No single common top-level dir wraps everything, so nothing can be safely stripped.
        assert find_plugin_root(["a/skills/x/SKILL.md", "b/other/y"]) == ""
