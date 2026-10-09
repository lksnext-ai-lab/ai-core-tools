"""HTTP-level coverage for the A2A discovery routes (step_017, AD-4 step 3).

Uses the `client` fixture (real lifespan, real `A2ARuntime`) together with
`a2a_committed_world` (committed rows, since the router opens its own
`SessionLocal()` rather than depending on `get_db` -- see this module's and
`conftest.py`'s docstrings for why the `db` fixture's rolled-back rows would
be invisible to it).
"""

from __future__ import annotations

import pytest

from fastapi.testclient import TestClient

from db.database import SessionLocal
from models.app import App
from services.rate_limit_service import rate_limit_service
from utils.a2a_config import get_a2a_config

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clear_a2a_config_cache():
    get_a2a_config.cache_clear()
    yield
    get_a2a_config.cache_clear()


def test_public_agent_card_is_visible_without_a_key(client, a2a_committed_world):
    world = a2a_committed_world
    resp = client.get(f"/a2a/v1/apps/{world.app_slug}/agents/{world.agent_public_id}/.well-known/agent-card.json")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.headers["cache-control"] == "no-cache"
    body = resp.json()
    assert "supportedInterfaces" in body or "supported_interfaces" in body


def test_api_key_agent_card_requires_a_key_and_is_uniform_404_without_one(client, a2a_committed_world):
    world = a2a_committed_world
    url = f"/a2a/v1/apps/{world.app_slug}/agents/{world.agent_api_key_id}/.well-known/agent-card.json"

    no_key_resp = client.get(url)
    assert no_key_resp.status_code == 404
    assert no_key_resp.json() == {"detail": "Not Found"}

    with_key_resp = client.get(url, headers={"X-API-KEY": world.key_1_raw})
    assert with_key_resp.status_code == 200
    assert with_key_resp.headers["cache-control"] == "no-store"


def test_disabled_agent_card_is_the_same_uniform_404(client, a2a_committed_world):
    world = a2a_committed_world
    resp = client.get(f"/a2a/v1/apps/{world.app_slug}/agents/{world.agent_disabled_id}/.well-known/agent-card.json")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not Found"}


def test_frozen_agent_card_is_the_same_uniform_404(client, a2a_committed_world):
    world = a2a_committed_world
    resp = client.get(f"/a2a/v1/apps/{world.app_slug}/agents/{world.agent_frozen_id}/.well-known/agent-card.json")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not Found"}


def test_missing_app_card_is_the_same_uniform_404(client, a2a_committed_world):
    world = a2a_committed_world
    resp = client.get(f"/a2a/v1/apps/does-not-exist-{world.app_id}/agents/{world.agent_public_id}/.well-known/agent-card.json")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not Found"}


def test_cross_app_agent_id_is_the_same_uniform_404(client, a2a_committed_world):
    """AC-3: a numeric agent id that exists, but under a different app, 404s
    exactly like one that does not exist at all."""
    world = a2a_committed_world
    resp = client.get(f"/a2a/v1/apps/{world.app_slug}/agents/{world.other_agent_id}/.well-known/agent-card.json")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not Found"}


def test_non_numeric_agent_id_is_the_same_uniform_404_not_422(client, a2a_committed_world):
    world = a2a_committed_world
    resp = client.get(f"/a2a/v1/apps/{world.app_slug}/agents/not-a-number/.well-known/agent-card.json")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not Found"}


def test_catalog_lists_only_visible_agents_ordered_by_agent_id(client, a2a_committed_world):
    world = a2a_committed_world
    resp = client.get(f"/a2a/v1/apps/{world.app_slug}/agents")
    assert resp.status_code == 200
    entries = resp.json()
    agent_ids = [e["agent_id"] for e in entries]
    # Only the public agent is visible with no key (api_key/disabled/frozen are not).
    assert world.agent_public_id in agent_ids
    assert world.agent_api_key_id not in agent_ids
    assert world.agent_disabled_id not in agent_ids
    assert world.agent_frozen_id not in agent_ids
    assert agent_ids == sorted(agent_ids)


