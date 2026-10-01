"""Real concurrency tests: per-app advisory lock closes the quota and duplicate-name races (separate sessions)."""
import io
import threading
import zipfile

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

import services.skill_package_service as pkg_module
from models.app import App
from models.skill import Skill
from models.user import User
from services.skill_errors import SkillConflictError
from services.skill_package_service import SkillPackageService

pytestmark = pytest.mark.integration


def make_zip(name: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('SKILL.md', f'---\nname: {name}\n---\nbody\n')
        zf.writestr('a.txt', 'x')
    return buf.getvalue()


@pytest.fixture
def committed_app(test_engine, monkeypatch):
    """A committed App (visible to other connections); cleaned up afterwards."""
    monkeypatch.setattr(pkg_module, '_IMPORT_SEMAPHORE', threading.BoundedSemaphore(16))
    with Session(test_engine) as s:
        user = User(email='race@mattin-test.com', name='Race', is_active=True)
        s.add(user)
        s.flush()
        app = App(name='Race App', slug='race-app-skill-imports', owner_id=user.user_id,
                  agent_rate_limit=0, max_file_size_mb=10)
        s.add(app)
        s.commit()
        app_id, user_id = app.app_id, user.user_id
    yield app_id
    with Session(test_engine) as s:
        s.query(Skill).filter(Skill.app_id == app_id).delete()  # SkillFile rows cascade in the DB
        s.query(App).filter(App.app_id == app_id).delete()
        s.query(User).filter(User.user_id == user_id).delete()
        s.commit()


def run_concurrently(test_engine, app_id, names):
    barrier = threading.Barrier(len(names))
    results = [None] * len(names)

    def worker(i, name):
        with Session(test_engine) as s:
            barrier.wait()
            try:
                results[i] = SkillPackageService.import_package(s, app_id=app_id, data=make_zip(name)).skill_id
            except Exception as exc:  # noqa: BLE001 - outcomes are asserted by type below
                results[i] = exc

    threads = [threading.Thread(target=worker, args=(i, n)) for i, n in enumerate(names)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not any(t.is_alive() for t in threads)
    return results


def test_quota_not_bypassed_by_concurrent_imports(test_engine, committed_app, monkeypatch):
    def limited(db, app_id, resource_type):
        if db.query(Skill).filter(Skill.app_id == app_id).count() >= 2:
            raise HTTPException(status_code=403, detail='limit reached')

    import services.tier_enforcement_service as tier
    monkeypatch.setattr(tier.TierEnforcementService, 'check_resource_limit', staticmethod(limited))

    results = run_concurrently(test_engine, committed_app, [f'quota-{i}' for i in range(4)])
    ok = [r for r in results if isinstance(r, int)]
    denied = [r for r in results if isinstance(r, HTTPException)]
    assert len(ok) == 2 and len(denied) == 2, results
    with Session(test_engine) as s:
        assert s.query(Skill).filter(Skill.app_id == committed_app).count() == 2


def test_same_name_concurrent_imports_yield_one_winner(test_engine, committed_app):
    results = run_concurrently(test_engine, committed_app, ['same-name'] * 3)
    ok = [r for r in results if isinstance(r, int)]
    conflicts = [r for r in results if isinstance(r, SkillConflictError)]
    assert len(ok) == 1 and len(conflicts) == 2, results
    with Session(test_engine) as s:
        assert s.query(Skill).filter(Skill.app_id == committed_app, Skill.name == 'same-name').count() == 1
