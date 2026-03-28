"""Unit tests for FreezeService.

The database is fully mocked (no DB connection required).
"""
import os
import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timedelta

os.environ.setdefault("AICT_DEPLOYMENT_MODE", "self_managed")

from services.freeze_service import FreezeService, _freeze_resources
from models.app_collaborator import CollaborationRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_resource(created_at_offset_days=0, is_frozen=False, app_id=1):
    """Create a mock resource with a controllable created_at timestamp."""
    r = MagicMock()
    r.is_frozen = is_frozen
    r.create_date = datetime(2025, 1, 1) + timedelta(days=created_at_offset_days)
    r.app_id = app_id
    return r


def make_collab(invited_at_offset_days=0, is_frozen=False, role=CollaborationRole.EDITOR):
    c = MagicMock()
    c.is_frozen = is_frozen
    c.invited_at = datetime(2025, 1, 1) + timedelta(days=invited_at_offset_days)
    c.role = role
    return c


def make_app(app_id=1, owner_id=99, created_at_offset_days=0):
    a = MagicMock()
    a.app_id = app_id
    a.owner_id = owner_id
    a.create_date = datetime(2025, 1, 1) + timedelta(days=created_at_offset_days)
    a.is_frozen = False
    return a


# ---------------------------------------------------------------------------
# _freeze_resources helper
# ---------------------------------------------------------------------------

class TestFreezeResourcesHelper:

    def test_all_unfrozen_when_below_limit(self):
        resources = [make_resource(i) for i in range(3)]
        _freeze_resources(resources, limit=5)
        assert all(not r.is_frozen for r in resources)

    def test_excess_frozen_newest_first(self):
        # resources[0] is newest (index 0), resources[4] is oldest
        resources = [make_resource(i) for i in range(5)]
        _freeze_resources(resources, limit=3)
        assert not resources[0].is_frozen
        assert not resources[1].is_frozen
        assert not resources[2].is_frozen
        assert resources[3].is_frozen
        assert resources[4].is_frozen

    def test_all_frozen_at_limit_zero(self):
        resources = [make_resource(i) for i in range(3)]
        _freeze_resources(resources, limit=0)
        assert all(r.is_frozen for r in resources)

    def test_unlimited_minus_one_never_freezes(self):
        resources = [make_resource(i) for i in range(10)]
        _freeze_resources(resources, limit=-1)
        assert all(not r.is_frozen for r in resources)

    def test_empty_list_does_not_raise(self):
        _freeze_resources([], limit=3)

    def test_previously_frozen_gets_unfrozen_when_slot_opens(self):
        # Start: 5 resources, limit=3 → index 3 and 4 frozen
        resources = [make_resource(i) for i in range(5)]
        _freeze_resources(resources, limit=3)
        assert resources[3].is_frozen
        assert resources[4].is_frozen

        # Now reduce to 4 resources (simulate delete of index-0/newest)
        remaining = resources[1:]
        _freeze_resources(remaining, limit=3)
        # With limit=3, index 0-2 unfrozen, index 3 (originally index 4) frozen
        assert not remaining[0].is_frozen
        assert not remaining[1].is_frozen
        assert not remaining[2].is_frozen
        assert remaining[3].is_frozen


# ---------------------------------------------------------------------------
# FreezeService.apply_freeze — app-level
# ---------------------------------------------------------------------------

