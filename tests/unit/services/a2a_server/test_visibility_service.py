"""Unit coverage for `services.a2a_server.visibility_service` (step_011, FR-4/FR-9/FR-10, NFR-1/NFR-2).

No DB: `get_agent_for_app`/`list_enabled_agents_for_app`/`AppSlugRepository.get_by_slug`/
`PublicAuthService.find_valid_key_for_app` are all monkeypatched. `db` is a bare
`MagicMock`; `resolve`/`list_visible` never call it directly (every DB access
goes through the monkeypatched repository functions).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services.a2a_server import visibility_service as vis
from services.a2a_server.visibility_service import Outcome, Reason


def _config(*, enabled=True, root_agent=None):
    return SimpleNamespace(enabled=enabled, root_agent=root_agent)


def _app(*, app_id=1, slug="acme", is_frozen=False, max_file_size_mb=0, name="Acme", owner=None):
    return SimpleNamespace(
        app_id=app_id, slug=slug, is_frozen=is_frozen, max_file_size_mb=max_file_size_mb, name=name, owner=owner
    )


def _agent(
    *,
    agent_id=9,
    app_id=1,
    app=None,
    a2a_enabled=True,
    is_frozen=False,
    visibility="public",
    name="Support Bot",
    description="desc",
):
    return SimpleNamespace(
        agent_id=agent_id,
        app_id=app_id,
        app=app or _app(app_id=app_id),
        a2a_enabled=a2a_enabled,
        is_frozen=is_frozen,
        a2a_card_visibility=visibility,
        name=name,
        description=description,
        a2a_name_override=None,
        a2a_description_override=None,
        a2a_skill_tags=[],
        a2a_examples=[],
        skill_associations=[],
        server_tools=[],
        enable_code_interpreter=False,
        output_parser_id=None,
        ai_service=None,
        has_memory=False,
    )


@pytest.fixture(autouse=True)
def _patch_config(monkeypatch):
    monkeypatch.setattr(vis, "get_a2a_config", lambda: _config())


class TestResolve:
    def test_global_disabled_is_not_found(self, monkeypatch):
        monkeypatch.setattr(vis, "get_a2a_config", lambda: _config(enabled=False))
        result = vis.resolve(MagicMock(), "acme", 9)
        assert result.outcome is Outcome.NOT_FOUND
        assert result.reason is Reason.DISABLED_GLOBAL

    def test_app_missing_is_not_found(self, monkeypatch):
        monkeypatch.setattr(vis.AppSlugRepository, "get_by_slug", staticmethod(lambda db, slug: None))
        result = vis.resolve(MagicMock(), "ghost", 9)
        assert result.outcome is Outcome.NOT_FOUND
        assert result.reason is Reason.APP_MISSING

    def test_agent_missing_everywhere_is_not_found(self, monkeypatch):
        monkeypatch.setattr(vis.AppSlugRepository, "get_by_slug", staticmethod(lambda db, slug: _app()))
        monkeypatch.setattr(vis, "get_agent_for_app", lambda db, app_id, agent_id: None)
        result = vis.resolve(MagicMock(), "acme", 404)
        assert result.outcome is Outcome.NOT_FOUND
        assert result.reason is Reason.AGENT_MISSING

    def test_agent_belongs_to_another_app_is_not_found_with_the_same_reason(self, monkeypatch):
        # get_agent_for_app is already scoped to app_id (repository-level filter), so an
        # agent that exists but belongs to another app looks identical to a nonexistent
        # one here: both return None, and both get Reason.AGENT_MISSING (review round 2,
        # LOW-5 -- no extra query to distinguish them for the log).
        monkeypatch.setattr(vis.AppSlugRepository, "get_by_slug", staticmethod(lambda db, slug: _app()))
        monkeypatch.setattr(vis, "get_agent_for_app", lambda db, app_id, agent_id: None)
        result = vis.resolve(MagicMock(), "acme", 9)
        assert result.outcome is Outcome.NOT_FOUND
        assert result.reason is Reason.AGENT_MISSING

    def test_key_lookup_runs_even_when_the_agent_is_missing(self, monkeypatch):
        # LOW-5: the key lookup must not be skipped just because the agent doesn't
        # exist, so the cost of this path doesn't depend on agent_id's validity.
        monkeypatch.setattr(vis.AppSlugRepository, "get_by_slug", staticmethod(lambda db, slug: _app()))
        monkeypatch.setattr(vis, "get_agent_for_app", lambda db, app_id, agent_id: None)
        calls = []
        monkeypatch.setattr(
            vis._auth_service,
            "find_valid_key_for_app",
            lambda db, app_id, raw: calls.append((app_id, raw)) or None,
        )
        vis.resolve(MagicMock(), "acme", 404, raw_api_key="some-key")
        assert calls == [(1, "some-key")]

    def test_owner_deactivated_is_not_found(self, monkeypatch):
        monkeypatch.setattr(
            vis.AppSlugRepository, "get_by_slug", staticmethod(lambda db, slug: _app(owner=SimpleNamespace(is_active=False)))
        )
        result = vis.resolve(MagicMock(), "acme", 9)
        assert result.outcome is Outcome.NOT_FOUND
        assert result.reason is Reason.OWNER_DEACTIVATED

    def test_a2a_disabled_on_agent_is_not_found(self, monkeypatch):
        monkeypatch.setattr(vis.AppSlugRepository, "get_by_slug", staticmethod(lambda db, slug: _app()))
        monkeypatch.setattr(vis, "get_agent_for_app", lambda db, app_id, agent_id: _agent(a2a_enabled=False))
        result = vis.resolve(MagicMock(), "acme", 9)
        assert result.outcome is Outcome.NOT_FOUND
        assert result.reason is Reason.DISABLED_AGENT

    def test_frozen_agent_is_not_found(self, monkeypatch):
        monkeypatch.setattr(vis.AppSlugRepository, "get_by_slug", staticmethod(lambda db, slug: _app()))
        monkeypatch.setattr(vis, "get_agent_for_app", lambda db, app_id, agent_id: _agent(is_frozen=True))
        result = vis.resolve(MagicMock(), "acme", 9)
        assert result.outcome is Outcome.NOT_FOUND
        assert result.reason is Reason.FROZEN_AGENT

    def test_frozen_app_is_not_found(self, monkeypatch):
        monkeypatch.setattr(vis.AppSlugRepository, "get_by_slug", staticmethod(lambda db, slug: _app(is_frozen=True)))
        monkeypatch.setattr(vis, "get_agent_for_app", lambda db, app_id, agent_id: _agent(app=_app(is_frozen=True)))
        result = vis.resolve(MagicMock(), "acme", 9)
        assert result.outcome is Outcome.NOT_FOUND
        assert result.reason is Reason.FROZEN_APP

    def test_api_key_visibility_without_key_is_not_found(self, monkeypatch):
        monkeypatch.setattr(vis.AppSlugRepository, "get_by_slug", staticmethod(lambda db, slug: _app()))
        monkeypatch.setattr(vis, "get_agent_for_app", lambda db, app_id, agent_id: _agent(visibility="api_key"))
        result = vis.resolve(MagicMock(), "acme", 9, raw_api_key=None)
        assert result.outcome is Outcome.NOT_FOUND
        assert result.reason is Reason.KEY_REQUIRED

    def test_api_key_visibility_with_valid_key_is_visible(self, monkeypatch):
        monkeypatch.setattr(vis.AppSlugRepository, "get_by_slug", staticmethod(lambda db, slug: _app()))
        monkeypatch.setattr(vis, "get_agent_for_app", lambda db, app_id, agent_id: _agent(visibility="api_key"))
        monkeypatch.setattr(
            vis._auth_service,
            "find_valid_key_for_app",
            lambda db, app_id, raw: SimpleNamespace(key_id=42),
        )
        result = vis.resolve(MagicMock(), "acme", 9, raw_api_key="raw-key")
        assert result.outcome is Outcome.VISIBLE
        assert result.key is not None
        assert result.key.key_id == 42
        assert result.key.raw.get_secret_value() == "raw-key"

    def test_key_of_another_app_counts_as_no_key(self, monkeypatch):
        monkeypatch.setattr(vis.AppSlugRepository, "get_by_slug", staticmethod(lambda db, slug: _app()))
        monkeypatch.setattr(vis, "get_agent_for_app", lambda db, app_id, agent_id: _agent(visibility="api_key"))
        monkeypatch.setattr(
            vis._auth_service, "find_valid_key_for_app", lambda db, app_id, raw: None
        )
        result = vis.resolve(MagicMock(), "acme", 9, raw_api_key="other-apps-key")
        assert result.outcome is Outcome.NOT_FOUND
        assert result.reason is Reason.KEY_REQUIRED

    def test_fail_closed_on_unexpected_visibility_value(self, monkeypatch):
        # LOW-3: anything other than the exact string "public" must require a key,
        # not just the literal "api_key" value -- simulates unexpected/legacy data.
        monkeypatch.setattr(vis.AppSlugRepository, "get_by_slug", staticmethod(lambda db, slug: _app()))
        monkeypatch.setattr(
            vis, "get_agent_for_app", lambda db, app_id, agent_id: _agent(visibility="something-else")
        )
        result = vis.resolve(MagicMock(), "acme", 9, raw_api_key=None)
        assert result.outcome is Outcome.NOT_FOUND
        assert result.reason is Reason.KEY_REQUIRED

    def test_public_agent_is_visible_without_a_key(self, monkeypatch):
        monkeypatch.setattr(vis.AppSlugRepository, "get_by_slug", staticmethod(lambda db, slug: _app()))
        monkeypatch.setattr(vis, "get_agent_for_app", lambda db, app_id, agent_id: _agent(visibility="public"))
        result = vis.resolve(MagicMock(), "acme", 9, raw_api_key=None)
        assert result.outcome is Outcome.VISIBLE
        assert result.key is None
        assert result.snapshot is not None
        assert result.snapshot.agent_id == 9


class TestListVisible:
    def test_global_disabled_yields_empty_list(self, monkeypatch):
        monkeypatch.setattr(vis, "get_a2a_config", lambda: _config(enabled=False))
        assert vis.list_visible(MagicMock(), "acme") == []

    def test_app_missing_yields_empty_list(self, monkeypatch):
        monkeypatch.setattr(vis.AppSlugRepository, "get_by_slug", staticmethod(lambda db, slug: None))
        assert vis.list_visible(MagicMock(), "ghost") == []

    def test_frozen_app_yields_empty_list(self, monkeypatch):
        monkeypatch.setattr(vis.AppSlugRepository, "get_by_slug", staticmethod(lambda db, slug: _app(is_frozen=True)))
        assert vis.list_visible(MagicMock(), "acme") == []

    def test_owner_deactivated_yields_empty_list(self, monkeypatch):
        monkeypatch.setattr(
            vis.AppSlugRepository, "get_by_slug", staticmethod(lambda db, slug: _app(owner=SimpleNamespace(is_active=False)))
        )
        assert vis.list_visible(MagicMock(), "acme") == []

    def test_ordering_and_filtering(self, monkeypatch):
        app = _app()
        agents = [
            _agent(agent_id=1, app=app, visibility="public"),
            _agent(agent_id=2, app=app, visibility="api_key"),
        ]
        monkeypatch.setattr(vis.AppSlugRepository, "get_by_slug", staticmethod(lambda db, slug: app))
        monkeypatch.setattr(vis, "list_enabled_agents_for_app", lambda db, app_id: agents)
        monkeypatch.setattr(vis._auth_service, "find_valid_key_for_app", lambda db, app_id, raw: None)

        result = vis.list_visible(MagicMock(), "acme", raw_api_key=None)
        assert [s.agent_id for s in result] == [1]

        monkeypatch.setattr(
            vis._auth_service, "find_valid_key_for_app", lambda db, app_id, raw: SimpleNamespace(key_id=1)
        )
        result_with_key = vis.list_visible(MagicMock(), "acme", raw_api_key="valid")
        assert [s.agent_id for s in result_with_key] == [1, 2]


class TestResolveRoot:
    def test_no_root_agent_configured_is_not_found(self, monkeypatch):
        monkeypatch.setattr(vis, "get_a2a_config", lambda: _config(root_agent=None))
        result = vis.resolve_root(MagicMock())
        assert result.outcome is Outcome.NOT_FOUND

    def test_malformed_root_agent_is_not_found(self, monkeypatch):
        monkeypatch.setattr(vis, "get_a2a_config", lambda: _config(root_agent="acme/not-a-number"))
        result = vis.resolve_root(MagicMock())
        assert result.outcome is Outcome.NOT_FOUND

    def test_root_agent_must_be_public_visibility(self, monkeypatch):
        monkeypatch.setattr(vis, "get_a2a_config", lambda: _config(root_agent="acme/9"))
        monkeypatch.setattr(vis.AppSlugRepository, "get_by_slug", staticmethod(lambda db, slug: _app()))
        monkeypatch.setattr(vis, "get_agent_for_app", lambda db, app_id, agent_id: _agent(visibility="api_key"))
        result = vis.resolve_root(MagicMock())
        assert result.outcome is Outcome.NOT_FOUND

    def test_public_root_agent_is_visible(self, monkeypatch):
        monkeypatch.setattr(vis, "get_a2a_config", lambda: _config(root_agent="acme/9"))
        monkeypatch.setattr(vis.AppSlugRepository, "get_by_slug", staticmethod(lambda db, slug: _app()))
        monkeypatch.setattr(vis, "get_agent_for_app", lambda db, app_id, agent_id: _agent(visibility="public"))
        result = vis.resolve_root(MagicMock())
        assert result.outcome is Outcome.VISIBLE
        assert result.snapshot.agent_id == 9
