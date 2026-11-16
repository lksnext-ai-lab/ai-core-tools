from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


SCIM_CORE_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0"
SCIM_SCHEMA_SCHEMA = f"{SCIM_CORE_SCHEMA}:Schema"
SCIM_LIST_RESPONSE_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
SCIM_ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"


class SCIMPatchCapability(BaseModel):
    """SCIM PATCH capability advertisement."""

    supported: bool


class SCIMBulkCapability(BaseModel):
    """SCIM Bulk capability advertisement."""

    supported: bool
    maxOperations: int = 0
    maxPayloadSize: int = 0


class SCIMServiceProviderConfig(BaseModel):
    """Capabilities exposed by this SCIM service."""

    schemas: list[str] = [f"{SCIM_CORE_SCHEMA}:ServiceProviderConfig"]
    patch: SCIMPatchCapability
    bulk: SCIMBulkCapability
    filter: dict[str, Any]
    changePassword: dict[str, bool]
    sort: dict[str, bool]
    etag: dict[str, bool]
    authenticationSchemes: list[dict[str, Any]]

    model_config = ConfigDict(populate_by_name=True)


class SCIMResourceType(BaseModel):
    """A SCIM resource type advertised by the service."""

    schemas: list[str] = ["urn:ietf:params:scim:schemas:core:2.0:ResourceType"]
    id: str
    name: str
    endpoint: str
    schema_: str = Field(alias="schema")
    description: Optional[str] = None
    meta: Optional[dict[str, str]] = None

    model_config = ConfigDict(populate_by_name=True)


class SCIMResourceTypeList(BaseModel):
    """SCIM list response containing resource types."""

    schemas: list[str] = [SCIM_LIST_RESPONSE_SCHEMA]
    totalResults: int
    startIndex: int = 1
    itemsPerPage: int
    Resources: list[SCIMResourceType] = Field(default_factory=list)


class SCIMSchemaAttribute(BaseModel):
    """A SCIM schema attribute definition."""

    name: str
    type: str
    multiValued: bool = False
    description: Optional[str] = None
    required: bool = False
    caseExact: bool = False
    mutability: str = "readWrite"
    returned: str = "default"
    uniqueness: str = "none"
    subAttributes: Optional[list["SCIMSchemaAttribute"]] = None


class SCIMSchemaResource(BaseModel):
    """A SCIM schema definition."""

    schemas: list[str] = [SCIM_SCHEMA_SCHEMA]
    id: str
    name: str
    description: str
    attributes: list[SCIMSchemaAttribute]


class SCIMSchemaList(BaseModel):
    """SCIM list response containing schema definitions."""

    schemas: list[str] = [SCIM_LIST_RESPONSE_SCHEMA]
    totalResults: int
    startIndex: int = 1
    itemsPerPage: int
    Resources: list[SCIMSchemaResource] = Field(default_factory=list)


class SCIMErrorResponse(BaseModel):
    """SCIM protocol error body."""

    schemas: list[str] = [SCIM_ERROR_SCHEMA]
    detail: str
    status: str


class SCIMEmail(BaseModel):
    """An email value in a SCIM User resource."""

    value: str
    type: Optional[str] = None
    primary: Optional[bool] = None


class SCIMName(BaseModel):
    """The supported SCIM name attributes."""

    givenName: Optional[str] = None
    familyName: Optional[str] = None
    formatted: Optional[str] = None


class SCIMUserCreate(BaseModel):
    """SCIM User attributes accepted when creating a resource."""

    schemas: list[str] = Field(default_factory=lambda: [f"{SCIM_CORE_SCHEMA}:User"])
    externalId: str
    userName: str
    active: bool = True
    displayName: Optional[str] = None
    name: Optional[SCIMName] = None
    emails: list[SCIMEmail] = Field(default_factory=list)


class SCIMUserResponse(SCIMUserCreate):
    """SCIM User resource returned by the API."""

    id: str
    meta: dict[str, Any]

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class SCIMUserPatchOperation(BaseModel):
    """One SCIM PATCH operation."""

    op: str
    path: Optional[str] = None
    value: Any = None


class SCIMUserPatch(BaseModel):
    """SCIM PATCH request for a User."""

    schemas: list[str] = Field(default_factory=lambda: [
        "urn:ietf:params:scim:api:messages:2.0:PatchOp"
    ])
    Operations: list[SCIMUserPatchOperation]

    model_config = ConfigDict(populate_by_name=True)


class SCIMUserListResponse(BaseModel):
    """SCIM paginated User list response."""

    schemas: list[str] = Field(default_factory=lambda: [SCIM_LIST_RESPONSE_SCHEMA])
    totalResults: int
    startIndex: int
    itemsPerPage: int
    Resources: list[SCIMUserResponse] = Field(default_factory=list)


class SCIMGroupMember(BaseModel):
    """A direct User membership in a SCIM Group."""

    value: str
    display: Optional[str] = None
    type: str = "User"
    ref: Optional[str] = None


class SCIMGroupCreate(BaseModel):
    """SCIM Group attributes accepted when creating a resource."""

    schemas: list[str] = Field(default_factory=lambda: [f"{SCIM_CORE_SCHEMA}:Group"])
    externalId: str
    displayName: str
    members: list[SCIMGroupMember] = Field(default_factory=list)


class SCIMGroupResponse(SCIMGroupCreate):
    """SCIM Group resource returned by the API."""

    id: str
    meta: dict[str, Any]

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class SCIMGroupPatch(BaseModel):
    """SCIM PATCH request for a Group."""

    schemas: list[str] = Field(default_factory=lambda: [
        "urn:ietf:params:scim:api:messages:2.0:PatchOp"
    ])
    Operations: list[SCIMUserPatchOperation]

    model_config = ConfigDict(populate_by_name=True)


class SCIMGroupListResponse(BaseModel):
    """SCIM paginated Group list response."""

    schemas: list[str] = Field(default_factory=lambda: [SCIM_LIST_RESPONSE_SCHEMA])
    totalResults: int
    startIndex: int
    itemsPerPage: int
    Resources: list[SCIMGroupResponse] = Field(default_factory=list)


# Descriptive aliases used by integrations that refer to the payload as a
# request rather than a create model.
SCIMUserRequest = SCIMUserCreate
SCIMUserPATCHRequest = SCIMUserPatch
