"""Unit tests for TierEnforcementService.

The database is fully mocked (no DB connection required).
"""
import os
import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

os.environ.setdefault("AICT_DEPLOYMENT_MODE", "self_managed")

from services.tier_enforcement_service import TierEnforcementService
from models.subscription import SubscriptionTier, BillingStatus


# ---------------------------------------------------------------------------
# Shared fixture: patch is_self_managed → False so enforcement paths are entered
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_saas_mode():
    """Patch is_self_managed() to return False for most tests.
    Tests that verify the self-managed no-op behavior override this fixture
    by calling monkeypatch.setenv and reloading the module themselves.
    """
    with patch("services.tier_enforcement_service.is_self_managed", return_value=False):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TIER_MAP = {
    "free": SubscriptionTier.FREE,
    "starter": SubscriptionTier.STARTER,
    "pro": SubscriptionTier.PRO,
}


def make_sub(tier=SubscriptionTier.FREE, admin_override_tier=None):
    sub = MagicMock()
    sub.tier = tier  # real enum so .value works
    sub.admin_override_tier = admin_override_tier
    return sub


def make_app(app_id=1, owner_id=99):
    app = MagicMock()
    app.app_id = app_id
    app.owner_id = owner_id
    return app


def _patch_tier(db, tier_str="free", limit_value=3):
    """Set up db mock so that:
      - SubscriptionRepository.get_by_user_id returns a sub with the given tier
      - TierConfigRepository.get_limit returns limit_value
    """
    return tier_str, limit_value


# ---------------------------------------------------------------------------
# check_app_limit
# ---------------------------------------------------------------------------

class TestCheckAppLimit:

    def _run(self, db, tier_str, limit, current_count):
        with (
            patch("services.tier_enforcement_service.SubscriptionRepository") as MockSubRepo,
            patch("services.tier_enforcement_service.TierConfigRepository") as MockTierRepo,
        ):
            sub = make_sub(tier=_TIER_MAP[tier_str])
            MockSubRepo.return_value.get_by_user_id.return_value = sub
            MockTierRepo.return_value.get_limit.return_value = limit
            db.query.return_value.filter.return_value.scalar.return_value = current_count

            TierEnforcementService.check_app_limit(db, user_id=99)

    def test_below_limit_passes(self):
        db = MagicMock()
        # Should not raise
        self._run(db, "free", limit=3, current_count=2)

    def test_at_limit_raises_403(self):
        db = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            self._run(db, "free", limit=3, current_count=3)
        assert exc_info.value.status_code == 403

    def test_unlimited_minus_one_always_passes(self):
        db = MagicMock()
        # limit=-1 means unlimited
        self._run(db, "pro", limit=-1, current_count=9999)

    def test_self_managed_is_noop(self, monkeypatch):
        monkeypatch.setenv("AICT_DEPLOYMENT_MODE", "self_managed")
        import importlib, services.tier_enforcement_service as m
        importlib.reload(m)

        db = MagicMock()
        # Must not raise regardless of state
        m.TierEnforcementService.check_app_limit(db, user_id=99)

        monkeypatch.setenv("AICT_DEPLOYMENT_MODE", "saas")
        importlib.reload(m)


# ---------------------------------------------------------------------------
# check_resource_limit — per resource type
# ---------------------------------------------------------------------------

class TestCheckResourceLimit:

    def _run(self, db, resource_type, limit, current_count, tier_str="free"):
        app = make_app()
        with (
            patch("services.tier_enforcement_service.SubscriptionRepository") as MockSubRepo,
            patch("services.tier_enforcement_service.TierConfigRepository") as MockTierRepo,
        ):
            sub = make_sub(tier=_TIER_MAP[tier_str])
            MockSubRepo.return_value.get_by_user_id.return_value = sub
            MockTierRepo.return_value.get_limit.return_value = limit
            db.query.return_value.filter.return_value.first.return_value = app
            db.query.return_value.filter.return_value.scalar.return_value = current_count

            TierEnforcementService.check_resource_limit(db, app_id=1, resource_type=resource_type)

    @pytest.mark.parametrize("resource_type", ["agents", "silos", "skills", "mcp_servers", "collaborators"])
    def test_below_limit_passes(self, resource_type):
        db = MagicMock()
        self._run(db, resource_type, limit=5, current_count=4)

    @pytest.mark.parametrize("resource_type", ["agents", "silos", "skills", "mcp_servers", "collaborators"])
    def test_at_limit_raises_403(self, resource_type):
        db = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            self._run(db, resource_type, limit=5, current_count=5)
        assert exc_info.value.status_code == 403

    def test_unlimited_minus_one_passes(self):
        db = MagicMock()
        self._run(db, "agents", limit=-1, current_count=9999)

    def test_unknown_resource_type_is_ignored(self):
        """Unrecognised resource types should not raise."""
        db = MagicMock()
        app = make_app()
        with (
            patch("services.tier_enforcement_service.SubscriptionRepository") as MockSubRepo,
            patch("services.tier_enforcement_service.TierConfigRepository") as MockTierRepo,
        ):
            MockSubRepo.return_value.get_by_user_id.return_value = make_sub()
            MockTierRepo.return_value.get_limit.return_value = 5
            db.query.return_value.filter.return_value.first.return_value = app
            TierEnforcementService.check_resource_limit(db, app_id=1, resource_type="bananas")

    def test_nonexistent_app_is_ignored(self):
        """If the app is not found, no exception should be raised."""
        db = MagicMock()
        with patch("services.tier_enforcement_service.SubscriptionRepository"):
            db.query.return_value.filter.return_value.first.return_value = None
            TierEnforcementService.check_resource_limit(db, app_id=999, resource_type="agents")

    def test_self_managed_is_noop(self, monkeypatch):
        monkeypatch.setenv("AICT_DEPLOYMENT_MODE", "self_managed")
        import importlib, services.tier_enforcement_service as m
        importlib.reload(m)

        db = MagicMock()
        m.TierEnforcementService.check_resource_limit(db, app_id=1, resource_type="agents")

        monkeypatch.setenv("AICT_DEPLOYMENT_MODE", "saas")
        importlib.reload(m)


