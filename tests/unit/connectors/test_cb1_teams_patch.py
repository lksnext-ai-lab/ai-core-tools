"""CB-1: PATCH of a Teams destination rejects config/credentials, atomically (FR-13, AC-18, AC-19)."""

import pytest
from fastapi import HTTPException
from models.output_delivery import OutputDestination
from routers.internal import output_providers as router
from schemas.output_provider_schemas import OutputDestinationUpdateSchema
from services.output_channels import destinations

from .factories import HMAC_SECRET, TEAMS_URL, WEBHOOK_URL, make_destination

REJECTED = "Teams destinations do not accept webhook settings or credentials"
OTHER_WORKFLOW = "Changing the Workflow or channel requires creating a new destination"


@pytest.fixture
def db(outbox):
    with outbox() as session:
        session.add_all([
            make_destination(1, name="Teams", credentials={}),
            make_destination(2, name="Hook", provider_key="webhook", config={"auth_mode": "none"}),
        ])
        session.commit()
        yield session


def _patch(db, destination_id=1, **fields):
    return router.patch_output_destination(
        app_id=1, destination_id=destination_id, payload=OutputDestinationUpdateSchema(**fields), role=None, db=db,
    )


def _patch_error(db, destination_id=1, **fields):
    with pytest.raises(HTTPException) as caught:
        _patch(db, destination_id, **fields)
    return caught.value.status_code, caught.value.detail


def _state(db, destination_id=1):
    """Attributes of the identity-map object in THIS session (no expire/refresh): sees un-flushed mutations."""
    row = db.get(OutputDestination, destination_id)
    return (row.name, row.enabled, row.content_mode, row.webhook_url, row.public_config, row.credentials)


def _assert_untouched(db, outbox, before, destination_id=1):
    """Nothing was mutated in the session; a later commit in the same session persists nothing either."""
    assert not db.dirty
    assert _state(db, destination_id) == before
    db.commit()
    assert _reread(outbox, destination_id) == before


def _reread(outbox, destination_id=1):
    with outbox() as other:
        row = other.get(OutputDestination, destination_id)
        return (row.name, row.enabled, row.content_mode, row.webhook_url, row.public_config, row.credentials)


@pytest.mark.parametrize("fields", [
    {"public_config": {"auth_mode": "none"}},
    {"public_config": {"anything": 1}},
    {"credentials": {"bearer_token": "x"}},
])
def test_non_empty_config_or_credentials_is_rejected(db, outbox, fields):
    assert _patch_error(db, **fields) == (400, REJECTED)
    assert _reread(outbox)[4:] == ({}, {})


@pytest.mark.parametrize("fields", [
    {"public_config": {}},
    {"credentials": {}},
    {"credentials": None},
    {"clear_credentials": True},
    {"clear_credentials": False},
])
def test_empty_inputs_are_noops(db, outbox, fields):
    result = _patch(db, **fields)
    assert result["name"] == "Teams"
    assert _reread(outbox)[4:] == ({}, {})  # pre-existing credentials={} stays {}


def test_rotation_on_same_endpoint_updates_url(db, outbox):
    rotated = TEAMS_URL.replace("sig=secret", "sig=rotated")
    _patch(db, webhook_url=rotated)
    assert _reread(outbox)[3] == rotated


def test_different_endpoint_is_rejected(db, outbox):
    assert _patch_error(db, webhook_url="https://prod.logic.azure.com/workflows/other") == (400, OTHER_WORKFLOW)
    assert _reread(outbox)[3] == TEAMS_URL


def test_name_mode_and_enabled_are_applied(db, outbox):
    _patch(db, name="Renamed", content_mode="excerpt", enabled=False)
    assert _reread(outbox)[:3] == ("Renamed", False, "excerpt")


def test_rejection_is_atomic_for_teams(db, outbox):
    before = _state(db)
    assert _patch_error(db, name="New", enabled=False, content_mode="link_only",
                        public_config={"auth_mode": "none"}) == (400, REJECTED)
    _assert_untouched(db, outbox, before)


def test_credentials_rejection_is_atomic_for_teams(db, outbox):
    before = _state(db)
    assert _patch_error(db, name="New", enabled=False, credentials={"a": "b"}) == (400, REJECTED)
    _assert_untouched(db, outbox, before)


def test_url_rejection_precedes_settings_rejection(db, outbox):
    before = _state(db)
    status, detail = _patch_error(db, name="New", enabled=False, webhook_url="https://prod.logic.azure.com/other",
                                  credentials={"a": "b"})
    assert (status, detail) == (400, OTHER_WORKFLOW)
    _assert_untouched(db, outbox, before)


def test_invalid_name_and_mode_precedence_unchanged(db, outbox):
    before = _state(db)
    assert _patch_error(db, name=" ", enabled=False, public_config={"a": 1})[1].startswith(
        "Destination name is required")
    _assert_untouched(db, outbox, before)
    assert _patch_error(db, 1, name="New", content_mode="result", public_config={"a": 1})[1] == REJECTED
    _assert_untouched(db, outbox, before)
    with pytest.raises(ValueError, match="content mode"):
        destinations.update_destination(db, db.get(OutputDestination, 1),
                                        {"name": "New", "enabled": False, "content_mode": "everything"})
    _assert_untouched(db, outbox, before)


def test_webhook_url_error_is_atomic(db, outbox):
    before = _state(db, 2)
    status, detail = _patch_error(db, 2, name="Renamed", enabled=False, content_mode="excerpt",
                                  webhook_url="https://other.example.com/mattin")
    assert status == 400 and "new destination" in detail
    _assert_untouched(db, outbox, before, 2)


def test_webhook_credentials_error_is_atomic(db, outbox):
    before = _state(db, 2)
    status, _ = _patch_error(db, 2, name="Renamed", enabled=False, public_config={"auth_mode": "hmac_sha256"},
                             credentials={"signing_secret": "short"})
    assert status == 400
    _assert_untouched(db, outbox, before, 2)


def test_webhook_empty_credentials_with_clear_is_accepted(db, outbox):
    _patch(db, 2, credentials={}, clear_credentials=True)
    config, credentials = _reread(outbox, 2)[4:]
    assert config["auth_mode"] == "none" and credentials is None


def test_unknown_provider_is_rejected_before_any_mutation(db, outbox):
    row = db.get(OutputDestination, 1)
    row.provider_key = "ghost"
    db.commit()
    before = _state(db)
    with pytest.raises(ValueError, match="ghost"):
        destinations.update_destination(db, row, {"name": "New", "enabled": False, "public_config": {"a": 1}})
    _assert_untouched(db, outbox, before)


def test_webhook_patch_still_applies_everything(db, outbox):
    _patch(db, 2, name="Renamed", public_config={"auth_mode": "hmac_sha256"},
           credentials={"signing_secret": HMAC_SECRET}, webhook_url=WEBHOOK_URL + "?")
    name, _, _, _, config, credentials = _reread(outbox, 2)
    assert name == "Renamed" and config["auth_mode"] == "hmac_sha256"
    assert credentials == {"signing_secret": HMAC_SECRET}
