"""Typed destination settings: equivalence with the historical checks, errors, secrecy."""

import base64
import itertools
from types import SimpleNamespace

import pytest
from connectors import registry
from connectors.core.settings import DestinationSettingsBase
from connectors.providers.teams_workflow.config import (
    TeamsWorkflowCredentials,
    TeamsWorkflowPublicConfig,
    TeamsWorkflowSettings,
    parse_teams_workflow_settings,
)
from connectors.providers.webhook.config import (
    WebhookBearerCredentials,
    WebhookHmacCredentials,
    WebhookNoCredentials,
    WebhookPublicConfig,
    WebhookSettings,
    parse_webhook_settings,
)
from connectors.providers.webhook.provider import validate_webhook_config
from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError
from routers.internal import output_providers as router
from schemas.output_provider_schemas import OutputDestinationCreateSchema

from .factories import TEAMS_URL

AUTH = SimpleNamespace(identity=SimpleNamespace(id="7"))
SECRET_B64 = base64.b64encode(b"k" * 32).decode("ascii")
BEARER = "tok-en_SECRET.123"
WEBHOOK_URL = "https://hooks.example.com/mattin"
CREDENTIALS_BY_MODE = {
    "hmac_sha256": {"signing_secret": SECRET_B64},
    "bearer": {"bearer_token": BEARER},
    "none": {},
}
STORED_KEYS = ["schema_version", "auth_mode", "receiver_deduplicates", "include_attachments"]


def _combinations():
    for mode, dedup, attach in itertools.product(CREDENTIALS_BY_MODE, (False, True), (False, True)):
        yield (
            {"schema_version": "1", "auth_mode": mode, "receiver_deduplicates": dedup, "include_attachments": attach},
            CREDENTIALS_BY_MODE[mode],
        )
    yield {}, CREDENTIALS_BY_MODE["hmac_sha256"]
    yield {"auth_mode": "bearer"}, CREDENTIALS_BY_MODE["bearer"]
    yield {"include_attachments": True, "auth_mode": "none"}, {}
    yield None, CREDENTIALS_BY_MODE["hmac_sha256"]


@pytest.mark.parametrize(("config", "credentials"), list(_combinations()))
def test_equivalent_to_validate_webhook_config_and_round_trips(config, credentials):
    settings = parse_webhook_settings(config, credentials)
    dumped = settings.public_config_json()
    assert dumped == validate_webhook_config(config, credentials)
    assert list(dumped) == STORED_KEYS
    assert settings.credentials_json() == credentials
    assert parse_webhook_settings(dumped, settings.credentials_json()) == settings


def test_typed_credentials_variants():
    assert isinstance(parse_webhook_settings({}, CREDENTIALS_BY_MODE["hmac_sha256"]).credentials, WebhookHmacCredentials)
    assert isinstance(
        parse_webhook_settings({"auth_mode": "bearer"}, CREDENTIALS_BY_MODE["bearer"]).credentials,
        WebhookBearerCredentials,
    )
    assert isinstance(parse_webhook_settings({"auth_mode": "none"}, None).credentials, WebhookNoCredentials)


def test_public_config_defaults_and_strictness():
    assert WebhookPublicConfig().model_dump() == {
        "schema_version": "1", "auth_mode": "hmac_sha256", "receiver_deduplicates": False, "include_attachments": False,
    }
    for bad in ({"receiver_deduplicates": 1}, {"unknown": True}, {"schema_version": 1}):
        with pytest.raises(ValidationError):
            WebhookPublicConfig(**bad)
    with pytest.raises(ValidationError):
        WebhookPublicConfig().include_attachments = True  # frozen


