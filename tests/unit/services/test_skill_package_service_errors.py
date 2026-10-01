"""Typed error mapping and bulkhead of SkillPackageService.import_package (no database)."""
import io
import threading
import zipfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

import services.skill_package_service as mod
from services.skill_errors import (
    SkillBusyError, SkillConflictError, SkillImportError, SkillPersistenceError, SkillServiceError,
)
from services.skill_package_service import SkillPackageService


def zip_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('SKILL.md', '---\nname: x\n---\nbody')
    return buf.getvalue()


def integrity_error(constraint):
    orig = SimpleNamespace(diag=SimpleNamespace(constraint_name=constraint))
    return IntegrityError("INSERT ... secret params", {}, orig)


@pytest.fixture
def repo():
    with patch.object(mod, 'SkillRepository') as r:
        r.get_system_skill_by_name.return_value = None
        yield r


def test_error_classes_are_not_value_errors_and_have_class_status():
    for cls, code in ((SkillImportError, 400), (SkillConflictError, 409), (SkillBusyError, 429),
                      (SkillPersistenceError, 500)):
        assert issubclass(cls, SkillServiceError) and not issubclass(cls, ValueError)
        assert cls.status_code == code


def test_system_name_constraint_maps_to_conflict(repo):
    repo.persist.side_effect = integrity_error('uq_skill_system_name')
    db = MagicMock()
    with pytest.raises(SkillConflictError) as ei:
        SkillPackageService.import_package(db, app_id=None, data=zip_bytes())
    db.rollback.assert_called()
    assert 'secret' not in ei.value.detail


def test_other_constraint_maps_to_persistence_error_500(repo):
    repo.persist.side_effect = integrity_error('some_other_fk')
    db = MagicMock()
    with pytest.raises(SkillPersistenceError) as ei:
        SkillPackageService.import_package(db, app_id=None, data=zip_bytes())
    db.rollback.assert_called()
    assert ei.value.status_code == 500 and 'secret' not in ei.value.detail


def test_duplicate_precheck_is_conflict_not_import_error(repo):
    repo.get_system_skill_by_name.return_value = SimpleNamespace(skill_id=1)
    with pytest.raises(SkillConflictError):
        SkillPackageService.import_package(MagicMock(), app_id=None, data=zip_bytes())


def test_bulkhead_rejects_when_exhausted_and_releases(monkeypatch, repo):
    sem = threading.BoundedSemaphore(1)
    monkeypatch.setattr(mod, '_IMPORT_SEMAPHORE', sem)
    assert sem.acquire(blocking=False)
    with pytest.raises(SkillBusyError):
        SkillPackageService.import_package(MagicMock(), app_id=None, data=zip_bytes())
    sem.release()
    with pytest.raises(SkillImportError):  # invalid zip, but the slot is released afterwards
        SkillPackageService.import_package(MagicMock(), app_id=None, data=b'not a zip')
    assert sem.acquire(blocking=False)


def test_app_scope_takes_advisory_lock_before_checks(repo):
    order = []
    repo.lock_app_skills.side_effect = lambda *a: order.append('lock')
    repo.get_by_name_and_app_id.side_effect = lambda *a: order.append('dup') or SimpleNamespace(skill_id=1)
    with pytest.raises(SkillConflictError):
        SkillPackageService.import_package(MagicMock(), app_id=3, data=zip_bytes())
    assert order == ['lock', 'dup']
