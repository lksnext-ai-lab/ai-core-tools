from pydantic import AnyHttpUrl, BaseModel, Field, SecretStr


class KeycloakTargetSetupRequest(BaseModel):
    mattin_scim_base_url: AnyHttpUrl
    keycloak_admin_base_url: AnyHttpUrl
    keycloak_admin_realm: str = Field(default="master", min_length=1, max_length=255)
    keycloak_admin_username: SecretStr = Field(min_length=1)
    keycloak_admin_password: SecretStr = Field(min_length=1)
    bearer_token: SecretStr = Field(min_length=1)
    keycloak_realm: str = Field(min_length=1, max_length=255)
    target_name: str = Field(min_length=1, max_length=255)
    sync_groups: bool = True


class KeycloakTargetSetupResponse(BaseModel):
    target_id: str
    target_name: str
    target_url: str
    test_ok: bool
    test_status: int | None = None
    patch_supported: bool = False
    filter_supported: bool = False


class KeycloakReconciliationRequest(BaseModel):
    keycloak_admin_base_url: AnyHttpUrl
    keycloak_admin_realm: str = Field(default="master", min_length=1, max_length=255)
    keycloak_admin_username: SecretStr = Field(min_length=1)
    keycloak_admin_password: SecretStr = Field(min_length=1)
    confirm_real_reconcile: bool = False
    preview_token: str | None = None


class KeycloakReconciliationSummary(BaseModel):
    target_id: str
    dry_run: bool
    blocked: bool
    local_users: int
    remote_users: int
    user_creates: int
    user_updates: int
    user_removals: int
    unmanaged_remote_users: int
    group_upserts: int
    group_removals: int
    started_at: int
    finished_at: int
    message: str | None = None


class KeycloakReconciliationResponse(BaseModel):
    target_id: str
    dry_run: bool
    summary: KeycloakReconciliationSummary
    outbox: dict[str, int] = Field(default_factory=dict)
    preview_token: str | None = None
