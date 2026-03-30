"""Integration tests for SaaS resource limit enforcement.

These tests require a real PostgreSQL test database (port 5433).
Run with: pytest tests/integration/test_saas_limits.py -v

Strategy:
- Seed TierConfig rows with known small limits
- Create a Free user with a Subscription record
- Call TierEnforcementService directly (service layer, not HTTP) against the real DB
- Verify that the correct HTTP exceptions are raised when limits are reached
"""
import os
import pytest
from datetime import date
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def saas_env(monkeypatch):
    """Switch deployment mode to SaaS for the duration of the test."""
    monkeypatch.setenv("AICT_DEPLOYMENT_MODE", "saas")
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_fake")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_fake")
    monkeypatch.setenv("STRIPE_PRICE_ID_STARTER", "price_starter_fake")
    monkeypatch.setenv("STRIPE_PRICE_ID_PRO", "price_pro_fake")
    monkeypatch.setenv("EMAIL_FROM", "noreply@test.com")

    # Reload deployment_mode so is_saas_mode() re-reads the env var
    import importlib
    import deployment_mode as dm
    importlib.reload(dm)

    # Reload services that import is_self_managed at module level
    import services.tier_enforcement_service as tes
    importlib.reload(tes)

    yield

    # Teardown: restore self_managed
    monkeypatch.setenv("AICT_DEPLOYMENT_MODE", "self_managed")
    importlib.reload(dm)
    importlib.reload(tes)


@pytest.fixture(scope="function")
def saas_user(db):
    """A User with a Free subscription and tier config seeded."""
    from models.user import User
    from models.subscription import Subscription, SubscriptionTier, BillingStatus
    from models.tier_config import TierConfig

    user = User(email="saas_user@test.com", name="SaaS User", is_active=True)
    db.add(user)
    db.flush()

    sub = Subscription(
        user_id=user.user_id,
        tier=SubscriptionTier.FREE,
        billing_status=BillingStatus.NONE,
    )
    db.add(sub)

    # Seed small limits for this test
    limit_configs = [
        ("free", "apps", 2),
        ("free", "agents", 3),
        ("free", "silos", 2),
        ("free", "skills", 5),
        ("free", "mcp_servers", 1),
        ("free", "collaborators", 2),
        ("free", "llm_calls", 50),
        ("starter", "apps", 10),
        ("starter", "agents", 10),
        ("starter", "llm_calls", 500),
        ("pro", "apps", -1),
        ("pro", "agents", -1),
        ("pro", "llm_calls", -1),
    ]
    for tier, resource, limit in limit_configs:
        existing = (
            db.query(TierConfig)
            .filter(TierConfig.tier == tier, TierConfig.resource_type == resource)
            .first()
        )
        if not existing:
            db.add(TierConfig(tier=tier, resource_type=resource, limit_value=limit))

    db.flush()
    return user


@pytest.fixture(scope="function")
def saas_app(db, saas_user):
    """An App owned by saas_user."""
    from models.app import App
    app = App(
        name="SaaS Test App",
        slug=f"saas-test-app-{saas_user.user_id}",
        owner_id=saas_user.user_id,
        agent_rate_limit=0,
        max_file_size_mb=10,
    )
    db.add(app)
    db.flush()
    return app


# ---------------------------------------------------------------------------
# App limit tests
# ---------------------------------------------------------------------------

class TestAppLimit:

    def test_free_user_can_create_up_to_limit(self, db, saas_user, saas_env):
        """A Free user at 1 app (below limit=2) should not be blocked."""
        from services.tier_enforcement_service import TierEnforcementService
        from models.app import App

        # Create 1 app (below limit of 2)
        app = App(
            name="App 1",
            slug=f"app-1-{saas_user.user_id}",
            owner_id=saas_user.user_id,
            agent_rate_limit=0,
            max_file_size_mb=10,
        )
        db.add(app)
        db.flush()

        # Should not raise — still below limit
        TierEnforcementService.check_app_limit(db, saas_user.user_id)

    def test_free_user_blocked_at_app_limit(self, db, saas_user, saas_env):
        """A Free user with 2 apps (at limit=2) should be blocked from creating more."""
        from services.tier_enforcement_service import TierEnforcementService
        from models.app import App

        for i in range(2):
            app = App(
                name=f"App {i}",
                slug=f"app-limit-{i}-{saas_user.user_id}",
                owner_id=saas_user.user_id,
                agent_rate_limit=0,
                max_file_size_mb=10,
            )
            db.add(app)
        db.flush()

        with pytest.raises(HTTPException) as exc_info:
            TierEnforcementService.check_app_limit(db, saas_user.user_id)

        assert exc_info.value.status_code == 403
        assert "App limit reached" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Agent limit tests
# ---------------------------------------------------------------------------

class TestAgentLimit:

    def test_free_user_blocked_at_agent_limit(self, db, saas_user, saas_app, saas_env):
        """Free user with 3 agents (at limit=3) cannot create more."""
        from services.tier_enforcement_service import TierEnforcementService
        from models.agent import Agent

        for i in range(3):
            agent = Agent(
                name=f"Agent {i}",
                description="test",
                system_prompt="You are an agent.",
                app_id=saas_app.app_id,
                has_memory=False,
                temperature=0.7,
            )
            db.add(agent)
        db.flush()

        with pytest.raises(HTTPException) as exc_info:
            TierEnforcementService.check_resource_limit(db, saas_app.app_id, "agents")

        assert exc_info.value.status_code == 403

    def test_free_user_can_create_agents_below_limit(self, db, saas_user, saas_app, saas_env):
        """Free user with 2 agents (below limit=3) passes the check."""
        from services.tier_enforcement_service import TierEnforcementService
        from models.agent import Agent

        for i in range(2):
            agent = Agent(
                name=f"Agent {i}",
                description="test",
                system_prompt="You are an agent.",
                app_id=saas_app.app_id,
                has_memory=False,
                temperature=0.7,
            )
            db.add(agent)
        db.flush()

        # Should not raise
        TierEnforcementService.check_resource_limit(db, saas_app.app_id, "agents")


