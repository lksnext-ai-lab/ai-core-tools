"""Typed settings for the webhook provider.

Error messages come from the hand-written checks in ``parse_webhook_settings`` (same
order and texts as the historical ``validate_webhook_config``); the models are built
only after every check passed, so Pydantic never produces a user-facing message.
"""

import base64
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    SecretStr,
    StrictBool,
    field_validator,
    model_validator,
)

from connectors.core.messages import JsonDict
from connectors.core.settings import DestinationSettingsBase

_MODEL_CONFIG = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)


class WebhookPublicConfig(BaseModel):
    model_config = _MODEL_CONFIG

    schema_version: Literal["1"] = "1"
    auth_mode: Literal["hmac_sha256", "bearer", "none"] = "hmac_sha256"
    receiver_deduplicates: StrictBool = False
    include_attachments: StrictBool = False


PUBLIC_CONFIG_KEYS = frozenset(WebhookPublicConfig.model_fields)


class WebhookHmacCredentials(BaseModel):
    model_config = _MODEL_CONFIG

    signing_secret: SecretStr

    @field_validator("signing_secret")
    @classmethod
    def _check_signing_secret(cls, value: SecretStr) -> SecretStr:
        try:
            key = base64.b64decode(value.get_secret_value(), validate=True)
        except (ValueError, TypeError):
            raise ValueError("HMAC signing secret must be base64 encoded") from None
        if len(key) != 32:
            raise ValueError("HMAC signing secret must contain exactly 32 random bytes")
        return value

    def to_storage(self) -> dict[str, str]:
        return {"signing_secret": self.signing_secret.get_secret_value()}


class WebhookBearerCredentials(BaseModel):
    model_config = _MODEL_CONFIG

    bearer_token: SecretStr

    @field_validator("bearer_token")
    @classmethod
    def _check_bearer_token(cls, value: SecretStr) -> SecretStr:
        token = value.get_secret_value()
        if not token or len(token) > 4096 or any(ord(char) < 33 or ord(char) > 126 for char in token):
            raise ValueError("Bearer token must be a non-empty printable ASCII token")
        return value

    def to_storage(self) -> dict[str, str]:
        return {"bearer_token": self.bearer_token.get_secret_value()}


class WebhookNoCredentials(BaseModel):
    model_config = _MODEL_CONFIG

    def to_storage(self) -> dict[str, str]:
        return {}


WebhookCredentials = WebhookHmacCredentials | WebhookBearerCredentials | WebhookNoCredentials


class WebhookSettings(DestinationSettingsBase):
    provider_key: Literal["webhook"] = "webhook"
    public_config: WebhookPublicConfig
    credentials: WebhookCredentials

    @model_validator(mode="after")
    def _credentials_match_auth_mode(self) -> "WebhookSettings":
        expected = {
            "hmac_sha256": WebhookHmacCredentials, "bearer": WebhookBearerCredentials, "none": WebhookNoCredentials,
        }[self.public_config.auth_mode]
        if type(self.credentials) is not expected:
            raise ValueError("Credentials do not match the webhook authentication mode")
        return self

    def public_config_json(self) -> JsonDict:
        return dict(self.public_config.model_dump())

    def credentials_json(self) -> dict[str, str]:
        return self.credentials.to_storage()


def parse_webhook_settings(
    config: Mapping[str, Any] | None, credentials: Mapping[str, str] | None,
) -> WebhookSettings:
    """Run the historical checks (same order, same texts), then build the typed models."""
    config = dict(config or {})
    credentials = dict(credentials or {})
    if set(config) - PUBLIC_CONFIG_KEYS:
        raise ValueError("Webhook configuration contains unsupported fields")
    if config.get("schema_version", "1") != "1":
        raise ValueError("Unsupported webhook schema version")
    config["schema_version"] = "1"
    auth_mode = config.get("auth_mode", "hmac_sha256")
    if auth_mode not in {"hmac_sha256", "bearer", "none"}:
        raise ValueError("Unsupported webhook authentication mode")
    config["auth_mode"] = auth_mode
    config["receiver_deduplicates"] = config.get("receiver_deduplicates", False)
    config["include_attachments"] = config.get("include_attachments", False)
    if type(config["receiver_deduplicates"]) is not bool or type(config["include_attachments"]) is not bool:
        raise ValueError("Webhook boolean configuration values must be true or false")
    typed_credentials: WebhookCredentials
    if auth_mode == "hmac_sha256":
        encoded = credentials.get("signing_secret", "")
        try:
            key = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("HMAC signing secret must be base64 encoded") from exc
        if len(key) != 32 or set(credentials) != {"signing_secret"}:
            raise ValueError("HMAC signing secret must contain exactly 32 random bytes")
        typed_credentials = WebhookHmacCredentials(signing_secret=SecretStr(encoded))
    elif auth_mode == "bearer":
        token = credentials.get("bearer_token", "")
        if not token or len(token) > 4096 or any(ord(char) < 33 or ord(char) > 126 for char in token):
            raise ValueError("Bearer token must be a non-empty printable ASCII token")
        if set(credentials) != {"bearer_token"}:
            raise ValueError("Bearer authentication accepts only a bearer token")
        typed_credentials = WebhookBearerCredentials(bearer_token=SecretStr(token))
    elif credentials:
        raise ValueError("Authentication mode none does not accept credentials")
    else:
        typed_credentials = WebhookNoCredentials()
    return WebhookSettings(
        provider_key="webhook",
        public_config=WebhookPublicConfig(
            schema_version="1", auth_mode=auth_mode, receiver_deduplicates=config["receiver_deduplicates"],
            include_attachments=config["include_attachments"],
        ),
        credentials=typed_credentials,
    )
