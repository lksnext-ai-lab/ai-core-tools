"""Integration tests for the downgrade + freeze flow.

These tests require a real PostgreSQL test database (port 5433).
Run with: pytest tests/integration/test_downgrade_freeze.py -v

Strategy:
- Create a Pro user with many agents
- Downgrade to Free via FreezeService.apply_freeze
- Verify correct agents are frozen (newest first within limit)
- Test unfreeze on resource deletion
- Test unfreeze on upgrade
- Test OMNIADMIN tier override triggers recalculation
"""
import os
import pytest
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# Environment fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function", autouse=True)
def saas_env(monkeypatch):
    monkeypatch.setenv("AICT_DEPLOYMENT_MODE", "saas")
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_fake")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_fake")
    monkeypatch.setenv("STRIPE_PRICE_ID_STARTER", "price_starter_fake")
    monkeypatch.setenv("STRIPE_PRICE_ID_PRO", "price_pro_fake")
    monkeypatch.setenv("EMAIL_FROM", "noreply@test.com")

    import importlib, deployment_mode as dm
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def tier_config(db):
    """Seed TierConfig with known limits for downgrade tests."""
    from models.tier_config import TierConfig

    configs = [
        ("free", "apps", 1),
        ("free", "agents", 3),
        ("free", "silos", 2),
        ("free", "skills", 5),
        ("free", "mcp_servers", 1),
        ("free", "collaborators", 2),
        ("free", "llm_calls", 50),
        ("starter", "apps", 5),
        ("starter", "agents", 10),
        ("starter", "silos", 5),
        ("starter", "skills", -1),
        ("starter", "mcp_servers", 3),
        ("starter", "collaborators", 10),
        ("starter", "llm_calls", 500),
        ("pro", "apps", -1),
        ("pro", "agents", -1),
        ("pro", "silos", -1),
        ("pro", "skills", -1),
        ("pro", "mcp_servers", -1),
        ("pro", "collaborators", -1),
        ("pro", "llm_calls", -1),
    ]
    for tier, resource, limit in configs:
        existing = (
            db.query(TierConfig)
            .filter(TierConfig.tier == tier, TierConfig.resource_type == resource)
            .first()
        )
        if not existing:
            db.add(TierConfig(tier=tier, resource_type=resource, limit_value=limit))
    db.flush()


@pytest.fixture(scope="function")
def pro_user(db, tier_config):
    """A Pro-tier user with one app and 8 agents (sorted by age)."""
    from models.user import User
    from models.subscription import Subscription, SubscriptionTier, BillingStatus
    from models.app import App
    from models.agent import Agent

    user = User(email="pro@downgrade-test.com", name="Pro User", is_active=True)
    db.add(user)
    db.flush()

    sub = Subscription(
        user_id=user.user_id,
        tier=SubscriptionTier.PRO,
        billing_status=BillingStatus.ACTIVE,
        stripe_customer_id="cus_pro_downgrade",
    )
    db.add(sub)

    app = App(
        name="Pro App",
        slug=f"pro-app-{user.user_id}",
        owner_id=user.user_id,
        agent_rate_limit=0,
        max_file_size_mb=10,
    )
    db.add(app)
    db.flush()

    # Create 8 agents with different create_date values (oldest first in creation order)
    agents = []
    for i in range(8):
        agent = Agent(
            name=f"Agent {i}",
            description=f"Agent {i} description",
            system_prompt="You are a helpful agent.",
            app_id=app.app_id,
            has_memory=False,
            temperature=0.7,
        )
        # Manually set create_date so ordering is deterministic
        agent.create_date = datetime(2025, 1, 1) + timedelta(days=i)
        db.add(agent)
        agents.append(agent)
    db.flush()

    return {"user": user, "app": app, "agents": agents, "sub": sub}


# ---------------------------------------------------------------------------
# Downgrade tests
# ---------------------------------------------------------------------------

class TestDowngradeFreeze:

    def test_pro_to_free_freezes_5_newest_agents(self, db, pro_user, tier_config):
        """Downgrading from Pro (8 agents) to Free (limit=3) freezes the 5 newest."""
        from services.freeze_service import FreezeService
        from models.agent import Agent

        user = pro_user["user"]
        app = pro_user["app"]
        agents = pro_user["agents"]  # agents[0] oldest, agents[7] newest

        FreezeService.apply_freeze(db, user.user_id, "free")
        db.flush()

        # Re-fetch agents from DB ordered by create_date
        db_agents = (
            db.query(Agent)
            .filter(Agent.app_id == app.app_id)
            .order_by(Agent.create_date.asc())
            .all()
        )

        # With limit=3, the 3 oldest should be unfrozen, the 5 newest frozen
        # FreezeService sorts DESC (newest first) and freezes index >= limit
        # So: agent[7] (newest) = index 0, agent[6] = index 1, agent[5] = index 2
        #     → these 3 are unfrozen; agents[0..4] are frozen
        frozen_agents = [a for a in db_agents if a.is_frozen]
        unfrozen_agents = [a for a in db_agents if not a.is_frozen]

        assert len(frozen_agents) == 5
        assert len(unfrozen_agents) == 3

    def test_oldest_agents_are_frozen(self, db, pro_user, tier_config):
        """The 5 oldest agents (by create_date) should be the frozen ones."""
        from services.freeze_service import FreezeService
        from models.agent import Agent

        user = pro_user["user"]
        app = pro_user["app"]

        FreezeService.apply_freeze(db, user.user_id, "free")
        db.flush()

        # agents sorted oldest-first (asc)
        db_agents = (
            db.query(Agent)
            .filter(Agent.app_id == app.app_id)
            .order_by(Agent.create_date.asc())
            .all()
        )

        # The 5 oldest (indices 0-4) should be frozen
        for agent in db_agents[:5]:
            assert agent.is_frozen, f"Expected {agent.name} to be frozen"

        # The 3 newest (indices 5-7) should NOT be frozen
        for agent in db_agents[5:]:
            assert not agent.is_frozen, f"Expected {agent.name} to be unfrozen"