# ---------------------------------------------------------------------------
# LLM quota tests
# ---------------------------------------------------------------------------

class TestLlmQuota:

    def test_free_user_blocked_at_call_quota(self, db, saas_user, saas_env):
        """Free user at 100% quota (50 calls) is blocked with 429."""
        from services.tier_enforcement_service import TierEnforcementService
        from models.usage_record import UsageRecord

        usage = UsageRecord(
            user_id=saas_user.user_id,
            billing_period_start=date.today().replace(day=1),
            call_count=50,  # at the limit
        )
        db.add(usage)
        db.flush()

        with pytest.raises(HTTPException) as exc_info:
            TierEnforcementService.check_system_llm_quota(db, saas_user.user_id)

        assert exc_info.value.status_code == 429

    def test_free_user_passes_below_quota(self, db, saas_user, saas_env):
        """Free user at 49 calls (below limit=50) passes."""
        from services.tier_enforcement_service import TierEnforcementService
        from models.usage_record import UsageRecord

        usage = UsageRecord(
            user_id=saas_user.user_id,
            billing_period_start=date.today().replace(day=1),
            call_count=49,
        )
        db.add(usage)
        db.flush()

        # Should not raise
        TierEnforcementService.check_system_llm_quota(db, saas_user.user_id)

    def test_pro_user_unlimited_quota_never_blocked(self, db, saas_env):
        """Pro user with limit=-1 is never blocked regardless of call count."""
        from models.user import User
        from models.subscription import Subscription, SubscriptionTier, BillingStatus
        from models.usage_record import UsageRecord
        from services.tier_enforcement_service import TierEnforcementService

        user = User(email="pro_user@test.com", name="Pro User", is_active=True)
        db.add(user)
        db.flush()

        sub = Subscription(
            user_id=user.user_id,
            tier=SubscriptionTier.PRO,
            billing_status=BillingStatus.ACTIVE,
        )
        db.add(sub)

        usage = UsageRecord(
            user_id=user.user_id,
            billing_period_start=date.today().replace(day=1),
            call_count=999999,
        )
        db.add(usage)
        db.flush()

        # Should not raise — limit is -1 (unlimited)
        TierEnforcementService.check_system_llm_quota(db, user.user_id)


# ---------------------------------------------------------------------------
# AI Service restriction for Free tier
# ---------------------------------------------------------------------------

class TestAiServiceRestriction:

    def test_free_user_cannot_create_ai_service(self, db, saas_user, saas_env):
        """Free tier users are blocked from creating custom AI Services."""
        from services.tier_enforcement_service import TierEnforcementService

        with pytest.raises(HTTPException) as exc_info:
            TierEnforcementService.check_ai_service_allowed(db, saas_user.user_id)

        assert exc_info.value.status_code == 403

    def test_starter_user_can_create_ai_service(self, db, saas_env):
        """Starter tier users can create custom AI Services."""
        from models.user import User
        from models.subscription import Subscription, SubscriptionTier, BillingStatus
        from services.tier_enforcement_service import TierEnforcementService

        user = User(email="starter@test.com", name="Starter User", is_active=True)
        db.add(user)
        db.flush()

        sub = Subscription(
            user_id=user.user_id,
            tier=SubscriptionTier.STARTER,
            billing_status=BillingStatus.ACTIVE,
        )
        db.add(sub)
        db.flush()

        # Should not raise
        TierEnforcementService.check_ai_service_allowed(db, user.user_id)


# ---------------------------------------------------------------------------
# Self-managed mode: all checks are no-ops
# ---------------------------------------------------------------------------

class TestSelfManagedNoOps:

    def test_check_app_limit_is_noop_in_self_managed(self, db, saas_user):
        """In self-managed mode, no limits are enforced regardless of state."""
        # Do not use saas_env fixture — we want default self_managed mode
        import importlib, deployment_mode as dm
        dm_mode = os.getenv("AICT_DEPLOYMENT_MODE", "self_managed")
        # Ensure it's self_managed
        os.environ["AICT_DEPLOYMENT_MODE"] = "self_managed"
        importlib.reload(dm)
        import services.tier_enforcement_service as tes
        importlib.reload(tes)

        try:
            from models.app import App
            # Create many apps — beyond any limit
            for i in range(10):
                app = App(
                    name=f"SM App {i}",
                    slug=f"sm-app-{i}-{saas_user.user_id}",
                    owner_id=saas_user.user_id,
                    agent_rate_limit=0,
                    max_file_size_mb=10,
                )
                db.add(app)
            db.flush()

            # Must not raise
            tes.TierEnforcementService.check_app_limit(db, saas_user.user_id)
        finally:
            os.environ["AICT_DEPLOYMENT_MODE"] = dm_mode
            importlib.reload(dm)
            importlib.reload(tes)
