"""Real-DB integration tests for backend/services/system_skills_seeder.py (step_033, AC-29..32).

Uses real, independently-connected `SessionLocal()` sessions (never the savepoint-wrapped `db`
fixture) because the seeder relies on genuine Postgres transaction-scoped advisory locks and real
commit/rollback semantics, exactly like `tests/integration/test_advisory_lock_concurrency.py`.
"""
import threading
import uuid

import pytest
from sqlalchemy import text

from db.advisory_lock import try_advisory_lock
from db.database import SessionLocal
from models.skill import Skill, SkillFile
import services.system_skills_seeder as seeder_module
from services.system_skills_seeder import seed_system_skills


def _write_package(tmp_path, name, *, with_skill_md=True, extra_files=None, bad_path=None):
    """Create a package directory ``tmp_path/<name>/`` with a SKILL.md and optional resource files."""
    pkg_dir = tmp_path / name
    pkg_dir.mkdir()
    if with_skill_md:
        (pkg_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Test skill {name}\n---\n# {name}\n\nBody text.\n",
            encoding="utf-8",
        )
    for rel, content in (extra_files or {}).items():
        file_path = pkg_dir / rel
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
    if bad_path:
        # Simulate a corrupted/malicious entry that isn't reachable through a normal relative walk
        # by writing a file whose *content* claims a traversal path is fine (the walker only ever
        # trusts what it discovers on disk, but this documents the attempted-escape scenario is
        # covered by normalize_path on every discovered file, not just top-level packages).
        (pkg_dir / "resources").mkdir(exist_ok=True)
        (pkg_dir / "resources" / "note.txt").write_text(bad_path, encoding="utf-8")
    return pkg_dir


def _delete_system_skill(name: str) -> None:
    db = SessionLocal()
    try:
        skill = (
            db.query(Skill)
            .filter(Skill.app_id.is_(None), Skill.name == name)
            .first()
        )
        if skill is not None:
            db.query(SkillFile).filter(SkillFile.skill_id == skill.skill_id).delete()
            db.delete(skill)
            db.commit()
    finally:
        db.close()


@pytest.fixture()
def unique_name():
    return f"seedtest-{uuid.uuid4().hex[:10]}"


@pytest.fixture(autouse=True)
def _cleanup(unique_name):
    yield
    _delete_system_skill(unique_name)


def test_creates_skill_with_expected_fields(tmp_path, unique_name, monkeypatch, test_engine):
    pkg_dir = _write_package(tmp_path, unique_name)
    monkeypatch.setattr(seeder_module, "_PACKAGES_ROOT", tmp_path)
    monkeypatch.setattr(
        seeder_module, "_load_skill_entries", lambda: [{"name": unique_name, "path": unique_name}]
    )

    db = SessionLocal()
    try:
        seed_system_skills(db)
    finally:
        db.close()

    check = SessionLocal()
    try:
        skill = (
            check.query(Skill)
            .filter(Skill.app_id.is_(None), Skill.name == unique_name)
            .first()
        )
        assert skill is not None
        assert skill.app_id is None
        assert skill.source == "yaml"
        assert skill.is_enabled is True
        assert skill.content.strip() == "# " + unique_name + "\n\nBody text."
    finally:
        check.close()


def test_second_run_is_idempotent_creates_nothing(tmp_path, unique_name, monkeypatch, test_engine):
    pkg_dir = _write_package(tmp_path, unique_name)
    monkeypatch.setattr(seeder_module, "_PACKAGES_ROOT", tmp_path)
    monkeypatch.setattr(
        seeder_module, "_load_skill_entries", lambda: [{"name": unique_name, "path": unique_name}]
    )

    db1 = SessionLocal()
    try:
        seed_system_skills(db1)
    finally:
        db1.close()

    check = SessionLocal()
    try:
        count_after_first = (
            check.query(Skill).filter(Skill.app_id.is_(None), Skill.name == unique_name).count()
        )
    finally:
        check.close()
    assert count_after_first == 1

    db2 = SessionLocal()
    try:
        seed_system_skills(db2)
    finally:
        db2.close()

    check2 = SessionLocal()
    try:
        count_after_second = (
            check2.query(Skill).filter(Skill.app_id.is_(None), Skill.name == unique_name).count()
        )
    finally:
        check2.close()
    assert count_after_second == 1, "second run must not create a duplicate row"


