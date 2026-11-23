from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from db.database import get_db
from models.provisioning_connection import ProvisioningConnection
from schemas.scim_schemas import (
    SCIMBulkCapability,
    SCIMResourceType,
    SCIMResourceTypeList,
    SCIMSchemaAttribute,
    SCIMSchemaList,
    SCIMSchemaResource,
    SCIMServiceProviderConfig,
    SCIMPatchCapability,
    SCIMUserCreate,
    SCIMUserListResponse,
    SCIMUserPatch,
    SCIMUserResponse,
    SCIMGroupCreate,
    SCIMGroupListResponse,
    SCIMGroupPatch,
    SCIMGroupResponse,
)
from services.scim_service import SCIMRequestError, scim_service

_SCIM_MEDIA_TYPE = "application/scim+json"


class SCIMJSONResponse(JSONResponse):
    """JSON response using the SCIM media type."""

    media_type = _SCIM_MEDIA_TYPE


router = APIRouter()


async def authenticate_scim(
    connection_key: str,
    authorization: Annotated[Optional[str], Header()] = None,
    db: Session = Depends(get_db),
) -> ProvisioningConnection:
    """Authenticate and resolve the connection in the request URL."""
    return await scim_service.authenticate(db, connection_key, authorization)


def _scim_error(error: SCIMRequestError) -> JSONResponse:
    """Build a SCIM-compliant error response."""
    return JSONResponse(
        status_code=error.status_code,
        content={
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"],
            "detail": error.detail,
            "status": str(error.status_code),
        },
        media_type=_SCIM_MEDIA_TYPE,
    )


@router.get(
    "/{connection_key}/ServiceProviderConfig",
    response_class=SCIMJSONResponse,
    tags=["SCIM"],
)
async def get_service_provider_config(
    connection: Annotated[ProvisioningConnection, Depends(authenticate_scim)],
) -> SCIMServiceProviderConfig:
    """Return the implemented SCIM capability profile."""
    return SCIMServiceProviderConfig(
        patch=SCIMPatchCapability(supported=True),
        bulk=SCIMBulkCapability(supported=False),
        filter={"supported": True},
        changePassword={"supported": False},
        sort={"supported": False},
        etag={"supported": False},
        authenticationSchemes=[{
            "type": "oauthbearertoken",
            "name": "Static bearer token",
            "description": "Connection-scoped bearer token.",
            "specUri": "https://www.rfc-editor.org/rfc/rfc6750",
            "primary": True,
        }],
    )


@router.get(
    "/{connection_key}/ResourceTypes",
    response_class=SCIMJSONResponse,
    tags=["SCIM"],
)
async def get_resource_types(
    connection: Annotated[ProvisioningConnection, Depends(authenticate_scim)],
) -> SCIMResourceTypeList:
    """Advertise the implemented User and Group resource types."""
    resources = [
        SCIMResourceType(
            id="User",
            name="User",
            endpoint="/Users",
            schema="urn:ietf:params:scim:schemas:core:2.0:User",
        ),
        SCIMResourceType(
            id="Group",
            name="Group",
            endpoint="/Groups",
            schema="urn:ietf:params:scim:schemas:core:2.0:Group",
        ),
    ]
    return SCIMResourceTypeList(totalResults=len(resources), itemsPerPage=len(resources), Resources=resources)


