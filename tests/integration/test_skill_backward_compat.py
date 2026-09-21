"""Backward compatibility: skills created with only the pre-package fields keep working (AC-3)."""
import pytest

from models.skill import Skill
from services.skill_service import SkillService
from tests.factories import AppFactory, configure_factories

pytestmark = pytest.mark.integration


@pytest.fixture
def legacy_skill(db):
    configure_factories(db)
    app = AppFactory()
    skill = Skill(name="legacy", description="old skill", content="# Legacy\n", app_id=app.app_id)
    db.add(skill)
    db.flush()
    db.refresh(skill)
    return skill


class TestLegacySkill:
    def test_new_columns_take_defaults(self, legacy_skill):
        s = legacy_skill
        assert s.source == 'admin'
        assert s.is_enabled is True
        assert s.display_name is None
        assert s.frontmatter is None
        assert s.allowed_tools is None
        assert s.runtime is None
        assert s.bootstrap_script_path is None
        assert s.runtime_options is None
        assert s.files == []
        assert s.is_system is False

    def test_list_skills_returns_it_unchanged(self, db, legacy_skill):
        items = SkillService.list_skills(db, legacy_skill.app_id)
        assert len(items) == 1
        item = items[0]
        assert (item.skill_id, item.name, item.description) == (legacy_skill.skill_id, "legacy", "old skill")
        assert item.file_count == 0
        assert item.is_enabled is True and item.source == 'admin' and item.is_system is False
        assert item.display_name is None

    def test_get_skill_detail_returns_it_unchanged(self, db, legacy_skill):
        d = SkillService.get_skill_detail(db, legacy_skill.app_id, legacy_skill.skill_id)
        assert d.name == "legacy" and d.content == "# Legacy\n"
        assert d.frontmatter == {} and d.allowed_tools == [] and d.runtime_options == {}
        assert d.runtime is None and d.bootstrap_script_path is None
        assert d.files == []
        assert d.is_enabled is True and d.source == 'admin'

    def test_detail_not_visible_from_other_app(self, db, legacy_skill):
        other = AppFactory()
        assert SkillService.get_skill_detail(db, other.app_id, legacy_skill.skill_id) is None


class TestRouterWiring:
    def test_router_imports_and_service_api_present(self):
        import routers.internal.skills  # noqa: F401
        assert callable(getattr(SkillService, 'list_skills', None))
        assert callable(getattr(SkillService, 'get_skill_detail', None))