def test_type_adapter_union_for_both_providers():
    adapter = TypeAdapter(registry.DestinationSettings)
    webhook = adapter.validate_python({
        "provider_key": "webhook",
        "public_config": {"auth_mode": "bearer"},
        "credentials": {"bearer_token": BEARER},
    })
    teams = adapter.validate_python({"provider_key": "teams_workflow", "public_config": {}, "credentials": {}})
    assert isinstance(webhook, WebhookSettings) and isinstance(teams, TeamsWorkflowSettings)
    for parsed in (webhook, teams):
        assert adapter.validate_python(adapter.dump_python(parsed)) == parsed
    assert webhook.credentials_json() == {"bearer_token": BEARER}
    with pytest.raises(ValidationError):
        adapter.validate_python({"provider_key": "other", "public_config": {}, "credentials": {}})


def test_parse_destination_settings_delegates_to_the_provider():
    assert isinstance(registry.parse_destination_settings("webhook", {}, CREDENTIALS_BY_MODE["hmac_sha256"]), WebhookSettings)
    parsed = registry.parse_destination_settings("teams_workflow", {}, None)
    assert isinstance(parsed, DestinationSettingsBase) and isinstance(parsed, TeamsWorkflowSettings)
    with pytest.raises(ValueError, match="Unsupported output provider: nope"):
        registry.parse_destination_settings("nope", {}, None)


ERROR_CASES = [
    ({"extra": 1}, CREDENTIALS_BY_MODE["hmac_sha256"], "Webhook configuration contains unsupported fields"),
    ({"schema_version": "2"}, CREDENTIALS_BY_MODE["hmac_sha256"], "Unsupported webhook schema version"),
    ({"auth_mode": "basic"}, {}, "Unsupported webhook authentication mode"),
    ({"include_attachments": "yes"}, CREDENTIALS_BY_MODE["hmac_sha256"],
     "Webhook boolean configuration values must be true or false"),
    ({}, {"signing_secret": "***not-base64***"}, "HMAC signing secret must be base64 encoded"),
    ({}, {"signing_secret": base64.b64encode(b"short").decode()}, "HMAC signing secret must contain exactly 32 random bytes"),
    ({}, {"signing_secret": SECRET_B64, "extra": "x"}, "HMAC signing secret must contain exactly 32 random bytes"),
    ({"auth_mode": "bearer"}, {"bearer_token": "café"}, "Bearer token must be a non-empty printable ASCII token"),
    ({"auth_mode": "bearer"}, {"bearer_token": "a" * 4097}, "Bearer token must be a non-empty printable ASCII token"),
    ({"auth_mode": "bearer"}, {"bearer_token": BEARER, "x": "y"}, "Bearer authentication accepts only a bearer token"),
    ({"auth_mode": "none"}, {"x": "y"}, "Authentication mode none does not accept credentials"),
]


@pytest.mark.parametrize(("config", "credentials", "message"), ERROR_CASES)
def test_error_messages_are_unchanged(config, credentials, message):
    for call in (parse_webhook_settings, validate_webhook_config):
        with pytest.raises(ValueError) as caught:
            call(config, credentials)
        assert str(caught.value) == message


@pytest.fixture
def db(outbox):
    with outbox() as session:
        yield session


@pytest.mark.parametrize(("config", "credentials", "message"), ERROR_CASES)
def test_router_maps_errors_to_http_400_with_same_detail(db, config, credentials, message):
    payload = OutputDestinationCreateSchema(
        name="Hook", provider_key="webhook", webhook_url=WEBHOOK_URL, public_config=config, credentials=credentials,
    )
    with pytest.raises(HTTPException) as caught:
        router.create_output_destination(app_id=1, payload=payload, auth=AUTH, role=None, db=db)
    assert caught.value.status_code == 400
    assert caught.value.detail == message


def test_router_teams_rejection_is_http_400(db):
    payload = OutputDestinationCreateSchema(name="T", webhook_url=TEAMS_URL, public_config={"x": 1})
    with pytest.raises(HTTPException) as caught:
        router.create_output_destination(app_id=1, payload=payload, auth=AUTH, role=None, db=db)
    assert caught.value.status_code == 400
    assert caught.value.detail == "Teams destinations do not accept webhook settings or credentials"