def test_manual_disable_survives_reseed_ac30(tmp_path, unique_name, monkeypatch, test_engine):
    """AC-30's core guarantee: an admin edit to a seeded skill is never overwritten/restored."""
    pkg_dir = _write_package(tmp_path, unique_name)
    monkeypatch.setattr(seeder_module, "_PACKAGES_ROOT", tmp_path)
    monkeypatch.setattr(
        seeder_module, "_load_skill_entries", lambda: [{"name": unique_name, "path": unique_name}]
    )

    db1 = SessionLocal()
    try:
        seed_system_skills(db1)
    finally:
        db1.close()

    # Admin disables it and edits the description directly in the DB.
    db2 = SessionLocal()
    try:
        skill = (
            db2.query(Skill)
            .filter(Skill.app_id.is_(None), Skill.name == unique_name)
            .first()
        )
        assert skill is not None
        skill.is_enabled = False
        skill.description = "manually edited by an admin"
        db2.add(skill)
        db2.commit()
    finally:
        db2.close()

    # Re-run the seeder: create-if-missing must skip this already-existing skill untouched.
    db3 = SessionLocal()
    try:
        seed_system_skills(db3)
    finally:
        db3.close()

    check = SessionLocal()
    try:
        skill = (
            check.query(Skill)
            .filter(Skill.app_id.is_(None), Skill.name == unique_name)
            .first()
        )
        assert skill is not None
        assert skill.is_enabled is False, "seeder must never re-enable a disabled seeded skill"
        assert skill.description == "manually edited by an admin", "seeder must never overwrite an edit"
    finally:
        check.close()


def test_corrupted_package_is_isolated_and_lock_stays_held_for_rest_of_run(
    tmp_path, unique_name, monkeypatch, caplog, test_engine
):
    """A missing-SKILL.md package fails, is logged with only its path (not content), does not crash
    the run, the next package in the same run still seeds successfully, and — critically — the
    advisory lock is still genuinely held by the seeder's own (uncommitted) transaction while
    the good package is being processed, proving the per-package db.begin_nested() recovery did
    not release the lock the way a bare db.rollback() would have (see step_032's footgun).
    """
    bad_name = f"{unique_name}-bad"
    good_name = f"{unique_name}-good"
    _write_package(tmp_path, bad_name, with_skill_md=False)
    _write_package(tmp_path, good_name)

    monkeypatch.setattr(seeder_module, "_PACKAGES_ROOT", tmp_path)
    monkeypatch.setattr(
        seeder_module,
        "_load_skill_entries",
        lambda: [
            {"name": bad_name, "path": bad_name},
            {"name": good_name, "path": good_name},
        ],
    )

    probe_results = {}
    original_create = seeder_module._create_skill_from_package

    def _instrumented_create(db, name, pkg_dir):
        if name == good_name:
            # Probe with a genuinely independent session while the seeder's own transaction
            # (and its advisory lock) is still open, mid-run, right after the bad package failed.
            probe_db = SessionLocal()
            try:
                with try_advisory_lock(probe_db, seeder_module._LOCK_KEY) as probe_acquired:
                    probe_results["still_locked_out"] = not probe_acquired
            finally:
                probe_db.close()
        return original_create(db, name, pkg_dir)

    monkeypatch.setattr(seeder_module, "_create_skill_from_package", _instrumented_create)

    import logging

    # seeder_module.logger has propagate=False (see utils/logger.py), so plain caplog.at_level
    # (which relies on propagation to the root logger's captured handler) would see nothing;
    # attach caplog's own handler directly to it instead.
    caplog.set_level(logging.DEBUG)
    seeder_module.logger.addHandler(caplog.handler)
    db = SessionLocal()
    try:
        seed_system_skills(db)
    finally:
        db.close()
        seeder_module.logger.removeHandler(caplog.handler)

    # The bad package's failure was logged, naming its path, without ever including file contents.
    error_records = [r for r in caplog.records if r.name == seeder_module.logger.name]
    bad_logs = [r for r in error_records if bad_name in r.getMessage()]
    assert bad_logs, "expected an error log naming the failed package's path"
    for record in bad_logs:
        assert "SKILL.md" not in record.getMessage() or "missing" in record.getMessage()

    # The lock was still genuinely held for the rest of the run (proves begin_nested(), not a bare
    # rollback, was used for the bad package's recovery).
    assert probe_results.get("still_locked_out") is True

    # The good package still seeded successfully despite the earlier failure in the same run.
    _delete_system_skill(bad_name)  # no-op (never created), kept for symmetry/clarity
    check = SessionLocal()
    try:
        good_skill = (
            check.query(Skill).filter(Skill.app_id.is_(None), Skill.name == good_name).first()
        )
        bad_skill = (
            check.query(Skill).filter(Skill.app_id.is_(None), Skill.name == bad_name).first()
        )
        assert good_skill is not None
        assert bad_skill is None
    finally:
        check.close()
        _delete_system_skill(good_name)


