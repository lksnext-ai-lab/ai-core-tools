"""Smoke tests for SkillPackageService / SkillService semantics against the real test DB (step_010)."""
import io
import zipfile

import pytest

from models.agent import AgentSkill
from models.skill import Skill, SkillFile
from repositories.agent_repository import AgentRepository
from repositories.skill_repository import SkillRepository
from repositories.skill_package_repository import SkillPackageRepository
from services.agent_service import AgentService
from services.skill_errors import (
    SkillConflictError, SkillForbiddenError, SkillImportError,
)
from services.skill_package_service import SkillPackageService
from services.skill_service import SkillService
from tests.factories import (
    AgentFactory, AppFactory, SkillFactory, SystemSkillFactory, configure_factories,
)

pytestmark = pytest.mark.integration

SKILL_MD = (
    "---\nname: My Skill\ndisplay_name: My Skill Label\ndescription: does things\n"
    "when_to_use: when asked\ndisable-model-invocation: true\nallowed-tools: [a, b]\n"
    "runtime: python3.11\nbootstrap_script_path: scripts/setup.py\nruntime_options:\n  k: 1\n"
    "custom_key: 5\n---\n# Body\nhello\n"
)


def make_zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


def good_zip():
    return make_zip({
        'SKILL.md': SKILL_MD,
        'scripts/setup.py': 'print(1)\n',
        'references/SKILL.md': 'nested',
        'assets/blob.bin': b'\x00\x01\xff',
        'empty.txt': '',
    })


@pytest.fixture
def two_apps(db):
    configure_factories(db)
    return AppFactory(), AppFactory()


def counts(db):
    return db.query(Skill).count(), db.query(SkillFile).count()


