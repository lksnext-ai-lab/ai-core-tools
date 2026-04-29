from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest

from services.a2a_service import A2AService
from utils.secret_utils import mask_secret


def _make_skill(skill_id: str, name: str):
    return SimpleNamespace(
        id=skill_id,
        name=name,
        model_dump=lambda mode="json", exclude_none=True: {
            "id": skill_id,
            "name": name,
        },
    )


def _make_card(card_snapshot: dict, skills: list[SimpleNamespace]):
    return SimpleNamespace(
        url=card_snapshot["url"],
        documentation_url=card_snapshot.get("documentationUrl"),
        icon_url=card_snapshot.get("iconUrl"),
        skills=skills,
        model_dump=lambda mode="json", exclude_none=True: card_snapshot,
    )


@pytest.mark.asyncio
async def test_validate_source_config_canonicalizes_api_key_auth(monkeypatch):
    card_snapshot = {
        "url": "https://remote.example.com",
        "name": "Remote Agent",
        "skills": [{"id": "skill-1", "name": "Search"}],
        "securitySchemes": {
            "remoteApiKey": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
            },
        },
    }
    card = _make_card(card_snapshot, [_make_skill("skill-1", "Search")])

    async def fake_resolve_with_snapshot(card_url: str):
        return card, card_snapshot

    monkeypatch.setattr(A2AService, "_resolve_agent_card_with_snapshot", fake_resolve_with_snapshot)

    canonical = await A2AService.validate_source_config({
        "card_url": "https://remote.example.com/.well-known/agent-card.json",
        "auth_config": {
            "scheme_name": "remoteApiKey",
            "api_key": "secret-api-key",
        },
    })

    assert canonical["remote_agent_id"] == "https://remote.example.com"
    assert canonical["remote_agent_metadata"] == card_snapshot
    assert canonical["auth_config"] == {
        "scheme_name": "remoteApiKey",
        "scheme_type": "apiKey",
        "api_key": "secret-api-key",
    }


@pytest.mark.asyncio
async def test_validate_source_config_preserves_existing_masked_bearer_token(monkeypatch):
    card_snapshot = {
        "url": "https://remote.example.com",
        "name": "Remote Agent",
        "skills": [{"id": "skill-1", "name": "Search"}],
        "securitySchemes": {
            "google": {
                "openIdConnectSecurityScheme": {
                    "openIdConnectUrl": "https://accounts.example.com/.well-known/openid-configuration",
                },
            },
        },
    }
    card = _make_card(card_snapshot, [_make_skill("skill-1", "Search")])

    async def fake_resolve_with_snapshot(card_url: str):
        return card, card_snapshot

    monkeypatch.setattr(A2AService, "_resolve_agent_card_with_snapshot", fake_resolve_with_snapshot)

    canonical = await A2AService.validate_source_config(
        {
            "card_url": "https://remote.example.com/.well-known/agent-card.json",
            "auth_config": {
                "scheme_name": "google",
                "bearer_token": mask_secret("existing-access-token"),
            },
        },
        existing_auth_config={
            "scheme_name": "google",
            "scheme_type": "openIdConnect",
            "bearer_token": "existing-access-token",
        },
    )

    assert canonical["auth_config"] == {
        "scheme_name": "google",
        "scheme_type": "openIdConnect",
        "bearer_token": "existing-access-token",
    }


def test_serialize_record_masks_auth_config_secrets():
    record = SimpleNamespace(
        card_url="https://remote.example.com/.well-known/agent-card.json",
        remote_agent_id="https://remote.example.com",
        auth_config={
            "scheme_name": "remoteApiKey",
            "scheme_type": "apiKey",
            "api_key": "secret-api-key",
        },
        remote_agent_metadata={
            "name": "Remote Agent",
            "skills": [{"id": "skill-1", "name": "Search"}],
        },
        sync_status="synced",
        health_status="healthy",
        last_successful_refresh_at=None,
        last_refresh_attempt_at=None,
        last_refresh_error=None,
        documentation_url=None,
        icon_url=None,
    )

    serialized = A2AService.serialize_record(record)

    assert serialized["auth_config"] == {
        "scheme_name": "remoteApiKey",
        "scheme_type": "apiKey",
        "api_key": mask_secret("secret-api-key"),
    }
    assert serialized["advertised_skills"] == [{"id": "skill-1", "name": "Search"}]


@pytest.mark.asyncio
async def test_create_authenticated_httpx_client_applies_query_api_key():
    timeout = httpx.Timeout(5.0)
    card_snapshot = {
        "securitySchemes": {
            "queryKey": {
                "type": "apiKey",
                "in": "query",
                "name": "token",
            },
        },
    }
    auth_config = {
        "scheme_name": "queryKey",
        "scheme_type": "apiKey",
        "api_key": "secret-query-token",
    }

    async with A2AService.create_authenticated_httpx_client(
        card_snapshot=card_snapshot,
        auth_config=auth_config,
        timeout=timeout,
    ) as client:
        assert client.params["token"] == "secret-query-token"


