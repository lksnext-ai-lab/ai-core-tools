"""Integration coverage for `services.a2a_server.visibility_service.list_visible` (step_011, AC-5).

Uses the committed world fixture (`a2a_committed_world`, step_012) and a
fresh `SessionLocal()` (own session, same convention as the context-binding
integration tests), since `list_visible` runs real queries through
`repositories.a2a_agent_repository`.
"""

from __future__ import annotations

from db.database import SessionLocal
from services.a2a_server import visibility_service as vis


class TestListVisibleOrderingAndFiltering:
    def test_without_a_key_only_public_agents_are_visible_in_agent_id_order(self, a2a_committed_world):
        world = a2a_committed_world
        db = SessionLocal()
        try:
            result = vis.list_visible(db, world.app_slug, raw_api_key=None)
        finally:
            db.close()

        visible_ids = [s.agent_id for s in result]
        assert world.agent_public_id in visible_ids
        assert world.agent_api_key_id not in visible_ids
        assert world.agent_disabled_id not in visible_ids
        assert world.agent_frozen_id not in visible_ids
        assert world.other_agent_id not in visible_ids
        assert visible_ids == sorted(visible_ids)

    def test_with_a_valid_key_api_key_visibility_agents_are_included(self, a2a_committed_world):
        world = a2a_committed_world
        db = SessionLocal()
        try:
            result = vis.list_visible(db, world.app_slug, raw_api_key=world.key_1_raw)
        finally:
            db.close()

        visible_ids = [s.agent_id for s in result]
        assert world.agent_public_id in visible_ids
        assert world.agent_api_key_id in visible_ids
        assert world.agent_disabled_id not in visible_ids
        assert world.agent_frozen_id not in visible_ids
        assert visible_ids == sorted(visible_ids)

    def test_key_of_another_app_behaves_like_no_key(self, a2a_committed_world):
        world = a2a_committed_world
        db = SessionLocal()
        try:
            result = vis.list_visible(db, world.app_slug, raw_api_key=world.other_key_raw)
        finally:
            db.close()

        visible_ids = [s.agent_id for s in result]
        assert world.agent_api_key_id not in visible_ids
        assert world.agent_public_id in visible_ids

    def test_other_apps_agent_never_appears_in_this_apps_catalog(self, a2a_committed_world):
        world = a2a_committed_world
        db = SessionLocal()
        try:
            result = vis.list_visible(db, world.app_slug, raw_api_key=world.key_1_raw)
        finally:
            db.close()

        assert world.other_agent_id not in [s.agent_id for s in result]


class TestDeactivatedOwnerHidesEverything:
    """review round 2, LOW-6: a deactivated owner hides the whole app, both from
    `resolve` and from the catalog. Uses the rolled-back `db` fixture (not the
    committed world) since this needs no SDK store access."""

    def test_resolve_hides_an_otherwise_public_agent(self, db, fake_app, fake_user, fake_agent):
        fake_agent.a2a_enabled = True
        fake_agent.a2a_card_visibility = "public"
        fake_user.is_active = False
        db.flush()

        result = vis.resolve(db, fake_app.slug, fake_agent.agent_id)
        assert result.outcome is vis.Outcome.NOT_FOUND
        assert result.reason is vis.Reason.OWNER_DEACTIVATED

    def test_list_visible_yields_empty(self, db, fake_app, fake_user, fake_agent):
        fake_agent.a2a_enabled = True
        fake_agent.a2a_card_visibility = "public"
        fake_user.is_active = False
        db.flush()

        assert vis.list_visible(db, fake_app.slug) == []

    def test_active_owner_still_resolves(self, db, fake_app, fake_user, fake_agent):
        fake_agent.a2a_enabled = True
        fake_agent.a2a_card_visibility = "public"
        db.flush()

        result = vis.resolve(db, fake_app.slug, fake_agent.agent_id)
        assert result.outcome is vis.Outcome.VISIBLE