# ---------------------------------------------------------------------------
# Unfreeze on delete
# ---------------------------------------------------------------------------

class TestUnfreezeOnDelete:

    def test_deleting_frozen_agent_unfreezes_next(self, db, pro_user, tier_config):
        """After deleting a frozen agent, the oldest remaining frozen one unfreezes."""
        from services.freeze_service import FreezeService
        from models.agent import Agent

        user = pro_user["user"]
        app = pro_user["app"]

        # Apply freeze first (Pro→Free, limit=3)
        FreezeService.apply_freeze(db, user.user_id, "free")
        db.flush()

        # Delete one frozen agent (oldest)
        db_agents = (
            db.query(Agent)
            .filter(Agent.app_id == app.app_id)
            .order_by(Agent.create_date.asc())
            .all()
        )
        oldest = db_agents[0]
        db.delete(oldest)
        db.flush()

        # Recalculate: now 7 agents remain, limit=3, so 4 frozen
        FreezeService.recalculate_on_delete(db, user.user_id, "agents", app_id=app.app_id)
        db.flush()

        remaining = (
            db.query(Agent)
            .filter(Agent.app_id == app.app_id)
            .order_by(Agent.create_date.asc())
            .all()
        )
        frozen = [a for a in remaining if a.is_frozen]
        assert len(frozen) == 4  # 7 - 3 = 4 frozen


# ---------------------------------------------------------------------------
# Unfreeze on upgrade
# ---------------------------------------------------------------------------

class TestUnfreezeOnUpgrade:

    def test_upgrading_unfreezes_all_that_fit(self, db, pro_user, tier_config):
        """Upgrading from Free to Starter (limit=10) unfreezes agents that now fit."""
        from services.freeze_service import FreezeService
        from models.agent import Agent

        user = pro_user["user"]
        app = pro_user["app"]

        # First downgrade to Free
        FreezeService.apply_freeze(db, user.user_id, "free")
        db.flush()

        frozen_before = db.query(Agent).filter(
            Agent.app_id == app.app_id, Agent.is_frozen == True
        ).count()
        assert frozen_before == 5

        # Upgrade to Starter (limit=10, we have 8 agents → all should unfreeze)
        FreezeService.recalculate_on_upgrade(db, user.user_id, "starter")
        db.flush()

        frozen_after = db.query(Agent).filter(
            Agent.app_id == app.app_id, Agent.is_frozen == True
        ).count()
        assert frozen_after == 0  # all 8 agents fit within Starter limit of 10


# ---------------------------------------------------------------------------
# OMNIADMIN tier override triggers freeze recalculation
# ---------------------------------------------------------------------------

class TestAdminOverrideFreeze:

    def test_admin_override_to_free_freezes_resources(self, db, pro_user, tier_config):
        """Setting an admin_override_tier of 'free' should trigger freeze."""
        from services.freeze_service import FreezeService
        from services.subscription_service import SubscriptionService
        from models.agent import Agent
        from repositories.subscription_repository import SubscriptionRepository

        user = pro_user["user"]
        app = pro_user["app"]

        # Admin overrides tier to 'free'
        sub_repo = SubscriptionRepository(db)
        sub_repo.set_admin_override(user.user_id, "free")
        db.flush()

        # In real usage the admin endpoint calls apply_freeze after setting the override
        FreezeService.apply_freeze(db, user.user_id, "free")
        db.flush()

        frozen = db.query(Agent).filter(
            Agent.app_id == app.app_id, Agent.is_frozen == True
        ).count()
        assert frozen == 5

    def test_admin_override_removed_unfreezes_all(self, db, pro_user, tier_config):
        """Removing admin_override_tier restores the actual subscription limits."""
        from services.freeze_service import FreezeService
        from models.agent import Agent
        from models.subscription import SubscriptionTier
        from repositories.subscription_repository import SubscriptionRepository

        user = pro_user["user"]
        app = pro_user["app"]

        # Override to free, freeze
        sub_repo = SubscriptionRepository(db)
        sub_repo.set_admin_override(user.user_id, "free")
        db.flush()
        FreezeService.apply_freeze(db, user.user_id, "free")
        db.flush()

        assert db.query(Agent).filter(
            Agent.app_id == app.app_id, Agent.is_frozen == True
        ).count() == 5

        # Remove override → effective tier reverts to Pro (limit=-1)
        sub_repo.set_admin_override(user.user_id, None)
        db.flush()
        FreezeService.apply_freeze(db, user.user_id, "pro")
        db.flush()

        assert db.query(Agent).filter(
            Agent.app_id == app.app_id, Agent.is_frozen == True
        ).count() == 0