@pytest.mark.asyncio
async def test_refresh_card_updates_cached_metadata(monkeypatch):
    card_snapshot = {
        "url": "https://remote.example.com",
        "name": "Remote Agent",
        "skills": [{"id": "skill-1", "name": "Updated Search"}],
        "documentationUrl": "https://docs.example.com/agent",
        "iconUrl": "https://docs.example.com/icon.png",
    }
    card = _make_card(card_snapshot, [_make_skill("skill-1", "Updated Search")])
    record = SimpleNamespace(
        agent_id=7,
        card_url="https://remote.example.com/.well-known/agent-card.json",
        remote_agent_id="https://remote.example.com/old",
        remote_agent_metadata={"name": "Old Agent"},
        sync_status="error",
        health_status="degraded",
        last_successful_refresh_at=None,
        last_refresh_attempt_at=None,
        last_refresh_error="stale",
        documentation_url=None,
        icon_url=None,
    )
    db = MagicMock()

    async def fake_resolve_with_snapshot(card_url: str):
        return card, card_snapshot

    monkeypatch.setattr(A2AService, "_resolve_agent_card_with_snapshot", fake_resolve_with_snapshot)

    refreshed = await A2AService.refresh_card(record, db)

    assert refreshed is record
    assert record.remote_agent_id == "https://remote.example.com"
    assert record.remote_agent_metadata == card_snapshot
    assert record.sync_status == A2AService.SYNCED
    assert record.health_status == A2AService.HEALTHY
    assert record.last_refresh_error is None
    assert record.last_successful_refresh_at is not None
    assert record.last_refresh_attempt_at == record.last_successful_refresh_at
    db.add.assert_called_once_with(record)
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_refresh_card_keeps_agent_healthy_when_advertised_skills_change(monkeypatch):
    card_snapshot = {
        "url": "https://remote.example.com",
        "name": "Remote Agent",
        "skills": [{"id": "skill-2", "name": "Other Skill"}],
    }
    card = _make_card(card_snapshot, [_make_skill("skill-2", "Other Skill")])
    record = SimpleNamespace(
        agent_id=7,
        card_url="https://remote.example.com/.well-known/agent-card.json",
        remote_agent_id="https://remote.example.com",
        remote_agent_metadata={"name": "Old Agent"},
        sync_status="synced",
        health_status="healthy",
        last_successful_refresh_at=None,
        last_refresh_attempt_at=None,
        last_refresh_error=None,
        documentation_url=None,
        icon_url=None,
    )
    db = MagicMock()

    async def fake_resolve_with_snapshot(card_url: str):
        return card, card_snapshot

    monkeypatch.setattr(A2AService, "_resolve_agent_card_with_snapshot", fake_resolve_with_snapshot)

    refreshed = await A2AService.refresh_card(record, db)

    assert refreshed is record
    assert record.remote_agent_metadata == card_snapshot
    assert record.sync_status == A2AService.SYNCED
    assert record.health_status == A2AService.HEALTHY
    assert record.last_refresh_error is None
    assert record.last_successful_refresh_at is not None
    assert record.last_refresh_attempt_at is not None
    db.add.assert_called_once_with(record)
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_discover_card_preserves_raw_authentication_metadata(monkeypatch):
    parsed_card_snapshot = {
        "url": "https://remote.example.com",
        "name": "Remote Agent",
        "skills": [{"id": "skill-1", "name": "Search"}],
    }
    raw_card_snapshot = {
        **parsed_card_snapshot,
        "authentication": {
            "schemes": ["x402"],
        },
    }
    card = _make_card(parsed_card_snapshot, [_make_skill("skill-1", "Search")])

    async def fake_resolve(card_url: str):
        return card

    async def fake_fetch_raw(card_url: str):
        return raw_card_snapshot

    monkeypatch.setattr(A2AService, "_resolve_agent_card", fake_resolve)
    monkeypatch.setattr(A2AService, "_fetch_raw_card_snapshot", fake_fetch_raw)

    discovery = await A2AService.discover_card(
        "https://remote.example.com/.well-known/agent.json"
    )

    assert discovery["card"]["authentication"] == {"schemes": ["x402"]}


@pytest.mark.asyncio
async def test_refresh_card_preserves_raw_authentication_metadata(monkeypatch):
    parsed_card_snapshot = {
        "url": "https://remote.example.com",
        "name": "Remote Agent",
        "skills": [{"id": "skill-1", "name": "Updated Search"}],
    }
    raw_card_snapshot = {
        **parsed_card_snapshot,
        "authentication": {
            "schemes": ["x402"],
        },
    }
    card = _make_card(parsed_card_snapshot, [_make_skill("skill-1", "Updated Search")])
    record = SimpleNamespace(
        agent_id=7,
        card_url="https://remote.example.com/.well-known/agent.json",
        remote_agent_id="https://remote.example.com/old",
        remote_agent_metadata={"name": "Old Agent"},
        sync_status="error",
        health_status="degraded",
        last_successful_refresh_at=None,
        last_refresh_attempt_at=None,
        last_refresh_error="stale",
        documentation_url=None,
        icon_url=None,
    )
    db = MagicMock()

    async def fake_resolve(card_url: str):
        return card

    async def fake_fetch_raw(card_url: str):
        return raw_card_snapshot

    monkeypatch.setattr(A2AService, "_resolve_agent_card", fake_resolve)
    monkeypatch.setattr(A2AService, "_fetch_raw_card_snapshot", fake_fetch_raw)

    refreshed = await A2AService.refresh_card(record, db)

    assert refreshed.remote_agent_metadata["authentication"] == {
        "schemes": ["x402"]
    }
