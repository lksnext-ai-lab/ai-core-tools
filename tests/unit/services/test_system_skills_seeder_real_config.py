"""M5: unit tests exercising the REAL (non-monkeypatched) config-loading path of
backend/services/system_skills_seeder.py — ``backend/system_defaults.yaml`` and the real
``_load_skill_entries`` YAML loader — rather than the monkeypatched ``_load_skill_entries`` lambda
used by ``tests/integration/test_system_skills_seeder.py``.

Since step_034, the real ``skills:`` block is populated with the five curated packages
(word/pdf/pptx/data-analysis/charts), so these tests assert against that real, non-empty list
instead of the earlier ``skills: []`` placeholder. No DB needed: these tests only exercise
``_load_skill_entries`` (pure YAML parsing) and the malformed-entries path of ``_seed_locked``
against a ``MagicMock`` session (those synthetic entries fail validation before any real DB call).
"""
import logging
from unittest.mock import MagicMock

import services.system_skills_seeder as seeder_module
from services.system_skills_seeder import _load_skill_entries, seed_system_skills

_EXPECTED_SYSTEM_SKILL_NAMES = {"word", "pdf", "pptx", "data-analysis", "charts"}


def test_real_defaults_yaml_skills_key_parses_to_the_curated_packages():
    """The real, shipped `backend/system_defaults.yaml` has a `skills:` entry for each of the five
    step_034 curated packages and must parse to that list (not None -- that would incorrectly
    signal a load failure) via the real loader."""
    entries = _load_skill_entries()
    assert entries is not None
    names = {entry["name"] for entry in entries}
    assert names == _EXPECTED_SYSTEM_SKILL_NAMES
    for entry in entries:
        assert entry["path"] == entry["name"], entry


def test_malformed_skills_entries_via_real_loader_are_failed_not_raised(monkeypatch, tmp_path, caplog):
    """A malformed `skills:` entry (non-mapping, missing name, missing path) must be counted as
    failed without raising -- exercised through the REAL YAML loader (`_load_skill_entries` itself
    is not monkeypatched here, only the file path it reads and the packages root, exactly like the
    existing integration tests already do for `_PACKAGES_ROOT`)."""
    bad_yaml = tmp_path / "system_defaults.yaml"
    bad_yaml.write_text(
        "skills:\n"
        "  - not-a-mapping\n"
        "  - {path: only-a-path-no-name}\n"
        "  - {name: only-a-name-no-path}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(seeder_module, "_DEFAULTS_PATH", bad_yaml)
    monkeypatch.setattr(seeder_module, "_PACKAGES_ROOT", tmp_path)

    entries = seeder_module._load_skill_entries()  # real loader, real YAML parsing
    assert entries is not None
    assert len(entries) == 3

    caplog.set_level(logging.DEBUG)
    seeder_module.logger.addHandler(caplog.handler)
    db = MagicMock()
    try:
        seeder_module._seed_locked(db, entries)  # must not raise
    finally:
        seeder_module.logger.removeHandler(caplog.handler)

    messages = [r.getMessage() for r in caplog.records if r.name == seeder_module.logger.name]
    assert any("failed=3" in msg for msg in messages), messages


def test_missing_defaults_yaml_is_distinguished_from_empty_run(monkeypatch, tmp_path, caplog):
    """M4/production-readiness: a config-load failure (missing file) must produce a distinctly
    worded log from a genuine zero-entry run, not the same "clean run" summary line."""
    monkeypatch.setattr(seeder_module, "_DEFAULTS_PATH", tmp_path / "does-not-exist.yaml")

    caplog.set_level(logging.DEBUG)
    seeder_module.logger.addHandler(caplog.handler)
    db = MagicMock()
    try:
        seed_system_skills(db)
    finally:
        seeder_module.logger.removeHandler(caplog.handler)

    assert db.method_calls == []
    messages = [r.getMessage() for r in caplog.records if r.name == seeder_module.logger.name]
    assert any("could not be loaded" in msg for msg in messages), messages
    assert not any("nothing to do" in msg for msg in messages), messages