@router.get(
    "/{connection_key}/Schemas",
    response_class=SCIMJSONResponse,
    tags=["SCIM"],
)
async def get_schemas(
    connection: Annotated[ProvisioningConnection, Depends(authenticate_scim)],
) -> SCIMSchemaList:
    """Advertise the core User and Group schemas used by this profile."""
    resources = [
        SCIMSchemaResource(
            id="urn:ietf:params:scim:schemas:core:2.0:User",
            name="User",
            description="SCIM User resource.",
            attributes=[
                SCIMSchemaAttribute(name="userName", type="string", required=True, caseExact=False),
                SCIMSchemaAttribute(name="externalId", type="string"),
                SCIMSchemaAttribute(name="displayName", type="string"),
                SCIMSchemaAttribute(name="active", type="boolean"),
                SCIMSchemaAttribute(name="emails", type="complex", multiValued=True),
            ],
        ),
        SCIMSchemaResource(
            id="urn:ietf:params:scim:schemas:core:2.0:Group",
            name="Group",
            description="SCIM Group resource.",
            attributes=[
                SCIMSchemaAttribute(name="externalId", type="string"),
                SCIMSchemaAttribute(name="displayName", type="string", required=True),
                SCIMSchemaAttribute(
                    name="members", type="complex", multiValued=True,
                    subAttributes=[
                        SCIMSchemaAttribute(name="value", type="string", required=True),
                        SCIMSchemaAttribute(name="display", type="string"),
                        SCIMSchemaAttribute(name="type", type="string"),
                        SCIMSchemaAttribute(name="$ref", type="reference"),
                    ],
                ),
            ],
        ),
    ]
    return SCIMSchemaList(totalResults=len(resources), itemsPerPage=len(resources), Resources=resources)


@router.post(
    "/{connection_key}/Users",
    response_model=SCIMUserResponse,
    response_class=SCIMJSONResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["SCIM"],
)
async def create_user(
    payload: SCIMUserCreate,
    connection: Annotated[ProvisioningConnection, Depends(authenticate_scim)],
    db: Annotated[Session, Depends(get_db)],
) -> SCIMUserResponse | JSONResponse:
    """Create or reconcile a provisioned SCIM user."""
    try:
        resource, _ = scim_service.upsert_user(db, connection, payload)
        return resource
    except SCIMRequestError as error:
        return _scim_error(error)


@router.get(
    "/{connection_key}/Users",
    response_model=SCIMUserListResponse,
    response_class=SCIMJSONResponse,
    tags=["SCIM"],
)
async def list_users(
    connection: Annotated[ProvisioningConnection, Depends(authenticate_scim)],
    db: Annotated[Session, Depends(get_db)],
    start_index: Annotated[int, Query(alias="startIndex", ge=1)] = 1,
    count: Annotated[int, Query(ge=0, le=1000)] = 100,
    filter_expression: Annotated[Optional[str], Query(alias="filter")] = None,
) -> SCIMUserListResponse | JSONResponse:
    """List connection-scoped SCIM users."""
    try:
        resources, total = scim_service.list_users(
            db, connection, start_index, count, filter_expression
        )
        return SCIMUserListResponse(
            totalResults=total,
            startIndex=start_index,
            itemsPerPage=len(resources),
            Resources=resources,
        )
    except SCIMRequestError as error:
        return _scim_error(error)


@router.get(
    "/{connection_key}/Users/{scim_id}",
    response_model=SCIMUserResponse,
    response_class=SCIMJSONResponse,
    tags=["SCIM"],
)
async def get_user(
    scim_id: str,
    connection: Annotated[ProvisioningConnection, Depends(authenticate_scim)],
    db: Annotated[Session, Depends(get_db)],
) -> SCIMUserResponse | JSONResponse:
    """Retrieve a connection-scoped SCIM user."""
    try:
        return scim_service.get_user(db, connection, scim_id)
    except SCIMRequestError as error:
        return _scim_error(error)


@router.patch(
    "/{connection_key}/Users/{scim_id}",
    response_model=SCIMUserResponse,
    response_class=SCIMJSONResponse,
    tags=["SCIM"],
)
async def patch_user(
    patch: SCIMUserPatch,
    scim_id: str,
    connection: Annotated[ProvisioningConnection, Depends(authenticate_scim)],
    db: Annotated[Session, Depends(get_db)],
) -> SCIMUserResponse | JSONResponse:
    """Patch supported attributes of a connection-scoped SCIM user."""
    try:
        return scim_service.patch_user(db, connection, scim_id, patch)
    except SCIMRequestError as error:
        return _scim_error(error)


