from datetime import datetime
from typing import Literal, Optional

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, SecretStr


class SCIMConnectionCreate(BaseModel):
    """Fields required to create a provider-neutral SCIM connection."""

    provider_type: str = Field(min_length=1, max_length=50)
    external_directory_id: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    auth_mode: Literal["static_bearer"] = "static_bearer"
    client_id: Optional[str] = Field(default=None, max_length=255)


class SCIMConnectionUpdate(BaseModel):
    """Fields editable by an administrator on an existing SCIM connection."""

    expected_external_directory_id: str | None
    external_directory_id: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    keycloak_admin_base_url: AnyHttpUrl | None = None
    keycloak_admin_realm: str = Field(default="master", min_length=1, max_length=255)
    keycloak_admin_username: SecretStr | None = None
    keycloak_admin_password: SecretStr | None = None


class SCIMConnectionListItem(BaseModel):
    """Non-secret SCIM connection information returned in listings."""

    id: int
    provider_type: str
    external_directory_id: Optional[str] = None
    connection_key: str
    display_name: str
    auth_mode: str
    client_id: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SCIMConnectionDetail(SCIMConnectionListItem):
    """Non-secret details for one SCIM connection."""


class SCIMConnectionCredentialResponse(SCIMConnectionDetail):
    """Connection details with a newly generated bearer token.

    ``bearer_token`` is populated only by create and rotate operations.
    """

    bearer_token: str


class SCIMConnectionStatusResponse(SCIMConnectionDetail):
    """Connection details returned after an activation change."""


class OIDCIdentityLinkCreate(BaseModel):
    """Administrator-supplied proof of the intended OIDC-to-SCIM association."""

    user_id: int = Field(gt=0)
    issuer: str = Field(min_length=1, max_length=1024)
    subject: str = Field(min_length=1, max_length=512)
    external_id: str = Field(min_length=1, max_length=255)


class OIDCIdentityLinkResponse(BaseModel):
    """Details of an explicit identity link, excluding credentials."""

    id: int
    user_id: int
    connection_id: int
    issuer: str
    subject: str
    external_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