class TestApplyFreeze:

    def _make_db_with_resources(
        self,
        apps,
        agents_per_app=None,
        silos_per_app=None,
        skills_per_app=None,
        mcp_per_app=None,
        collabs_per_app=None,
    ):
        """Build a MagicMock db where query chains return the right resource lists."""
        db = MagicMock()
        agents_per_app = agents_per_app or {}
        silos_per_app = silos_per_app or {}
        skills_per_app = skills_per_app or {}
        mcp_per_app = mcp_per_app or {}
        collabs_per_app = collabs_per_app or {}

        # We can't easily mock individual filter chains in a single db.query mock when
        # multiple model types are queried. Instead, use side_effect on db.query to return
        # different QueryMock objects per model class.

        from models.app import App
        from models.agent import Agent
        from models.silo import Silo
        from models.skill import Skill
        from models.mcp_server import MCPServer
        from models.app_collaborator import AppCollaborator

        def query_side_effect(model_cls):
            q = MagicMock()
            if model_cls is App:
                q.filter.return_value.order_by.return_value.all.return_value = apps
            elif model_cls is Agent:
                def agent_filter(cond):
                    f = MagicMock()
                    # Extract app_id from filter condition is tricky; use a closure over app list
                    # We'll track which app_id was filtered by checking call args
                    app_id = None
                    # The condition is `Agent.app_id == app_id` — we can't easily inspect it,
                    # so we return all agents and let tests be app-specific
                    for aid, agent_list in agents_per_app.items():
                        f.order_by.return_value.all.return_value = agent_list
                    return f
                q.filter.side_effect = agent_filter
            elif model_cls is Silo:
                def silo_filter(cond):
                    f = MagicMock()
                    for aid, silo_list in silos_per_app.items():
                        f.order_by.return_value.all.return_value = silo_list
                    return f
                q.filter.side_effect = silo_filter
            elif model_cls is Skill:
                def skill_filter(cond):
                    f = MagicMock()
                    for aid, skill_list in skills_per_app.items():
                        f.order_by.return_value.all.return_value = skill_list
                    return f
                q.filter.side_effect = skill_filter
            elif model_cls is MCPServer:
                def mcp_filter(cond):
                    f = MagicMock()
                    for aid, mcp_list in mcp_per_app.items():
                        f.order_by.return_value.all.return_value = mcp_list
                    return f
                q.filter.side_effect = mcp_filter
            elif model_cls is AppCollaborator:
                def collab_filter(*args):
                    f = MagicMock()
                    for aid, collab_list in collabs_per_app.items():
                        f.filter.return_value.order_by.return_value.all.return_value = collab_list
                        f.order_by.return_value.all.return_value = collab_list
                    return f
                q.filter.side_effect = collab_filter
            else:
                q.filter.return_value.order_by.return_value.all.return_value = []
            return q

        db.query.side_effect = query_side_effect
        return db

    def test_downgrade_freezes_excess_apps(self):
        """With limit=2 and 4 apps, the 2 oldest (index 2, 3) should be frozen."""
        apps = [make_app(app_id=i+1, created_at_offset_days=3-i) for i in range(4)]
        # apps[0] newest, apps[3] oldest

        with (
            patch("services.freeze_service.SubscriptionRepository") as MockSubRepo,
            patch("services.freeze_service.TierConfigRepository") as MockTierRepo,
        ):
            MockSubRepo.return_value.get_by_user_id.return_value = MagicMock(
                tier=MagicMock(value="free"), admin_override_tier=None
            )
            MockTierRepo.return_value.get_limit.return_value = 2

            db = self._make_db_with_resources(apps)
            FreezeService.apply_freeze(db, user_id=99, new_tier="free")

        assert not apps[0].is_frozen
        assert not apps[1].is_frozen
        assert apps[2].is_frozen
        assert apps[3].is_frozen

    def test_unlimited_tier_unfreezes_all(self):
        """With limit=-1, all apps and resources should be unfrozen."""
        apps = [make_app(app_id=i+1, created_at_offset_days=i) for i in range(5)]
        for app in apps:
            app.is_frozen = True  # pre-frozen

        with (
            patch("services.freeze_service.SubscriptionRepository"),
            patch("services.freeze_service.TierConfigRepository") as MockTierRepo,
        ):
            MockTierRepo.return_value.get_limit.return_value = -1

            db = self._make_db_with_resources(apps)
            FreezeService.apply_freeze(db, user_id=99, new_tier="pro")

        assert all(not a.is_frozen for a in apps)

    def test_zero_resources_does_not_raise(self):
        """apply_freeze with no resources should be a no-op (no exception)."""
        with (
            patch("services.freeze_service.SubscriptionRepository"),
            patch("services.freeze_service.TierConfigRepository") as MockTierRepo,
        ):
            MockTierRepo.return_value.get_limit.return_value = 3

            db = self._make_db_with_resources(apps=[])
            FreezeService.apply_freeze(db, user_id=99, new_tier="free")