# ---------------------------------------------------------------------------
# check_system_llm_quota
# ---------------------------------------------------------------------------

class TestCheckSystemLlmQuota:

    def _run(self, db, limit, call_count, tier_str="free"):
        usage = MagicMock()
        usage.call_count = call_count

        with (
            patch("services.tier_enforcement_service.SubscriptionRepository") as MockSubRepo,
            patch("services.tier_enforcement_service.TierConfigRepository") as MockTierRepo,
            patch("services.tier_enforcement_service.UsageRecordRepository") as MockUsageRepo,
        ):
            sub = make_sub(tier=_TIER_MAP[tier_str])
            MockSubRepo.return_value.get_by_user_id.return_value = sub
            MockTierRepo.return_value.get_limit.return_value = limit
            MockUsageRepo.return_value.get_current.return_value = usage

            TierEnforcementService.check_system_llm_quota(db, user_id=99)

    def test_below_limit_passes(self):
        db = MagicMock()
        self._run(db, limit=100, call_count=50)

    def test_at_limit_raises_429(self):
        db = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            self._run(db, limit=100, call_count=100)
        assert exc_info.value.status_code == 429

    def test_over_limit_raises_429(self):
        db = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            self._run(db, limit=100, call_count=150)
        assert exc_info.value.status_code == 429

    def test_unlimited_minus_one_passes(self):
        db = MagicMock()
        self._run(db, limit=-1, call_count=99999)

    def test_no_usage_record_passes(self):
        """If no usage record exists yet, count is 0 and should never block."""
        db = MagicMock()
        with (
            patch("services.tier_enforcement_service.SubscriptionRepository") as MockSubRepo,
            patch("services.tier_enforcement_service.TierConfigRepository") as MockTierRepo,
            patch("services.tier_enforcement_service.UsageRecordRepository") as MockUsageRepo,
        ):
            sub = make_sub(tier=SubscriptionTier.FREE)
            MockSubRepo.return_value.get_by_user_id.return_value = sub
            MockTierRepo.return_value.get_limit.return_value = 100
            MockUsageRepo.return_value.get_current.return_value = None  # no record

            TierEnforcementService.check_system_llm_quota(db, user_id=99)

    def test_self_managed_is_noop(self, monkeypatch):
        monkeypatch.setenv("AICT_DEPLOYMENT_MODE", "self_managed")
        import importlib, services.tier_enforcement_service as m
        importlib.reload(m)

        db = MagicMock()
        m.TierEnforcementService.check_system_llm_quota(db, user_id=99)

        monkeypatch.setenv("AICT_DEPLOYMENT_MODE", "saas")
        importlib.reload(m)


# ---------------------------------------------------------------------------
# check_ai_service_allowed
# ---------------------------------------------------------------------------

class TestCheckAiServiceAllowed:

    def _run(self, db, tier_str):
        with patch("services.tier_enforcement_service.SubscriptionRepository") as MockSubRepo:
            sub = make_sub(tier=_TIER_MAP[tier_str])
            MockSubRepo.return_value.get_by_user_id.return_value = sub
            TierEnforcementService.check_ai_service_allowed(db, user_id=99)

    def test_free_tier_raises_403(self):
        db = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            self._run(db, "free")
        assert exc_info.value.status_code == 403

    def test_starter_tier_passes(self):
        db = MagicMock()
        self._run(db, "starter")

    def test_pro_tier_passes(self):
        db = MagicMock()
        self._run(db, "pro")

    def test_self_managed_is_noop(self, monkeypatch):
        monkeypatch.setenv("AICT_DEPLOYMENT_MODE", "self_managed")
        import importlib, services.tier_enforcement_service as m
        importlib.reload(m)

        db = MagicMock()
        m.TierEnforcementService.check_ai_service_allowed(db, user_id=99)

        monkeypatch.setenv("AICT_DEPLOYMENT_MODE", "saas")
        importlib.reload(m)

    def test_admin_override_to_starter_passes(self):
        """Admin override to a paid tier should bypass the Free restriction."""
        db = MagicMock()
        with patch("services.tier_enforcement_service.SubscriptionRepository") as MockSubRepo:
            sub = make_sub(tier=SubscriptionTier.FREE, admin_override_tier="starter")
            MockSubRepo.return_value.get_by_user_id.return_value = sub
            # Should not raise — effective tier is starter via override
            TierEnforcementService.check_ai_service_allowed(db, user_id=99)
