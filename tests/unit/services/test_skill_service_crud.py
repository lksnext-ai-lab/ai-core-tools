"""Unit tests for SkillService.create_or_update_skill / list_skills / get_skill_detail (no database)."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from schemas.skill_schemas import CreateUpdateSkillSchema
from services.skill_service import SkillService

REPO = "services.skill_service.SkillRepository"
PKG = "services.skill_service.SkillPackageRepository"
TIER = "services.tier_enforcement_service.TierEnforcementService"


def stored_skill(**over):
    attrs = dict(
        skill_id=5, app_id=1, name="old", description="d", content="c",
        display_name="Old Label", runtime="python3.11", bootstrap_script_path="setup.sh",
        allowed_tools='["a"]', runtime_options='{"k": 1}', frontmatter=None,
        is_enabled=True, is_frozen=False, source='admin', create_date=None,
    )
    attrs.update(over)
    return SimpleNamespace(**attrs, **{}) if 'is_system' in attrs else _with_system(attrs)


def _with_system(attrs):
    ns = SimpleNamespace(**attrs)
    ns.is_system = attrs['app_id'] is None
    return ns


def data(**kw):
    return CreateUpdateSkillSchema(name="new", content="body", **kw)


def _assign_id(db, s):
    """Mimic SQLAlchemy assigning a PK on create; SkillDetailSchema requires a non-null skill_id."""
    if s.skill_id is None:
        s.skill_id = 999
    return s


@pytest.fixture
def repo():
    with patch(REPO) as r:
        r.update.side_effect = lambda db, s: s
        r.create.side_effect = _assign_id
        r.get_by_name_and_app_id.return_value = None
        r.get_system_skills.return_value = []
        yield r


def update(repo, skill, **kw):
    repo.get_by_id_and_app_id.return_value = skill
    return SkillService.create_or_update_skill(MagicMock(), 1, skill.skill_id, data(**kw))


class TestCreateOrUpdate:
    def test_omitted_fields_preserve_stored_values(self, repo):
        skill = stored_skill()
        result = update(repo, skill)
        assert result.skill_id == skill.skill_id
        assert (skill.name, skill.content) == ("new", "body")
        assert skill.display_name == "Old Label"
        assert skill.runtime == "python3.11"
        assert skill.bootstrap_script_path == "setup.sh"
        assert skill.allowed_tools == '["a"]'
        assert skill.runtime_options == '{"k": 1}'
        assert skill.is_enabled is True
        assert skill.frontmatter is None

    def test_explicit_null_clears_fields(self, repo):
        skill = stored_skill()
        update(repo, skill, display_name=None, runtime=None, bootstrap_script_path=None,
               allowed_tools=None, runtime_options=None)
        assert skill.display_name is None
        assert skill.runtime is None
        assert skill.bootstrap_script_path is None
        assert skill.allowed_tools is None
        assert skill.runtime_options is None

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_blank_string_clears_string_fields(self, repo, blank):
        skill = stored_skill()
        update(repo, skill, display_name=blank, runtime=blank, bootstrap_script_path=blank)
        assert skill.display_name is None
        assert skill.runtime is None
        assert skill.bootstrap_script_path is None

    def test_empty_allowed_tools_stored_as_empty_json_list(self, repo):
        skill = stored_skill()
        update(repo, skill, allowed_tools=[])
        assert skill.allowed_tools == "[]"

    def test_values_are_stored_and_json_encoded(self, repo):
        skill = stored_skill(display_name=None)
        update(repo, skill, display_name="Label", allowed_tools=["x", "y"], runtime_options={"a": 1})
        assert skill.display_name == "Label"
        assert json.loads(skill.allowed_tools) == ["x", "y"]
        assert json.loads(skill.runtime_options) == {"a": 1}

    def test_is_enabled_none_treated_as_omitted(self, repo):
        skill = stored_skill(is_enabled=False)
        update(repo, skill, is_enabled=None)
        assert skill.is_enabled is False

    def test_is_enabled_explicit_value_applied(self, repo):
        skill = stored_skill(is_enabled=True)
        update(repo, skill, is_enabled=False)
        assert skill.is_enabled is False

    def test_when_to_use_written_to_frontmatter(self, repo):
        skill = stored_skill()
        update(repo, skill, when_to_use="always")
        assert json.loads(skill.frontmatter) == {"when_to_use": "always"}

    def test_app_id_none_raises(self, repo):
        with pytest.raises(ValueError):
            SkillService.create_or_update_skill(MagicMock(), None, 5, data())
        repo.get_by_id_and_app_id.assert_not_called()

    def test_unknown_skill_returns_none(self, repo):
        repo.get_by_id_and_app_id.return_value = None
        repo.get_system_skill_by_id.return_value = None
        assert SkillService.create_or_update_skill(MagicMock(), 1, 99, data()) is None
        repo.update.assert_not_called()

    def test_update_commits_through_repository_update(self, repo):
        skill = stored_skill()
        update(repo, skill)
        repo.update.assert_called_once()
        repo.create.assert_not_called()

    def test_create_checks_tier_limit_and_scopes_to_app(self, repo):
        with patch(TIER) as tier:
            result = SkillService.create_or_update_skill(MagicMock(), 7, 0, data(display_name="L"))
        tier.check_resource_limit.assert_called_once()
        assert tier.check_resource_limit.call_args.args[1:] == (7, 'skills')
        repo.create.assert_called_once()
        created_skill = repo.create.call_args.args[1]
        assert created_skill.app_id == 7
        assert result.display_name == "L"
        assert result.name == "new"

    def test_create_tier_failure_prevents_creation(self, repo):
        with patch(TIER) as tier:
            tier.check_resource_limit.side_effect = RuntimeError("limit")
            with pytest.raises(RuntimeError):
                SkillService.create_or_update_skill(MagicMock(), 7, 0, data())
        repo.create.assert_not_called()


class TestListSkills:
    def test_one_grouped_count_call(self, repo):
        skills = [stored_skill(skill_id=1), stored_skill(skill_id=2, is_enabled=None, source=None)]
        repo.list_for_app.return_value = skills
        with patch(PKG) as pkg:
            pkg.count_by_skill_ids.return_value = {1: 3}
            items = SkillService.list_skills(MagicMock(), 1)
        pkg.count_by_skill_ids.assert_called_once()
        assert pkg.count_by_skill_ids.call_args.args[1] == [1, 2]
        assert [(i.skill_id, i.file_count) for i in items] == [(1, 3), (2, 0)]
        assert items[1].is_enabled is True
        assert items[1].source == 'admin'

    def test_count_skipped_when_empty(self, repo):
        repo.list_for_app.return_value = []
        with patch(PKG) as pkg:
            assert SkillService.list_skills(MagicMock(), 1) == []
        pkg.count_by_skill_ids.assert_not_called()


class TestGetSkillDetail:
    def test_new_skill_response(self, repo):
        detail = SkillService.get_skill_detail(MagicMock(), 1, 0)
        assert detail.skill_id == 0
        assert detail.name == "" and detail.content == ""
        assert detail.files == []
        repo.get_by_id_and_app_id.assert_not_called()

    def test_missing_returns_none(self, repo):
        repo.get_by_id_and_app_id.return_value = None
        repo.get_system_skill_by_id.return_value = None
        assert SkillService.get_skill_detail(MagicMock(), 1, 5) is None

    def test_files_mapped_from_five_tuples_and_json_decoded(self, repo):
        repo.get_by_id_and_app_id.return_value = stored_skill(
            frontmatter='{"when_to_use": "x"}', allowed_tools='["a", 1]'
        )
        rows = [
            ("a/b.md", "text/markdown", 10, "c" * 64, True),
            ("img.png", None, 99, "d" * 64, False),
        ]
        with patch(PKG) as pkg:
            pkg.list_paths.return_value = rows
            detail = SkillService.get_skill_detail(MagicMock(), 1, 5)
        assert [(f.path, f.media_type, f.size_bytes, f.checksum_sha256, f.is_text) for f in detail.files] == rows
        assert detail.frontmatter == {"when_to_use": "x"}
        assert detail.allowed_tools == ["a"]
        assert detail.runtime_options == {"k": 1}
        assert detail.is_system is False

    def test_malformed_stored_json_tolerated(self, repo):
        repo.get_by_id_and_app_id.return_value = stored_skill(frontmatter="{bad", allowed_tools="{bad")
        with patch(PKG) as pkg:
            pkg.list_paths.return_value = []
            detail = SkillService.get_skill_detail(MagicMock(), 1, 5)
        assert detail.frontmatter == {} and detail.allowed_tools == []


class TestSystemSkillIntegrityBackstop:
    """The uq_skill_system_name index can still be lost to a race the advisory lock does not cover for
    system skills (there is no per-system-scope advisory lock, only the DB constraint); the service must
    still turn a lost race into a typed 409, never an unhandled IntegrityError."""

    def test_create_integrity_error_maps_to_conflict_and_rolls_back(self):
        from sqlalchemy.exc import IntegrityError
        from services.skill_errors import SkillConflictError

        with patch("services.skill_service.SkillRepository") as repo:
            repo.get_system_skill_by_name.return_value = None
            repo.create.side_effect = IntegrityError("stmt", {}, Exception("uq_skill_system_name"))
            db = MagicMock()
            with pytest.raises(SkillConflictError) as ei:
                SkillService.create_or_update_system_skill(db, 0, CreateUpdateSkillSchema(name="dup", content="c"))
            db.rollback.assert_called_once()
            assert ei.value.status_code == 409

    def test_rename_integrity_error_maps_to_conflict_and_rolls_back(self):
        from sqlalchemy.exc import IntegrityError
        from services.skill_errors import SkillConflictError

        existing = stored_skill(app_id=None, name="old-sys")
        with patch("services.skill_service.SkillRepository") as repo:
            repo.get_system_skill_by_id.return_value = existing
            repo.get_system_skill_by_name.return_value = None
            repo.update.side_effect = IntegrityError("stmt", {}, Exception("uq_skill_system_name"))
            db = MagicMock()
            with pytest.raises(SkillConflictError):
                SkillService.create_or_update_system_skill(db, existing.skill_id, CreateUpdateSkillSchema(name="new-sys", content="c"))
            db.rollback.assert_called_once()


class TestDeleteTranslatesRepositoryRuntimeError:
    """SkillRepository.delete raises a plain RuntimeError (data layer, no HTTP-shaped decision);
    SkillService must translate it to the typed SkillConflictError at the service boundary."""

    def test_delete_skill_translates_runtime_error(self):
        from services.skill_errors import SkillConflictError

        with patch("services.skill_service.SkillRepository") as repo:
            repo.delete_by_id_and_app_id.side_effect = RuntimeError("skill is in use; retry")
            with pytest.raises(SkillConflictError) as ei:
                SkillService.delete_skill(MagicMock(), 1, 5)
        assert ei.value.status_code == 409 and "retry" in ei.value.detail

    def test_delete_system_skill_translates_runtime_error(self):
        from services.skill_errors import SkillConflictError

        skill = stored_skill(app_id=None, source='admin', is_frozen=False)
        with patch("services.skill_service.SkillRepository") as repo:
            repo.get_system_skill_by_id.return_value = skill
            repo.get_attachment_stats.return_value = (0, [])
            repo.delete.side_effect = RuntimeError("skill is in use; retry")
            with pytest.raises(SkillConflictError) as ei:
                SkillService.delete_system_skill(MagicMock(), skill.skill_id)
        assert ei.value.status_code == 409 and "retry" in ei.value.detail