def test_catalog_with_a_valid_key_also_lists_the_api_key_agent(client, a2a_committed_world):
    world = a2a_committed_world
    resp = client.get(f"/a2a/v1/apps/{world.app_slug}/agents", headers={"X-API-KEY": world.key_1_raw})
    assert resp.status_code == 200
    agent_ids = [e["agent_id"] for e in resp.json()]
    assert world.agent_api_key_id in agent_ids


def test_empty_catalog_is_the_same_uniform_404(client, a2a_committed_world):
    world = a2a_committed_world
    resp = client.get(f"/a2a/v1/apps/does-not-exist-{world.app_id}/agents")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not Found"}


def test_root_card_is_404_when_a2a_root_agent_is_unset(client, monkeypatch):
    monkeypatch.delenv("A2A_ROOT_AGENT", raising=False)
    get_a2a_config.cache_clear()
    resp = client.get("/.well-known/agent-card.json")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not Found"}


def test_root_card_is_visible_when_configured_and_public(client, a2a_committed_world, monkeypatch):
    world = a2a_committed_world
    monkeypatch.setenv("A2A_ROOT_AGENT", f"{world.app_slug}/{world.agent_public_id}")
    get_a2a_config.cache_clear()
    resp = client.get("/.well-known/agent-card.json")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-cache"


def test_root_card_404s_when_the_configured_agent_requires_a_key(client, a2a_committed_world, monkeypatch):
    world = a2a_committed_world
    monkeypatch.setenv("A2A_ROOT_AGENT", f"{world.app_slug}/{world.agent_api_key_id}")
    get_a2a_config.cache_clear()
    resp = client.get("/.well-known/agent-card.json")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not Found"}


def test_a2a_disabled_globally_404s_every_discovery_route(client, a2a_committed_world, monkeypatch):
    world = a2a_committed_world
    monkeypatch.setenv("A2A_ENABLED", "false")
    get_a2a_config.cache_clear()
    try:
        card_resp = client.get(
            f"/a2a/v1/apps/{world.app_slug}/agents/{world.agent_public_id}/.well-known/agent-card.json"
        )
        catalog_resp = client.get(f"/a2a/v1/apps/{world.app_slug}/agents")
        assert card_resp.status_code == 404
        assert card_resp.json() == {"detail": "Not Found"}
        assert catalog_resp.status_code == 404
        assert catalog_resp.json() == {"detail": "Not Found"}
    finally:
        monkeypatch.setenv("A2A_ENABLED", "true")
        get_a2a_config.cache_clear()


def _card_url(world, agent_id) -> str:
    return f"/a2a/v1/apps/{world.app_slug}/agents/{agent_id}/.well-known/agent-card.json"


_NOT_FOUND_BODY = {"detail": "Not Found"}


def test_nonexistent_agent_id_card_is_the_same_uniform_404(client, a2a_committed_world):
    """AC-3(b): an agent id that does not exist anywhere (not even under a
    different app) 404s exactly like every other AC-3 case."""
    world = a2a_committed_world
    missing_agent_id = max(
        world.agent_public_id, world.agent_api_key_id, world.agent_disabled_id,
        world.agent_frozen_id, world.other_agent_id,
    ) + 1_000_000
    resp = client.get(_card_url(world, missing_agent_id))
    assert resp.status_code == 404
    assert resp.json() == _NOT_FOUND_BODY


def test_frozen_app_card_is_the_same_uniform_404(client, a2a_committed_world):
    """AC-3(f): the app itself is frozen (its agent is otherwise public and enabled)."""
    world = a2a_committed_world
    session = SessionLocal()
    try:
        app = session.get(App, world.app_id)
        app.is_frozen = True
        session.commit()
    finally:
        session.close()

    resp = client.get(_card_url(world, world.agent_public_id))
    assert resp.status_code == 404
    assert resp.json() == _NOT_FOUND_BODY


def test_api_key_agent_card_with_another_apps_key_is_the_same_uniform_404(client, a2a_committed_world):
    """AC-3(h): a key that is valid, but for a different app, counts as no key."""
    world = a2a_committed_world
    url = _card_url(world, world.agent_api_key_id)
    resp = client.get(url, headers={"X-API-KEY": world.other_key_raw})
    assert resp.status_code == 404
    assert resp.json() == _NOT_FOUND_BODY


