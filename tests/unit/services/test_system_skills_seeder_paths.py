"""Unit tests for the pure path-safety helpers of backend/services/system_skills_seeder.py.

No DB needed: these exercise `_resolve_package_dir` / `_walk_package_files` directly against a
real temp filesystem.
"""
import os

import pytest

from services.system_skills_seeder import _PackageError, _resolve_package_dir, _walk_package_files


def test_resolve_package_dir_rejects_traversal(tmp_path, monkeypatch):
    import services.system_skills_seeder as m
    monkeypatch.setattr(m, "_PACKAGES_ROOT", tmp_path)
    with pytest.raises(_PackageError):
        m._resolve_package_dir("../escape")


def test_resolve_package_dir_rejects_missing(tmp_path, monkeypatch):
    import services.system_skills_seeder as m
    monkeypatch.setattr(m, "_PACKAGES_ROOT", tmp_path)
    with pytest.raises(_PackageError):
        m._resolve_package_dir("does-not-exist")


def test_resolve_package_dir_rejects_symlink(tmp_path, monkeypatch):
    import services.system_skills_seeder as m
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    outside = tmp_path.parent / "outside_pkg"
    outside.mkdir(exist_ok=True)
    link = tmp_path / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported in this environment")
    monkeypatch.setattr(m, "_PACKAGES_ROOT", tmp_path)
    with pytest.raises(_PackageError):
        m._resolve_package_dir("link")


def test_resolve_package_dir_accepts_valid_subdir(tmp_path, monkeypatch):
    import services.system_skills_seeder as m
    pkg = tmp_path / "good"
    pkg.mkdir()
    monkeypatch.setattr(m, "_PACKAGES_ROOT", tmp_path)
    resolved = m._resolve_package_dir("good")
    assert resolved == pkg.resolve()


def test_walk_package_files_rejects_missing_skill_md(tmp_path):
    from services.system_skills_seeder import _walk_package_files, _PackageError as PE
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    with pytest.raises(PE):
        _walk_package_files(pkg)


def test_walk_package_files_rejects_symlinked_file(tmp_path):
    from services.system_skills_seeder import _walk_package_files, _PackageError as PE
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "SKILL.md").write_text("---\nname: pkg\n---\nBody\n", encoding="utf-8")
    outside_file = tmp_path / "secret.txt"
    outside_file.write_text("outside content", encoding="utf-8")
    link = pkg / "linked.txt"
    try:
        link.symlink_to(outside_file)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported in this environment")
    with pytest.raises(PE):
        _walk_package_files(pkg)


def test_walk_package_files_enforces_max_file_bytes(tmp_path, monkeypatch):
    import services.system_skills_seeder as m
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "SKILL.md").write_text("---\nname: pkg\n---\nBody\n", encoding="utf-8")
    (pkg / "big.txt").write_text("x" * 100, encoding="utf-8")
    monkeypatch.setattr(m.settings, "SKILL_IMPORT_MAX_FILE_BYTES", 10)
    with pytest.raises(m._PackageError):
        m._walk_package_files(pkg)


def test_walk_package_files_reads_valid_package(tmp_path):
    from services.system_skills_seeder import _walk_package_files
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "SKILL.md").write_text("---\nname: pkg\n---\nBody\n", encoding="utf-8")
    (pkg / "scripts").mkdir()
    (pkg / "scripts" / "run.py").write_text("print('hi')\n", encoding="utf-8")
    skill_md_text, files = _walk_package_files(pkg)
    assert "Body" in skill_md_text
    assert files == {"scripts/run.py": b"print('hi')\n"}


def test_walk_package_files_rejects_homoglyph_collision(tmp_path):
    """H1: two DISTINCT on-disk files that NFKC-fold onto the same normalised path must raise loudly,
    never silently let the later one (e.g. a homoglyph malicious file) overwrite the earlier one."""
    from services.system_skills_seeder import _PackageError as PE, _walk_package_files
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "SKILL.md").write_text("---\nname: pkg\n---\nBody\n", encoding="utf-8")
    # 's' (U+FF53, FULLWIDTH LATIN SMALL LETTER S) NFKC-folds to ASCII 's'.
    (pkg / "setup.sh").write_text("echo benign\n", encoding="utf-8")
    (pkg / "ｓetup.sh").write_text("echo malicious\n", encoding="utf-8")
    with pytest.raises(PE) as exc_info:
        _walk_package_files(pkg)
    # The reviewed on-disk name (setup.sh) is either the one that trips the "not already normalised"
    # rejection (for the homoglyph filename) or -- crucially -- content is never silently swapped:
    # no successful return is possible for this package at all.
    assert "normalised" in str(exc_info.value) or "duplicate" in str(exc_info.value).lower()


