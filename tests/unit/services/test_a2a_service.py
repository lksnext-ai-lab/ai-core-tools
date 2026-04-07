from types import SimpleNamespace

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

    async def fake_resolve(card_url: str):
        return card

    monkeypatch.setattr(A2AService, "_resolve_agent_card", fake_resolve)

    canonical = await A2AService.validate_source_config({
        "card_url": "https://remote.example.com/.well-known/agent-card.json",
        "selected_skill_id": "skill-1",
        "auth_config": {
            "scheme_name": "remoteApiKey",
            "api_key": "secret-api-key",
        },
    })

    assert canonical["remote_skill_id"] == "skill-1"
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

    async def fake_resolve(card_url: str):
        return card

    monkeypatch.setattr(A2AService, "_resolve_agent_card", fake_resolve)

    canonical = await A2AService.validate_source_config(
        {
            "card_url": "https://remote.example.com/.well-known/agent-card.json",
            "selected_skill_id": "skill-1",
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
        remote_skill_id="skill-1",
        remote_skill_name="Search",
        auth_config={
            "scheme_name": "remoteApiKey",
            "scheme_type": "apiKey",
            "api_key": "secret-api-key",
        },
        remote_agent_metadata={"name": "Remote Agent"},
        remote_skill_metadata={"id": "skill-1"},
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
