"""Regression lock for FR-15/AC-12: skills quota / freeze / cascade-delete must stay app-private.

Confirms system skills (Skill.app_id IS NULL) are never counted, frozen, or deleted as a side
effect of a tenant-scoped operation. Covers the three call sites documented in the
backend/services/skill_service.py module docstring (step_014):
  - TierEnforcementService.check_resource_limit — the "skills" quota only counts an app's own skills.
  - FreezeService.apply_freeze — freezing excess skills on a tier downgrade never touches system skills.
  - AppRepository.get_skills_by_app_id (via AppService.delete_app) — deleting an app never deletes
    platform-owned system skills or their SkillFile rows, and never raises an FK error.

Requires a real PostgreSQL test database (port 5433).
Run with: pytest tests/integration/services/test_skill_app_private_scoping.py -v
"""
import pytest
from fastapi import HTTPException

from models.app import App
from models.skill import Skill, SkillFile
from models.subscription import BillingStatus, Subscription, SubscriptionTier
from models.tier_config import TierConfig
from tests.factories import AppFactory, SkillFactory, SkillFileFactory, SystemSkillFactory, UserFactory, configure_factories

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Environment: enable SaaS mode so tier enforcement / freeze are not no-ops
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function", autouse=True)
def saas_env(monkeypatch):
    monkeypatch.setenv("AICT_DEPLOYMENT_MODE", "saas")
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_fake")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_fake")
    monkeypatch.setenv("STRIPE_PRICE_ID_STARTER", "price_starter_fake")
    monkeypatch.setenv("STRIPE_PRICE_ID_PRO", "price_pro_fake")
    monkeypatch.setenv("EMAIL_FROM", "noreply@test.com")

    import importlib

    import deployment_mode as dm
    importlib.reload(dm)
    import services.freeze_service as fs
    importlib.reload(fs)
    import services.tier_enforcement_service as tes
    importlib.reload(tes)

    yield

    monkeypatch.setenv("AICT_DEPLOYMENT_MODE", "self_managed")
    importlib.reload(dm)
    importlib.reload(fs)
    importlib.reload(tes)


def _seed_tier_config(db, tier: str, skills_limit: int) -> None:
    """Seed a full set of 'free'-tier limits (skills tunable), unlimited everywhere else."""
    configs = [
        (tier, "apps", -1),
        (tier, "agents", -1),
        (tier, "silos", -1),
        (tier, "skills", skills_limit),
        (tier, "mcp_servers", -1),
        (tier, "collaborators", -1),
        (tier, "llm_calls", -1),
    ]
    for t, resource, limit in configs:
        existing = db.query(TierConfig).filter(TierConfig.tier == t, TierConfig.resource_type == resource).first()
        if existing:
            existing.limit_value = limit
        else:
            db.add(TierConfig(tier=t, resource_type=resource, limit_value=limit))
    db.flush()


@pytest.fixture
def scoped_app(db):
    """A Free-tier user/app with 1 private (app-owned) skill and 2 system skills.

    One system skill also carries a SkillFile row, so cascade-delete FK safety can be asserted.
    """
    configure_factories(db)

    user = UserFactory()
    db.flush()
    db.add(Subscription(
        user_id=user.user_id, tier=SubscriptionTier.FREE, billing_status=BillingStatus.ACTIVE,
        stripe_customer_id=f"cus_free_{user.user_id}",
    ))
    app = AppFactory(owner=user)
    db.flush()

    app_skill = SkillFactory(app=app, name="app-private-skill")
    system_skill_1 = SystemSkillFactory(name="system-skill-alpha")
    system_skill_2 = SystemSkillFactory(name="system-skill-beta")
    db.flush()
    system_file = SkillFileFactory(skill=system_skill_1, path="references/notes.md")
    db.flush()

    return {
        "user": user, "app": app, "app_skill": app_skill,
        "system_skills": [system_skill_1, system_skill_2], "system_file": system_file,
    }


# ---------------------------------------------------------------------------
# (a) Quota: system skills are never counted against an app's skill limit
# ---------------------------------------------------------------------------