class TestImportExport:
    @staticmethod
    def _orm(db, app_id, skill_id):
        """import_package returns a detached SkillDetailSchema; fetch the ORM row for export/payload calls,
        which (per skill_package_service.py's docstrings) take an already-resolved-and-authorised Skill."""
        if app_id is None:
            return SkillRepository.get_system_skill_by_id(db, skill_id)
        return SkillRepository.get_by_id_and_app_id(db, skill_id, app_id)

    def test_import_and_round_trip(self, db, two_apps):
        a1, a2 = two_apps
        d1 = SkillPackageService.import_package(db, app_id=a1.app_id, data=good_zip())
        assert d1.name == 'my-skill' and d1.content == '# Body\nhello\n'
        assert d1.bootstrap_script_path == 'scripts/setup.py'
        assert d1.frontmatter == {'custom_key': 5, 'when_to_use': 'when asked', 'disable_model_invocation': True}
        s1 = self._orm(db, a1.app_id, d1.skill_id)
        files = {f.path: f for f in SkillPackageRepository.list_files(db, s1.skill_id)}
        assert set(files) == {'scripts/setup.py', 'references/SKILL.md', 'assets/blob.bin', 'empty.txt'}
        assert files['empty.txt'].content_text == '' and files['empty.txt'].content_bytes is None
        assert files['assets/blob.bin'].content_bytes == b'\x00\x01\xff'
        name, blob = SkillPackageService.export_package(db, s1)
        assert name == 'my-skill.zip'
        d2 = SkillPackageService.import_package(db, app_id=a2.app_id, data=blob)
        for attr in ('name', 'display_name', 'description', 'content', 'frontmatter', 'allowed_tools',
                     'runtime', 'bootstrap_script_path', 'runtime_options'):
            assert getattr(d1, attr) == getattr(d2, attr), attr
        s2 = self._orm(db, a2.app_id, d2.skill_id)
        n2, b2 = SkillPackageService.export_package(db, s2)
        assert (n2, b2) == (name, blob)
        payload = SkillPackageService.build_payload(db, s2)
        assert payload.name == 'my-skill' and dict(payload.files)['scripts/setup.py'] == b'print(1)\n'

    def test_export_without_files(self, db, two_apps):
        s = SkillFactory(app=two_apps[0])
        name, blob = SkillPackageService.export_package(db, s)
        assert zipfile.ZipFile(io.BytesIO(blob)).namelist() == ['SKILL.md']

    @pytest.mark.parametrize("data", [
        b'not a zip',
        make_zip({'other.md': 'x'}),
        make_zip({'SKILL.md': '---\nname: [\n---\nb'}),
        make_zip({'SKILL.md': '---\nname: x\nbootstrap_script_path: nope.py\n---\nb'}),
        make_zip({'SKILL.md': '---\nname: x\ndescription: ' + 'd' * 2000 + '\n---\nb'}),
        make_zip({'SKILL.md': b'---\nname: x\n---\n\xff\xfe'}),
    ])
    def test_rejections_leave_nothing(self, db, two_apps, data):
        before = counts(db)
        with pytest.raises(SkillImportError) as ei:
            SkillPackageService.import_package(db, app_id=two_apps[0].app_id, data=data)
        assert ei.value.status_code == 400
        assert counts(db) == before

    def test_duplicate_name_409(self, db, two_apps):
        a1 = two_apps[0]
        SkillPackageService.import_package(db, app_id=a1.app_id, data=good_zip())
        before = counts(db)
        with pytest.raises(SkillConflictError) as ei:
            SkillPackageService.import_package(
                db, app_id=a1.app_id, data=make_zip({'SKILL.md': '---\nname: MY-skill\n---\nb'}))
        assert ei.value.status_code == 409 and counts(db) == before

    def test_structural_validation_precedes_duplicate_name_check(self, db, two_apps):
        """A structurally invalid package (over-length field / unresolvable bootstrap path) must
        fail with SkillImportError/400 even when it ALSO collides with an existing skill name —
        validation runs before the duplicate-name/quota DB checks, not after (regression guard:
        an earlier refactor moved the pure-validation call inside the persistence seam, which
        silently flipped this precedence to 409/403; see step_033's carry-over notes)."""
        a1 = two_apps[0]
        SkillPackageService.import_package(db, app_id=a1.app_id, data=good_zip())
        before = counts(db)
        malformed_same_name = make_zip({
            'SKILL.md': '---\nname: MY-skill\nbootstrap_script_path: does-not-exist.py\n---\nb',
        })
        with pytest.raises(SkillImportError) as ei:
            SkillPackageService.import_package(db, app_id=a1.app_id, data=malformed_same_name)
        assert ei.value.status_code == 400 and counts(db) == before

    def test_files_failure_rolls_back_skill_row(self, db, two_apps, monkeypatch):
        before = counts(db)
        real = SkillPackageRepository.replace_files

        def boom(db_, skill_id, files):
            real(db_, skill_id, [('a.txt', b'x', None), ('A.txt', b'y', None)])  # case-insensitive duplicate

        monkeypatch.setattr(SkillPackageRepository, 'replace_files', staticmethod(boom))
        with pytest.raises(SkillImportError) as ei:
            SkillPackageService.import_package(db, app_id=two_apps[0].app_id, data=good_zip())
        assert ei.value.status_code == 400 and counts(db) == before

    def test_system_import_no_quota(self, db, two_apps, monkeypatch):
        import services.tier_enforcement_service as t
        monkeypatch.setattr(t.TierEnforcementService, 'check_resource_limit',
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError('quota used')))
        d = SkillPackageService.import_package(db, app_id=None, data=good_zip(), source='yaml')
        assert d.is_system is True and d.source == 'yaml'
        with pytest.raises(SkillConflictError) as ei:
            SkillPackageService.import_package(db, app_id=None, data=good_zip())
        assert ei.value.status_code == 409