def test_walk_package_files_rejects_case_insensitive_duplicate(tmp_path):
    """H1 (case leg): 'A.txt' and 'a.txt' are distinct on-disk paths but must collide, matching
    SkillPackageRepository.replace_files's own case-insensitive duplicate rule."""
    from services.system_skills_seeder import _PackageError as PE, _walk_package_files
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "SKILL.md").write_text("---\nname: pkg\n---\nBody\n", encoding="utf-8")
    (pkg / "A.txt").write_text("upper\n", encoding="utf-8")
    (pkg / "a.txt").write_text("lower\n", encoding="utf-8")
    with pytest.raises(PE):
        _walk_package_files(pkg)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFOs not supported on this platform")
def test_walk_package_files_rejects_fifo_without_hanging(tmp_path):
    """M1: a FIFO under a package directory must raise quickly (never Path.read_bytes()-hang forever,
    which would freeze the whole FastAPI lifespan while holding the advisory lock)."""
    import signal

    from services.system_skills_seeder import _PackageError as PE, _walk_package_files
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "SKILL.md").write_text("---\nname: pkg\n---\nBody\n", encoding="utf-8")
    os.mkfifo(pkg / "evil.fifo")

    def _on_alarm(signum, frame):
        raise TimeoutError("_walk_package_files hung on a FIFO with no writer")

    old_handler = signal.signal(signal.SIGALRM, _on_alarm)
    signal.alarm(5)
    try:
        with pytest.raises(PE, match="not a regular file"):
            _walk_package_files(pkg)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def test_walk_package_files_checks_size_before_reading_bytes(tmp_path, monkeypatch):
    """M2: the size cap must be enforced from ``fstat`` BEFORE the file's bytes are read into memory.
    Verified by making ``os.read`` fail the test if it is ever called for the oversized file — proving
    rejection happens at the fstat/size-check stage, not after a full buffered read."""
    import services.system_skills_seeder as m

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "SKILL.md").write_text("---\nname: pkg\n---\nBody\n", encoding="utf-8")
    (pkg / "big.bin").write_bytes(b"x" * 1000)
    monkeypatch.setattr(m.settings, "SKILL_IMPORT_MAX_FILE_BYTES", 10)

    real_read = os.read
    calls = []

    def _tracking_read(fd, n):
        calls.append(n)
        return real_read(fd, n)

    monkeypatch.setattr(m.os, "read", _tracking_read)
    with pytest.raises(m._PackageError, match="exceeds max size"):
        m._walk_package_files(pkg)
    # os.read was never invoked for big.bin: the fstat-based size check rejected it first.
    assert calls == []


def test_walk_package_files_counts_skill_md_toward_total_and_caps_it(tmp_path, monkeypatch):
    """M2: SKILL.md itself must be size-capped and counted toward SKILL_IMPORT_MAX_TOTAL_BYTES,
    not exempted from accounting."""
    import services.system_skills_seeder as m

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "SKILL.md").write_text("---\nname: pkg\n---\n" + ("x" * 100) + "\n", encoding="utf-8")
    monkeypatch.setattr(m.settings, "SKILL_IMPORT_MAX_FILE_BYTES", 10)
    with pytest.raises(m._PackageError):
        m._walk_package_files(pkg)


def test_walk_package_files_rejects_symlinked_subdirectory_loudly(tmp_path):
    """A symlinked subdirectory must raise, not be silently pruned from the walk (would otherwise
    seed a truncated package that's never repaired since seeding is create-if-missing only)."""
    from services.system_skills_seeder import _PackageError as PE, _walk_package_files
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "SKILL.md").write_text("---\nname: pkg\n---\nBody\n", encoding="utf-8")
    real_subdir = tmp_path / "outside_subdir"
    real_subdir.mkdir()
    (real_subdir / "note.txt").write_text("hello\n", encoding="utf-8")
    link = pkg / "resources"
    try:
        link.symlink_to(real_subdir, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported in this environment")
    with pytest.raises(PE, match="symlinked directory"):
        _walk_package_files(pkg)
