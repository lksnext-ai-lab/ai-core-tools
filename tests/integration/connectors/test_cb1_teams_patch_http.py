"""CB-1 over HTTP against PostgreSQL: a rejected PATCH changes nothing (AC-19)."""

import pytest
from connectors.core import http as core_http
from models.output_delivery import OutputDestination

TEAMS_URL = "https://prod.logic.azure.com/workflows/abc/triggers/manual?sig=secret"
WEBHOOK_URL = "https://hooks.example.com/mattin"
REJECTED = "Teams destinations do not accept webhook settings or credentials"


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch):
    monkeypatch.setattr(core_http, "resolve_host", lambda host: ["20.1.2.3"])


def _make(db, app, user, **overrides):
    values = {
        "app_id": app.app_id, "created_by": user.user_id, "name": "Teams", "provider_key": "teams_workflow",
        "content_mode": "result", "enabled": True, "public_config": {}, "credentials": None, "webhook_url": TEAMS_URL,
    }
    row = OutputDestination(**{**values, **overrides})
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def destination(db, fake_app, fake_user):
    return _make(db, fake_app, fake_user)


@pytest.fixture
def webhook_destination(db, fake_app, fake_user):
    return _make(db, fake_app, fake_user, name="Hook", provider_key="webhook", webhook_url=WEBHOOK_URL,
                 public_config={"schema_version": "1", "auth_mode": "none", "receiver_deduplicates": False,
                                "include_attachments": False})


def _url(app, row):
    return f"/internal/apps/{app.app_id}/output-destinations/{row.id}"


def _state(row):
    """Attributes of the identity-map object, read BEFORE any expire/refresh (sees un-flushed mutations)."""
    return (row.name, row.enabled, row.content_mode, row.webhook_url, row.public_config, row.credentials)


def _assert_untouched(db, row, before):
    assert not db.dirty
    assert _state(db.get(OutputDestination, row.id)) == before
    db.commit()  # a later commit in the same session must persist nothing
    db.expire_all()
    assert _state(db.get(OutputDestination, row.id)) == before


def test_rejected_teams_patch_is_atomic(client, db, owner_headers, fake_app, destination):
    before = _state(destination)
    response = client.patch(_url(fake_app, destination), headers=owner_headers, json={
        "name": "Renamed", "enabled": False, "content_mode": "link_only", "public_config": {"auth_mode": "none"},
    })
    assert response.status_code == 400
    assert response.json()["detail"] == REJECTED
    _assert_untouched(db, destination, before)


def test_rejected_teams_credentials_patch_is_atomic(client, db, owner_headers, fake_app, destination):
    before = _state(destination)
    response = client.patch(_url(fake_app, destination), headers=owner_headers,
                            json={"name": "Renamed", "enabled": False, "credentials": {"bearer_token": "x"}})
    assert (response.status_code, response.json()["detail"]) == (400, REJECTED)
    _assert_untouched(db, destination, before)


def test_rejected_webhook_url_patch_is_atomic(client, db, owner_headers, fake_app, webhook_destination):
    before = _state(webhook_destination)
    response = client.patch(_url(fake_app, webhook_destination), headers=owner_headers, json={
        "name": "Renamed", "enabled": False, "webhook_url": "https://other.example.com/mattin",
    })
    assert response.status_code == 400
    assert "new destination" in response.json()["detail"]
    _assert_untouched(db, webhook_destination, before)


def test_teams_rotation_on_same_endpoint(client, db, owner_headers, fake_app, destination):
    rotated = TEAMS_URL.replace("sig=secret", "sig=rotated")
    response = client.patch(_url(fake_app, destination), headers=owner_headers, json={"webhook_url": rotated})
    assert response.status_code == 200
    assert db.get(OutputDestination, destination.id).webhook_url == rotated


def test_noop_inputs_and_valid_fields_are_applied(client, db, owner_headers, fake_app, destination):
    response = client.patch(_url(fake_app, destination), headers=owner_headers, json={
        "name": "Renamed", "enabled": False, "public_config": {}, "credentials": {}, "clear_credentials": True,
    })
    assert response.status_code == 200
    db.expire_all()
    assert _state(db.get(OutputDestination, destination.id)) == (
        "Renamed", False, "result", TEAMS_URL, {}, None)