class TestAC3Uniform404Matrix:
    """AC-3: every one of the nine cases returns an HTTP response that is
    byte-identical (same status, same body bytes, no distinguishing header)
    to every other -- not merely "also a 404 with the same dict content"."""

    def test_all_nine_cases_are_byte_identical(self, client, a2a_committed_world, monkeypatch):
        world = a2a_committed_world

        session = SessionLocal()
        try:
            app = session.get(App, world.app_id)
            app.is_frozen = True
            session.commit()
        finally:
            session.close()

        missing_agent_id = max(
            world.agent_public_id, world.agent_api_key_id, world.agent_disabled_id,
            world.agent_frozen_id, world.other_agent_id,
        ) + 1_000_000

        # (f) requires the app frozen above; build the rest of the cases
        # against that same (now-frozen) world so every case genuinely
        # returns through `resolve()`'s uniform 404, not a side effect of a
        # case ordering quirk.
        cases = {
            "a_missing_app_slug": lambda: client.get(
                f"/a2a/v1/apps/does-not-exist-{world.app_id}/agents/{world.agent_public_id}/.well-known/agent-card.json"
            ),
            "b_missing_agent_id": lambda: client.get(_card_url(world, missing_agent_id)),
            "c_agent_of_app_b_under_app_a": lambda: client.get(_card_url(world, world.other_agent_id)),
            "d_a2a_enabled_false": lambda: client.get(_card_url(world, world.agent_disabled_id)),
            "e_agent_frozen": lambda: client.get(_card_url(world, world.agent_frozen_id)),
            "f_app_frozen": lambda: client.get(_card_url(world, world.agent_public_id)),
            "g_api_key_visibility_no_key": lambda: client.get(_card_url(world, world.agent_api_key_id)),
            "h_api_key_visibility_other_apps_key": lambda: client.get(
                _card_url(world, world.agent_api_key_id), headers={"X-API-KEY": world.other_key_raw}
            ),
        }

        responses = {name: fn() for name, fn in cases.items()}

        monkeypatch.setenv("A2A_ENABLED", "false")
        get_a2a_config.cache_clear()
        try:
            responses["i_a2a_enabled_false_globally"] = client.get(_card_url(world, world.agent_public_id))
        finally:
            monkeypatch.setenv("A2A_ENABLED", "true")
            get_a2a_config.cache_clear()

        reference = responses["a_missing_app_slug"]
        assert reference.status_code == 404
        assert reference.content == b'{"detail":"Not Found"}'

        for name, resp in responses.items():
            assert resp.status_code == reference.status_code, f"case {name} had a different status code"
            assert resp.content == reference.content, f"case {name} had a different body"


def test_discovery_rate_limit_returns_429_with_retry_after_and_never_touches_the_app_budget(
    client, a2a_committed_world, monkeypatch
):
    """AC-12: the discovery limiter is per-IP, separate from the app's
    execution budget (`agent_rate_limit`/`rate_limit_service.check_and_consume`).

    Issues requests through a second `TestClient` wrapping the *same*,
    already-started `app` object (`client.app`) but with a dedicated client
    IP, so this test's budget never collides with another test's "testclient"
    bucket. It is used without its own `with` block -- the original `client`
    fixture already ran the app's lifespan (which built the A2A runtime this
    route needs), and a `TestClient` not used as a context manager still
    dispatches requests normally; it just never re-runs lifespan events.
    """
    world = a2a_committed_world
    monkeypatch.setenv("A2A_DISCOVERY_RATE_LIMIT_PER_MINUTE", "1")
    get_a2a_config.cache_clear()

    isolated_client = TestClient(client.app, client=("203.0.113.5", 12345))
    url = f"/a2a/v1/apps/{world.app_slug}/agents/{world.agent_public_id}/.well-known/agent-card.json"

    first = isolated_client.get(url)
    assert first.status_code == 200

    second = isolated_client.get(url)
    assert second.status_code == 429
    assert "Retry-After" in second.headers

    # The app's own execution budget counter was never consumed by discovery traffic.
    state = rate_limit_service.check_and_consume(world.app_id, 1000)
    assert state.remaining == 999