def test_manual_delete_of_skill_file_row_survives_reseed_ac30(tmp_path, unique_name, monkeypatch, test_engine):
    """AC-30's second leg (per step_038's task note): the operator deletes one of the seeded
    skill's ``SkillFile`` rows directly (e.g. cleaning up a resource they don't want) -- a re-run
    of the seeder must never restore it, since create-if-missing only checks the skill NAME, not
    its file set."""
    pkg_dir = _write_package(
        tmp_path, unique_name, extra_files={"resources/note.txt": "keep me or not"}
    )
    monkeypatch.setattr(seeder_module, "_PACKAGES_ROOT", tmp_path)
    monkeypatch.setattr(
        seeder_module, "_load_skill_entries", lambda: [{"name": unique_name, "path": unique_name}]
    )

    db1 = SessionLocal()
    try:
        seed_system_skills(db1)
    finally:
        db1.close()

    db2 = SessionLocal()
    try:
        skill = (
            db2.query(Skill).filter(Skill.app_id.is_(None), Skill.name == unique_name).first()
        )
        assert skill is not None
        file_row = (
            db2.query(SkillFile)
            .filter(SkillFile.skill_id == skill.skill_id, SkillFile.path == "resources/note.txt")
            .first()
        )
        assert file_row is not None, "seeder must have created the resource file row"
        db2.delete(file_row)
        db2.commit()
    finally:
        db2.close()

    # Re-run the seeder: the skill name already exists, so it must be skipped entirely --
    # the deleted SkillFile row must NOT be restored.
    db3 = SessionLocal()
    try:
        seed_system_skills(db3)
    finally:
        db3.close()

    check = SessionLocal()
    try:
        skill = (
            check.query(Skill).filter(Skill.app_id.is_(None), Skill.name == unique_name).first()
        )
        assert skill is not None
        remaining = (
            check.query(SkillFile)
            .filter(SkillFile.skill_id == skill.skill_id, SkillFile.path == "resources/note.txt")
            .first()
        )
        assert remaining is None, "seeder must never restore a manually deleted SkillFile row"
    finally:
        check.close()


def test_two_genuinely_concurrent_sessions_create_exactly_one_row_per_skill_ac32(
    tmp_path, unique_name, monkeypatch, test_engine
):
    """AC-32: two real threads, each with its own independently-connected ``SessionLocal()``,
    call ``seed_system_skills`` for the SAME package at (as close to) the same time as a barrier
    can arrange. The transaction-scoped advisory lock (step_032) must serialise them so exactly
    one Skill row (and one SkillFile row) exists afterward -- a shared session/transaction would
    not exercise the lock at all, which is why this uses two threads with two real connections,
    not two sequential calls on one session."""
    _write_package(tmp_path, unique_name, extra_files={"scripts/run.py": "print('hi')\n"})
    monkeypatch.setattr(seeder_module, "_PACKAGES_ROOT", tmp_path)
    monkeypatch.setattr(
        seeder_module, "_load_skill_entries", lambda: [{"name": unique_name, "path": unique_name}]
    )

    barrier = threading.Barrier(2)
    errors = []

    def _run():
        try:
            barrier.wait(timeout=5)
            db = SessionLocal()
            try:
                seed_system_skills(db)
            finally:
                db.close()
        except Exception as exc:  # pragma: no cover - surfaced via `errors` below
            errors.append(exc)

    t1 = threading.Thread(target=_run)
    t2 = threading.Thread(target=_run)
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)

    assert not errors, f"seed_system_skills raised in a worker thread: {errors}"
    assert not t1.is_alive() and not t2.is_alive(), "a worker thread did not finish in time"

    check = SessionLocal()
    try:
        skill_count = (
            check.query(Skill).filter(Skill.app_id.is_(None), Skill.name == unique_name).count()
        )
        assert skill_count == 1, "concurrent seeding must create exactly one Skill row"
        skill = (
            check.query(Skill).filter(Skill.app_id.is_(None), Skill.name == unique_name).first()
        )
        file_count = (
            check.query(SkillFile)
            .filter(SkillFile.skill_id == skill.skill_id, SkillFile.path == "scripts/run.py")
            .count()
        )
        assert file_count == 1, "concurrent seeding must create exactly one SkillFile row per file"
    finally:
        check.close()


def test_lock_not_acquired_skips_entire_run(tmp_path, unique_name, monkeypatch, test_engine):
    pkg_dir = _write_package(tmp_path, unique_name)
    monkeypatch.setattr(seeder_module, "_PACKAGES_ROOT", tmp_path)
    monkeypatch.setattr(
        seeder_module, "_load_skill_entries", lambda: [{"name": unique_name, "path": unique_name}]
    )

    holder = SessionLocal()
    try:
        with try_advisory_lock(holder, seeder_module._LOCK_KEY) as acquired:
            assert acquired is True
            # A losing seeder run concurrent with the lock holder must skip entirely.
            loser_db = SessionLocal()
            try:
                seed_system_skills(loser_db)
            finally:
                loser_db.close()
        holder.commit()
    finally:
        holder.close()

    check = SessionLocal()
    try:
        count = check.query(Skill).filter(Skill.app_id.is_(None), Skill.name == unique_name).count()
    finally:
        check.close()
    assert count == 0, "a run that lost the advisory lock race must not have created anything"