@router.delete(
    "/{connection_key}/Users/{scim_id}",
    response_model=None,
    response_class=SCIMJSONResponse,
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["SCIM"],
)
async def delete_user(
    scim_id: str,
    connection: Annotated[ProvisioningConnection, Depends(authenticate_scim)],
    db: Annotated[Session, Depends(get_db)],
) -> Response | JSONResponse:
    """Deprovision a user without deleting local records."""
    try:
        scim_service.delete_user(db, connection, scim_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT, media_type=_SCIM_MEDIA_TYPE)
    except SCIMRequestError as error:
        return _scim_error(error)


@router.post(
    "/{connection_key}/Groups",
    response_model=SCIMGroupResponse,
    response_class=SCIMJSONResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["SCIM"],
)
async def create_group(
    payload: SCIMGroupCreate,
    connection: Annotated[ProvisioningConnection, Depends(authenticate_scim)],
    db: Annotated[Session, Depends(get_db)],
) -> SCIMGroupResponse | JSONResponse:
    """Create or reconcile a connection-scoped SCIM Group."""
    try:
        resource, _ = scim_service.upsert_group(db, connection, payload)
        return resource
    except SCIMRequestError as error:
        return _scim_error(error)


@router.get(
    "/{connection_key}/Groups",
    response_model=SCIMGroupListResponse,
    response_class=SCIMJSONResponse,
    tags=["SCIM"],
)
async def list_groups(
    connection: Annotated[ProvisioningConnection, Depends(authenticate_scim)],
    db: Annotated[Session, Depends(get_db)],
    start_index: Annotated[int, Query(alias="startIndex", ge=1)] = 1,
    count: Annotated[int, Query(ge=0, le=1000)] = 100,
    filter_expression: Annotated[Optional[str], Query(alias="filter")] = None,
) -> SCIMGroupListResponse | JSONResponse:
    """List connection-scoped SCIM Groups."""
    try:
        resources, total = scim_service.list_groups(
            db, connection, start_index, count, filter_expression
        )
        return SCIMGroupListResponse(
            totalResults=total, startIndex=start_index,
            itemsPerPage=len(resources), Resources=resources,
        )
    except SCIMRequestError as error:
        return _scim_error(error)


@router.get(
    "/{connection_key}/Groups/{scim_id}",
    response_model=SCIMGroupResponse,
    response_class=SCIMJSONResponse,
    tags=["SCIM"],
)
async def get_group(
    scim_id: str,
    connection: Annotated[ProvisioningConnection, Depends(authenticate_scim)],
    db: Annotated[Session, Depends(get_db)],
) -> SCIMGroupResponse | JSONResponse:
    """Retrieve a connection-scoped SCIM Group."""
    try:
        return scim_service.get_group(db, connection, scim_id)
    except SCIMRequestError as error:
        return _scim_error(error)


@router.patch(
    "/{connection_key}/Groups/{scim_id}",
    response_model=SCIMGroupResponse,
    response_class=SCIMJSONResponse,
    tags=["SCIM"],
)
async def patch_group(
    patch: SCIMGroupPatch,
    scim_id: str,
    connection: Annotated[ProvisioningConnection, Depends(authenticate_scim)],
    db: Annotated[Session, Depends(get_db)],
) -> SCIMGroupResponse | JSONResponse:
    """Patch displayName and direct memberships of a Group."""
    try:
        return scim_service.patch_group(db, connection, scim_id, patch)
    except SCIMRequestError as error:
        return _scim_error(error)


@router.delete(
    "/{connection_key}/Groups/{scim_id}",
    response_model=None,
    response_class=SCIMJSONResponse,
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["SCIM"],
)
async def delete_group(
    scim_id: str,
    connection: Annotated[ProvisioningConnection, Depends(authenticate_scim)],
    db: Annotated[Session, Depends(get_db)],
) -> Response | JSONResponse:
    """Deactivate a Group without deleting local users."""
    try:
        scim_service.delete_group(db, connection, scim_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT, media_type=_SCIM_MEDIA_TYPE)
    except SCIMRequestError as error:
        return _scim_error(error)
