"""Internal API for explicit SCIM-group-to-app access policies."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session
from fastapi.concurrency import run_in_threadpool

from db.database import get_db
from routers.controls.role_authorization import AppRole, require_min_role
from routers.internal.auth_utils import get_current_user_oauth
from schemas.group_app_access_schemas import (
    GroupAppAccessRuleCreate,
    GroupAppAccessRuleListItem,
    GroupAppAccessRuleUpdate,
)
from services.group_app_access_service import (
    GroupAppAccessForbiddenError,
    GroupAppAccessNotFoundError,
    GroupAppAccessService,
)

router = APIRouter(tags=["Apps", "SCIM group access"])


def _service(db: Session) -> GroupAppAccessService:
    return GroupAppAccessService(db)


@router.get(
    "",
    response_model=list[GroupAppAccessRuleListItem],
    dependencies=[Depends(require_min_role(AppRole.ADMINISTRATOR))],
)
async def list_group_rules(
    app_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
) -> list[GroupAppAccessRuleListItem]:
    """List policy audit rows for the caller's external connection."""
    try:
        return await run_in_threadpool(
            _service(db).list_rules, app_id, int(auth_context.identity.id)
        )
    except GroupAppAccessForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post(
    "",
    response_model=GroupAppAccessRuleListItem,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_min_role(AppRole.ADMINISTRATOR))],
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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except GroupAppAccessNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch(
    "/{rule_id}",
    response_model=GroupAppAccessRuleListItem,
    dependencies=[Depends(require_min_role(AppRole.ADMINISTRATOR))],
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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except GroupAppAccessNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete(
    "/{rule_id}",
    response_model=GroupAppAccessRuleListItem,
    dependencies=[Depends(require_min_role(AppRole.ADMINISTRATOR))],
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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except GroupAppAccessNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