class TestServiceSemantics:
    def test_merged_listing_collision_and_disabled(self, db, two_apps):
        a1 = two_apps[0]
        SkillFactory(app=a1, name='shared')
        SkillFactory(app=a1, name='off-app', is_enabled=False)
        SystemSkillFactory(name='Shared')
        keep = SystemSkillFactory(name='sys-ok')
        SystemSkillFactory(name='sys-off', is_enabled=False)
        items = {i.name: i for i in SkillService.list_skills(db, a1.app_id)}
        assert set(items) == {'shared', 'off-app', 'sys-ok'}
        assert items['off-app'].is_enabled is False and items['sys-ok'].is_system is True
        assert SkillService.get_skill_detail(db, a1.app_id, keep.skill_id).is_system is True

    def test_forbidden_and_delete_system(self, db, two_apps):
        from schemas.skill_schemas import CreateUpdateSkillSchema
        a1 = two_apps[0]
        sysk = SystemSkillFactory()
        with pytest.raises(SkillForbiddenError):
            SkillService.create_or_update_skill(
                db, a1.app_id, sysk.skill_id, CreateUpdateSkillSchema(name='x', content='y'))
        with pytest.raises(SkillForbiddenError):
            SkillService.delete_skill(db, a1.app_id, sysk.skill_id)
        yaml_skill = SystemSkillFactory(source='yaml')
        with pytest.raises(SkillConflictError):
            SkillService.delete_system_skill(db, yaml_skill.skill_id)
        assert SkillService.delete_system_skill(db, sysk.skill_id) is True
        detail = SkillService.set_system_skill_enabled(db, yaml_skill.skill_id, False)
        assert detail.is_enabled is False and detail.is_system is True
        assert SkillService.set_system_skill_enabled(db, 10**9, False) is None

    def test_delete_system_skill_refused_when_attached(self, db, two_apps):
        agent = AgentFactory(app=two_apps[0])
        sysk = SystemSkillFactory()
        AgentRepository.create_agent_skill_association(db, agent.agent_id, sysk.skill_id)
        db.flush()
        with pytest.raises(SkillConflictError) as ei:
            SkillService.delete_system_skill(db, sysk.skill_id)
        assert 'attached to 1 agents' in ei.value.detail

    def test_set_enabled_for_app(self, db, two_apps):
        a1, a2 = two_apps
        own = SkillFactory(app=a1)
        sysk = SystemSkillFactory()
        assert SkillService.set_enabled_for_app(db, a1.app_id, own.skill_id, False).is_enabled is False
        assert SkillService.set_enabled_for_app(db, a2.app_id, own.skill_id, True) is None  # cross-app
        with pytest.raises(SkillForbiddenError):
            SkillService.set_enabled_for_app(db, a1.app_id, sysk.skill_id, False)

    def test_facade_export_and_detail(self, db, two_apps):
        a1, a2 = two_apps
        own = SkillFactory(app=a1, name='exp-own')
        on = SystemSkillFactory(name='exp-sys')
        off = SystemSkillFactory(name='exp-off', is_enabled=False)
        assert SkillPackageService.export_for_app(db, a1.app_id, own.skill_id)[0] == 'exp-own.zip'
        assert SkillPackageService.export_for_app(db, a2.app_id, own.skill_id) is None
        assert SkillPackageService.export_for_app(db, a2.app_id, on.skill_id)[0] == 'exp-sys.zip'
        assert SkillPackageService.export_for_app(db, a2.app_id, off.skill_id) is None
        assert SkillPackageService.export_system_skill(db, off.skill_id)[0] == 'exp-off.zip'
        assert SkillPackageService.export_system_skill(db, own.skill_id) is None
        assert SkillService.get_system_skill_detail(db, off.skill_id).skill_id == off.skill_id
        assert SkillService.get_system_skill_detail(db, own.skill_id) is None
        assert {i.name for i in SkillService.list_system_skills(db, enabled_only=True)} >= {'exp-sys'}
        assert 'exp-off' not in {i.name for i in SkillService.list_system_skills(db, enabled_only=True)}

    def test_crud_create_rename_duplicate_and_bootstrap(self, db, two_apps):
        from schemas.skill_schemas import CreateUpdateSkillSchema as C
        from services.skill_errors import SkillValidationError
        a1 = two_apps[0]
        SkillService.create_or_update_skill(db, a1.app_id, 0, C(name='Alpha One', content='x'))
        with pytest.raises(SkillConflictError):
            SkillService.create_or_update_skill(db, a1.app_id, 0, C(name='alpha-one', content='x'))
        other = SkillService.create_or_update_skill(db, a1.app_id, 0, C(name='beta', content='x'))
        with pytest.raises(SkillConflictError):
            SkillService.create_or_update_skill(db, a1.app_id, other.skill_id, C(name='ALPHA-ONE', content='x'))
        with pytest.raises(SkillValidationError):
            SkillService.create_or_update_skill(
                db, a1.app_id, other.skill_id, C(name='beta', content='x', bootstrap_script_path='missing.py'))
        SkillPackageRepository.replace_files(db, other.skill_id, [('run.py', b'1', None)])
        updated = SkillService.create_or_update_skill(
            db, a1.app_id, other.skill_id, C(name='beta', content='x', bootstrap_script_path='./run.py'))
        assert updated.bootstrap_script_path == 'run.py'

    def test_picker_and_valid_ids_exclude_colliding_system_skill(self, db, two_apps):
        a1 = two_apps[0]
        agent = AgentFactory(app=a1)
        SkillFactory(app=a1, name='dup-name')
        clash = SystemSkillFactory(name='Dup-Name')
        fine = SystemSkillFactory(name='fine-sys')
        picker = {s.skill_id for s in AgentRepository.get_selectable_skills_for_app(db, a1.app_id, agent.agent_id)}
        assert clash.skill_id not in picker and fine.skill_id in picker
        from repositories.skill_repository import SkillRepository
        assert SkillRepository.get_valid_skill_ids_for_app(db, {clash.skill_id, fine.skill_id}, a1.app_id) \
            == {fine.skill_id}