def test_secrets_never_appear_in_repr_or_str():
    for config, credentials in (
        ({}, CREDENTIALS_BY_MODE["hmac_sha256"]), ({"auth_mode": "bearer"}, CREDENTIALS_BY_MODE["bearer"]),
    ):
        settings = parse_webhook_settings(config, credentials)
        secret = next(iter(credentials.values()))
        for obj in (settings, settings.credentials):
            assert secret not in repr(obj) and secret not in str(obj)
        assert secret not in settings.model_dump_json()
    assert BEARER not in repr(parse_webhook_settings({"auth_mode": "bearer"}, CREDENTIALS_BY_MODE["bearer"]).credentials)


def test_teams_empty_valid_and_unknown_keys_fail_with_fixed_message():
    settings = parse_teams_workflow_settings({}, {})
    assert settings.public_config_json() == {} and settings.credentials_json() == {}
    assert parse_teams_workflow_settings(None, None) == settings
    assert TeamsWorkflowPublicConfig() == settings.public_config and TeamsWorkflowCredentials() == settings.credentials
    for config, credentials in (({"x": 1}, None), (None, {"token": "s3cr3t-value"}), ({"x": 1}, {"a": "b"})):
        with pytest.raises(ValueError) as caught:
            parse_teams_workflow_settings(config, credentials)
        assert str(caught.value) == "Teams destinations do not accept webhook settings or credentials"
        assert caught.value.__cause__ is None and caught.value.__context__ is None
        assert "s3cr3t-value" not in repr(caught.value)


def test_validate_webhook_config_keeps_historical_key_order_for_partial_input():
    stored = validate_webhook_config({"include_attachments": True, "auth_mode": "none"}, {})
    assert list(stored) == ["include_attachments", "auth_mode", "schema_version", "receiver_deduplicates"]


def _webhook_dict(auth_mode, credentials):
    return {"provider_key": "webhook", "public_config": {"auth_mode": auth_mode}, "credentials": credentials}


@pytest.mark.parametrize(("auth_mode", "credentials"), [
    ("hmac_sha256", {"signing_secret": base64.b64encode(b"short").decode()}),
    ("hmac_sha256", {"signing_secret": "**********"}),
    ("bearer", {"bearer_token": "has space"}),
    ("bearer", {"bearer_token": "café"}),
    ("bearer", {"bearer_token": ""}),
    ("bearer", {"signing_secret": SECRET_B64}),
    ("none", {"bearer_token": BEARER}),
    ("hmac_sha256", {}),
])
def test_union_models_protect_themselves(auth_mode, credentials):
    with pytest.raises(ValidationError) as caught:
        registry.DESTINATION_SETTINGS_ADAPTER.validate_python(_webhook_dict(auth_mode, credentials))
    text = str(caught.value)
    for value in credentials.values():
        if value:
            assert value not in text


def test_union_rejects_credentials_of_the_wrong_kind_for_the_mode():
    with pytest.raises(ValidationError):
        TypeAdapter(registry.DestinationSettings).validate_python(
            _webhook_dict("hmac_sha256", {"bearer_token": BEARER}),
        )


def test_teams_fixed_message_without_context_and_for_non_mappings():
    with pytest.raises(ValueError) as caught:
        parse_teams_workflow_settings(None, {"token": "s3cr3t-value"})
    assert caught.value.__context__ is None and "s3cr3t-value" not in repr(caught.value.__context__)
    with pytest.raises(ValueError) as caught:
        parse_teams_workflow_settings("abc", None)
    assert str(caught.value) == "Teams destinations do not accept webhook settings or credentials"


def test_public_config_keys_come_from_the_model():
    from connectors.providers.webhook.config import PUBLIC_CONFIG_KEYS

    assert PUBLIC_CONFIG_KEYS == frozenset(STORED_KEYS)


def test_masked_bearer_token_is_still_accepted_as_at_head():
    # "**********" is a valid printable token today; persisting settings must go through
    # credentials_json()/to_storage(), never model_dump(mode="json") (which masks secrets).
    settings = parse_webhook_settings({"auth_mode": "bearer"}, {"bearer_token": "**********"})
    assert settings.credentials_json() == {"bearer_token": "**********"}
