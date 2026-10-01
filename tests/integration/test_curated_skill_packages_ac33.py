"""Integration tests — step_038 (P6 verification gate), AC-33.

For each of the five curated packages (``word``, ``pdf``, ``pptx``, ``data-analysis``, ``charts``,
step_034): seed it via the real ``system_skills_seeder`` (real on-disk packages, real
``system_defaults.yaml`` ``skills:`` block -- nothing monkeypatched, unlike
``tests/integration/test_system_skills_seeder.py``'s synthetic-package tests), confirm it has a
substantive ``SKILL.md`` and at least one bundled resource file, attach it to a real ``Agent`` via
``AgentSkill``, and activate it through ``load_skill`` against a sandbox **double** (never a real
sandbox provider) -- reusing the exact ``FakeProvider``/``FakeHandle`` pattern already established in
``tests/unit/tools/test_skill_activation.py`` (Phase 3) rather than inventing a new one.

Uses the transactional ``db`` fixture (not a real ``SessionLocal()``): everything here, including
``seed_system_skills(db)``, runs and rolls back inside the single per-test savepoint-wrapped
transaction, so nothing persists to the real test DB afterward -- appropriate here because (unlike
``test_system_skills_seeder.py``'s AC-32 concurrency tests) this exercises a single session's content
and attachment behaviour, not cross-session lock semantics.
"""
import pytest

from db.database import SessionLocal
from models.agent import AgentSkill
from models.skill import Skill
from services.skill_package_service import SkillPackageService
from services.system_skills_seeder import seed_system_skills
from tools.skill_tools import SkillSnapshot, create_skill_loader_tool
from tools.sandbox.provider import SkillActivationResult, SkillPhaseResult

_CURATED_NAMES = ("word", "pdf", "pptx", "data-analysis", "charts")


class _FakeHandle:
    """Sandbox handle double -- never a real provider (matches test_skill_activation.py)."""


class _FakeActivatingProvider:
    """Sandbox provider double whose ``ensure_skill`` always reports a clean activation."""

    def __init__(self):
        self.calls = []

    def ensure_skill(self, handle, payload):
        self.calls.append(payload)
        return SkillActivationResult(
            skill_name=payload.name,
            skill_id=payload.skill_id,
            files_dir=f"/workspace/.skills/{payload.name}",
            phases=(
                SkillPhaseResult(phase="files", status="ok", detail="materialised", duration_ms=5),
            ),
            status="active",
        )


@pytest.fixture(scope="module", autouse=True)
def _ensure_real_curated_packages_are_seedable():
    """Sanity precondition, run once for the whole module: the real
    ``backend/system_skills/<name>/`` packages must exist on disk before any test below tries to
    seed and use them -- fails loudly and once, instead of every test below failing individually
    with a confusing "skill not found"."""
    from services.system_skills_seeder import _load_skill_entries, _resolve_package_dir

    entries = _load_skill_entries()
    assert entries is not None
    names = {e["name"] for e in entries}
    assert set(_CURATED_NAMES).issubset(names), (
        f"expected curated packages {_CURATED_NAMES} in system_defaults.yaml skills:, found {names}"
    )
    for name in _CURATED_NAMES:
        entry = next(e for e in entries if e["name"] == name)
        pkg_dir = _resolve_package_dir(entry["path"])
        assert (pkg_dir / "SKILL.md").is_file()


@pytest.mark.parametrize("skill_name", _CURATED_NAMES)
class TestCuratedPackageSeedsAttachesAndActivates:
    def test_seeds_with_substantive_skill_md_and_resource_file(self, skill_name, db):
        seed_system_skills(db)

        skill = (
            db.query(Skill).filter(Skill.app_id.is_(None), Skill.name == skill_name).first()
        )
        assert skill is not None, f"curated package {skill_name!r} was not seeded"
        assert skill.source == "yaml"
        assert skill.is_enabled is True
        # Substantive SKILL.md body: not a thin one-liner placeholder.
        assert len(skill.content.strip()) > 200, (
            f"{skill_name}'s SKILL.md body looks too thin ({len(skill.content.strip())} chars) "
            "to be a real curated package"
        )

        files = SkillPackageService.build_payload(db, skill).files
        assert len(files) >= 1, f"curated package {skill_name!r} has no bundled resource files"

    def test_can_be_attached_to_an_agent(self, skill_name, db, fake_agent):
        seed_system_skills(db)
        skill = (
            db.query(Skill).filter(Skill.app_id.is_(None), Skill.name == skill_name).first()
        )
        assert skill is not None

        assoc = AgentSkill(agent_id=fake_agent.agent_id, skill_id=skill.skill_id)
        db.add(assoc)
        db.flush()

        reloaded = (
            db.query(AgentSkill)
            .filter(AgentSkill.agent_id == fake_agent.agent_id, AgentSkill.skill_id == skill.skill_id)
            .first()
        )
        assert reloaded is not None

    def test_activates_against_a_sandbox_double(self, skill_name, db, fake_agent):
        seed_system_skills(db)
        skill = (
            db.query(Skill).filter(Skill.app_id.is_(None), Skill.name == skill_name).first()
        )
        assert skill is not None

        assoc = AgentSkill(agent_id=fake_agent.agent_id, skill_id=skill.skill_id)
        db.add(assoc)
        db.flush()

        payload = SkillPackageService.build_payload(db, skill)
        snapshot = SkillSnapshot(skill_id=skill.skill_id, name=skill.name, content=skill.content or "")

        provider = _FakeActivatingProvider()
        tool = create_skill_loader_tool(
            [snapshot],
            sandbox_handle=_FakeHandle(),
            sandbox_provider=provider,
            payload_provider=lambda skill_id: payload,
        )
        assert tool is not None

        result = tool.invoke({"skill_name": skill_name})

        assert len(provider.calls) == 1, "the sandbox double's ensure_skill must be called exactly once"
        assert f"Files directory: /workspace/.skills/{payload.name}" in result
        assert "activated" in result