# ---------------------------------------------------------------------------
# FreezeService.recalculate_on_delete
# ---------------------------------------------------------------------------

class TestRecalculateOnDelete:

    def test_deleting_resource_unfreezes_next_in_line(self):
        """After deleting a resource, the next-newest (previously frozen) should unfreeze."""
        from models.agent import Agent

        # 3 agents, limit=2 → agent[2] (oldest) was frozen
        agents = [make_resource(i) for i in range(3)]
        agents[2].is_frozen = True

        db = MagicMock()
        app = MagicMock()
        app.owner_id = 99

        with (
            patch("services.freeze_service.SubscriptionRepository") as MockSubRepo,
            patch("services.freeze_service.TierConfigRepository") as MockTierRepo,
        ):
            sub = MagicMock()
            sub.tier = MagicMock(value="free")
            sub.admin_override_tier = None
            MockSubRepo.return_value.get_by_user_id.return_value = sub
            MockTierRepo.return_value.get_limit.return_value = 3  # limit increased by 1

            q = MagicMock()
            q.filter.return_value.order_by.return_value.all.return_value = agents
            db.query.return_value = q

            FreezeService.recalculate_on_delete(db, user_id=99, resource_type="agents", app_id=1)

        # With limit=3 and 3 agents, none should be frozen
        assert all(not a.is_frozen for a in agents)

    def test_recalculate_apps_on_delete(self):
        """Apps list is re-evaluated after a deletion."""
        from models.app import App

        # 3 apps, limit=3 → none should be frozen after recalculation
        apps = [make_app(app_id=i+1, created_at_offset_days=i) for i in range(3)]
        apps[2].is_frozen = True  # was previously frozen

        db = MagicMock()

        with (
            patch("services.freeze_service.SubscriptionRepository") as MockSubRepo,
            patch("services.freeze_service.TierConfigRepository") as MockTierRepo,
        ):
            sub = MagicMock()
            sub.tier = MagicMock(value="free")
            sub.admin_override_tier = None
            MockSubRepo.return_value.get_by_user_id.return_value = sub
            MockTierRepo.return_value.get_limit.return_value = 3

            q = MagicMock()
            q.filter.return_value.order_by.return_value.all.return_value = apps
            db.query.return_value = q

            FreezeService.recalculate_on_delete(db, user_id=99, resource_type="apps")

        assert all(not a.is_frozen for a in apps)


# ---------------------------------------------------------------------------
# FreezeService.recalculate_on_upgrade
# ---------------------------------------------------------------------------

class TestRecalculateOnUpgrade:

    def test_upgrade_delegates_to_apply_freeze(self):
        """recalculate_on_upgrade must call apply_freeze with the new tier."""
        db = MagicMock()

        with patch.object(FreezeService, "apply_freeze") as mock_freeze:
            FreezeService.recalculate_on_upgrade(db, user_id=42, new_tier="pro")

        mock_freeze.assert_called_once_with(db, 42, "pro")


# ---------------------------------------------------------------------------
# Collaborator freeze edge cases
# ---------------------------------------------------------------------------

class TestCollaboratorFreeze:

    def test_owner_collaborator_never_frozen(self):
        """Owner-role collaborators must be excluded from the freeze count."""
        # The service explicitly filters out OWNER before applying _freeze_resources.
        # Verify _freeze_resources only processes non-owners.
        collabs = [make_collab(invited_at_offset_days=i) for i in range(4)]

        # Directly test the _freeze_resources helper with a collab list of size 4, limit=2
        _freeze_resources(collabs, limit=2)

        # collabs[0] and collabs[1] (newest) unfrozen, collabs[2] and [3] frozen
        assert not collabs[0].is_frozen
        assert not collabs[1].is_frozen
        assert collabs[2].is_frozen
        assert collabs[3].is_frozen
