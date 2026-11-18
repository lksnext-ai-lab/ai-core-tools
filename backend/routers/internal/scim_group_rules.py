"""Internal API for explicit SCIM-group-to-app access policies."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session
from fastapi.concurrency import run_in_threadpool

from db.database import get_db
from routers.internal.auth_utils import get_current_user_oauth
from schemas.group_app_access_schemas import (
    EligibleGroupsPage,
    GroupAppAccessRuleCreate,
    GroupAppAccessRuleListItem,
    GroupAppAccessRuleUpdate,
)
from services.group_app_access_service import (
    GroupAppAccessForbiddenError,
    GroupAppAccessInvalidRoleError,
    GroupAppAccessNotFoundError,
    GroupAppAccessService,
)

router = APIRouter(tags=["Apps", "SCIM group access"])


def _service(db: Session) -> GroupAppAccessService:
    return GroupAppAccessService(db)


def require_group_app_manager(
    app_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Enforce app ownership/admin collaboration at the HTTP boundary."""
    try:
        _service(db).authorize_manager(app_id, int(auth_context.identity.id))
    except GroupAppAccessForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to manage this app's group policies.",
        ) from exc


@router.get(
    "",
    response_model=list[GroupAppAccessRuleListItem],
    dependencies=[Depends(require_group_app_manager)],
)
async def list_group_rules(
    app_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> list[GroupAppAccessRuleListItem]:
    """List policy audit rows for the caller's external connection."""
    try:
        return await run_in_threadpool(
            _service(db).list_rules,
            app_id,
            int(auth_context.identity.id),
            offset,
            limit,
        )
    except GroupAppAccessForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to manage this app's group policies.",
        ) from exc
    except GroupAppAccessNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="App not found."
        ) from exc


@router.get(
    "/eligible-groups",
    response_model=EligibleGroupsPage,
    dependencies=[Depends(require_group_app_manager)],
)
async def list_eligible_groups(
    app_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> EligibleGroupsPage:
    """List active group choices from the app manager's active connection."""
    try:
        return await run_in_threadpool(
            _service(db).list_eligible_groups,
            app_id,
            int(auth_context.identity.id),
            offset,
            limit,
        )
    except GroupAppAccessForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to manage this app's group policies.",
        ) from exc
    except GroupAppAccessNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="App not found."
        ) from exc


@router.post(
    "",
    response_model=GroupAppAccessRuleListItem,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_group_app_manager)],
)
async def create_group_rule(
    app_id: int,
    payload: GroupAppAccessRuleCreate,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
) -> GroupAppAccessRuleListItem:
    """Create or reactivate one connection-scoped group policy."""
    try:
        return await run_in_threadpool(
            _service(db).create_rule,
            app_id,
            int(auth_context.identity.id),
            payload.group_id,
            payload.role,
        )
    except GroupAppAccessForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="An active linked provisioning identity is required.",
        ) from exc
    except GroupAppAccessInvalidRoleError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only VIEWER and EDITOR group roles are supported.",
        ) from exc
    except GroupAppAccessNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active group not found.",
        ) from exc


@router.patch(
    "/{rule_id}",
    response_model=GroupAppAccessRuleListItem,
    dependencies=[Depends(require_group_app_manager)],
)
async def update_group_rule(
    app_id: int,
    rule_id: int,
    payload: GroupAppAccessRuleUpdate,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
) -> GroupAppAccessRuleListItem:
    """Change a policy role or disable it without removing its audit row."""
    try:
        return await run_in_threadpool(
            _service(db).update_rule,
            app_id,
            rule_id,
            int(auth_context.identity.id),
            payload.role,
            payload.is_active,
        )
    except GroupAppAccessForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="An active linked provisioning identity is required.",
        ) from exc
    except GroupAppAccessInvalidRoleError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only VIEWER and EDITOR group roles are supported.",
        ) from exc
    except GroupAppAccessNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group access rule or active group not found.",
        ) from exc


@router.delete(
    "/{rule_id}",
    response_model=GroupAppAccessRuleListItem,
    dependencies=[Depends(require_group_app_manager)],
)
async def delete_group_rule(
    app_id: int,
    rule_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
) -> GroupAppAccessRuleListItem:
    """Disable a policy while retaining its audit row."""
    try:
        return await run_in_threadpool(
            _service(db).delete_rule, app_id, rule_id, int(auth_context.identity.id)
        )
    except GroupAppAccessForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="An active linked provisioning identity is required.",
        ) from exc
    except GroupAppAccessNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Group access rule not found."
        ) from exc