class TestAgentSkills:
    def test_update_agent_skills_rules(self, db, two_apps):
        a1, a2 = two_apps
        agent = AgentFactory(app=a1)
        own = SkillFactory(app=a1)
        other = SkillFactory(app=a2)
        sys_on = SystemSkillFactory()
        sys_off = SystemSkillFactory(is_enabled=False)
        svc = AgentService()
        svc.update_agent_skills(db, agent.agent_id, [own.skill_id, other.skill_id, sys_on.skill_id, sys_off.skill_id])
        ids = {a.skill_id for a in AgentRepository.get_agent_skill_associations(db, agent.agent_id)}
        assert ids == {own.skill_id, sys_on.skill_id}

        sys_on.is_enabled = False
        db.flush()
        svc.update_agent_skills(db, agent.agent_id, [own.skill_id, sys_on.skill_id, sys_off.skill_id])
        ids = {a.skill_id for a in AgentRepository.get_agent_skill_associations(db, agent.agent_id)}
        assert ids == {own.skill_id, sys_on.skill_id}  # retained; unattached disabled dropped

        picker = AgentRepository.get_selectable_skills_for_app(db, a1.app_id, agent_id=agent.agent_id)
        by_id = {s.skill_id: s for s in picker}
        assert sys_on.skill_id in by_id and by_id[sys_on.skill_id].is_enabled is False
        assert sys_off.skill_id not in by_id and other.skill_id not in by_id
        no_agent = {s.skill_id for s in AgentRepository.get_selectable_skills_for_app(db, a1.app_id)}
        assert sys_on.skill_id not in no_agent

        svc.update_agent_skills(db, agent.agent_id, [own.skill_id])
        ids = {a.skill_id for a in AgentRepository.get_agent_skill_associations(db, agent.agent_id)}
        assert ids == {own.skill_id}