class TestQuotaExcludesSystemSkills:

    def test_check_resource_limit_ignores_system_skills(self, db, scoped_app):
        """Free tier skills limit=2; 1 private skill + 2 system skills visible.

        If system skills were counted, the merged total (3) would already exceed the limit (2) and
        this call would raise. Because only the private skill (1) is counted, it must pass.
        """
        from services.tier_enforcement_service import TierEnforcementService

        _seed_tier_config(db, "free", skills_limit=2)
        app = scoped_app["app"]

        # Sanity: 1 private skill + 2 system skills are visible to the app (merged listing).
        assert db.query(Skill).filter(Skill.app_id == app.app_id).count() == 1
        assert db.query(Skill).filter(Skill.app_id.is_(None)).count() == 2

        # Should NOT raise: only the 1 private skill is counted against the limit of 2.
        TierEnforcementService.check_resource_limit(db, app.app_id, "skills")

    def test_check_resource_limit_blocks_on_private_count_alone(self, db, scoped_app):
        """Adding a 2nd private skill (private count == limit) blocks, proving the count is private-only."""
        from services.tier_enforcement_service import TierEnforcementService

        _seed_tier_config(db, "free", skills_limit=2)
        app = scoped_app["app"]

        SkillFactory(app=app, name="app-private-skill-2")
        db.flush()

        with pytest.raises(HTTPException) as exc_info:
            TierEnforcementService.check_resource_limit(db, app.app_id, "skills")
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# (b) Freeze: freezing an app's skills never touches system skills
# ---------------------------------------------------------------------------

class TestFreezeExcludesSystemSkills:

    def test_apply_freeze_never_freezes_system_skills(self, db, scoped_app):
        """Downgrading to a skills limit of 0 freezes the private skill but leaves system skills untouched."""
        from services.freeze_service import FreezeService

        _seed_tier_config(db, "free", skills_limit=0)
        user = scoped_app["user"]
        app_skill = scoped_app["app_skill"]
        system_skills = scoped_app["system_skills"]

        FreezeService.apply_freeze(db, user.user_id, "free")
        db.flush()

        db.refresh(app_skill)
        assert app_skill.is_frozen is True

        for system_skill in system_skills:
            db.refresh(system_skill)
            assert system_skill.is_frozen is False, "System skills must never be frozen by app-tier downgrades"

    def test_recalculate_on_delete_never_touches_system_skills(self, db, scoped_app):
        """recalculate_on_delete's generic model_map path also stays app-private for skills."""
        from services.freeze_service import FreezeService

        _seed_tier_config(db, "free", skills_limit=0)
        user = scoped_app["user"]
        app = scoped_app["app"]
        system_skills = scoped_app["system_skills"]

        FreezeService.recalculate_on_delete(db, user.user_id, "skills", app_id=app.app_id)
        db.flush()

        for system_skill in system_skills:
            db.refresh(system_skill)
            assert system_skill.is_frozen is False


# ---------------------------------------------------------------------------
# (c) Cascade delete: deleting an app never deletes system skills or their files
# ---------------------------------------------------------------------------

class TestCascadeDeleteExcludesSystemSkills:

    def test_delete_app_leaves_system_skills_and_files_intact(self, db, scoped_app):
        """AppService.delete_app must succeed (no FK error) and leave every system skill untouched."""
        from services.app_service import AppService

        app = scoped_app["app"]
        app_skill_id = scoped_app["app_skill"].skill_id
        system_skill_ids = [s.skill_id for s in scoped_app["system_skills"]]
        system_file_id = scoped_app["system_file"].id

        result = AppService(db).delete_app(app.app_id)

        # No FK error was swallowed by delete_app's broad except-and-rollback: it actually succeeded.
        assert result is True
        assert db.query(App).filter(App.app_id == app.app_id).first() is None

        # The app's own skill is gone along with the app.
        assert db.query(Skill).filter(Skill.skill_id == app_skill_id).first() is None

        # Every system skill and its SkillFile rows are completely intact.
        for skill_id in system_skill_ids:
            assert db.query(Skill).filter(Skill.skill_id == skill_id).first() is not None
        assert db.query(SkillFile).filter(SkillFile.id == system_file_id).first() is not None


# ---------------------------------------------------------------------------
# (d) Security hardening: a leftover Skill row must never be nullified into a
#     platform-wide system skill by app deletion (verified HIGH finding).
# ---------------------------------------------------------------------------

class TestLeftoverSkillNeverNullified:
    """App.skills has no delete cascade and Skill.app_id's FK has no ondelete, so the ORM's default
    behaviour on `db.delete(app)` is to NULL out app_id on any leftover Skill row instead of
    deleting it or raising — silently promoting a tenant skill (with attacker-chosen
    content/bootstrap_script_path) into a platform-wide system skill visible to every tenant.

    Fix: `App.skills` now sets `passive_deletes='all'` so the ORM never issues that UPDATE; the
    FK's default NO ACTION then makes Postgres raise IntegrityError on a leftover row, which
    AppRepository.delete / AppService.delete_app already catch and turn into a clean `False`.
    """

    def test_app_repository_delete_never_nullifies_a_leftover_skill(self, db):
        """Item 1 (ORM/DB-level guard): bypass AppService's cascade entirely and call
        AppRepository.delete() directly with a skill still attached, simulating what would happen
        if the race-window re-check (item 2) were ever bypassed or itself raced."""
        from repositories.app_repository import AppRepository

        configure_factories(db)
        user = UserFactory()
        db.flush()
        app = AppFactory(owner=user)
        skill = SkillFactory(app=app, name="leftover-skill")
        # Commit the setup to its own savepoint (join_transaction_mode="create_savepoint"): the
        # `db` fixture's outer rollback at teardown still undoes this, but it establishes a
        # boundary so that delete()'s internal error-path rollback (below) only undoes the failed
        # delete attempt, not this test's fixture setup — matching a realistic "app already
        # existed" scenario rather than an artifact of nested-savepoint test isolation.
        db.commit()

        system_skill_count_before = db.query(Skill).filter(Skill.app_id.is_(None)).count()

        result = AppRepository(db).delete(app)

        assert result is False, "delete() must fail loudly rather than silently nullifying app_id"
        # The App row survives — AppRepository.delete's except path rolled back the failed delete.
        assert db.query(App).filter(App.app_id == app.app_id).first() is not None

        # The skill is completely untouched: still app-private, never promoted to a system skill.
        db.refresh(skill)
        assert skill.app_id == app.app_id
        assert db.query(Skill).filter(Skill.app_id.is_(None)).count() == system_skill_count_before

    def test_skill_created_during_cascade_aborts_delete_app(self, db, monkeypatch):
        """Item 2 (race-window re-check): a skill created after step 2's skill enumeration but
        before the final delete step (simulated here via a hook on a later cascade step, mirroring
        a concurrent import landing in that window) is caught by the pre-delete re-check and aborts
        the whole deletion — it never reaches the ORM/FK layer at all."""
        from repositories.app_repository import AppRepository
        from services.app_service import AppService

        configure_factories(db)
        user = UserFactory()
        db.flush()
        app = AppFactory(owner=user)
        # See the comment in the previous test: commit this setup to its own savepoint so that
        # delete_app's internal rollback-on-abort (below) doesn't also undo the fixture setup.
        db.commit()

        system_skill_count_before = db.query(Skill).filter(Skill.app_id.is_(None)).count()

        service = AppService(db)
        original_get_mcp_servers = AppRepository.get_mcp_servers_by_app_id
        race_skill = {}

        def racy_get_mcp_servers_by_app_id(self, app_id):
            # Step 3 runs right after step 2 (skill enumeration/deletion) — simulate a skill import
            # completing concurrently, landing in that window, before this call returns. A real
            # concurrent import (SkillPackageService.import_package, on its own DB session) commits
            # before it's visible to anyone else, so commit here too rather than just flushing —
            # otherwise this test's own later rollback (on abort) would undo the "concurrent" insert
            # along with it, which a real second transaction would never be subject to.
            if app_id == app.app_id and "skill_id" not in race_skill:
                skill = SkillFactory(app=app, name="race-window-skill")
                db.commit()
                race_skill["skill_id"] = skill.skill_id
            return original_get_mcp_servers(self, app_id)

        monkeypatch.setattr(AppRepository, "get_mcp_servers_by_app_id", racy_get_mcp_servers_by_app_id)

        result = service.delete_app(app.app_id)

        assert result is False, "delete_app must abort when a skill appears after enumeration"
        assert "skill_id" in race_skill, "the race hook never fired — test setup is broken"

        # The app survives — the race check aborted before the final delete step.
        assert db.query(App).filter(App.app_id == app.app_id).first() is not None

        # The race-window skill is untouched: neither deleted nor promoted to a system skill.
        leftover = db.query(Skill).filter(Skill.skill_id == race_skill["skill_id"]).first()
        assert leftover is not None
        assert leftover.app_id == app.app_id
        assert db.query(Skill).filter(Skill.app_id.is_(None)).count() == system_skill_count_before
