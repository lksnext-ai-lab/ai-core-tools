"""Internal, read-only API for an authenticated user's SCIM group access."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session

from db.database import get_db
from routers.internal.auth_utils import get_current_user_oauth
from schemas.my_groups_schemas import MyGroupAppsPage, MyGroupsPage
from services.my_groups_service import MyGroupNotFoundError, MyGroupsService

router = APIRouter(tags=["My Groups"])


@router.get("/my-groups")
async def list_my_groups(
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> MyGroupsPage:
    """List only the caller's directly provisioned, currently eligible groups."""
    return await run_in_threadpool(
        MyGroupsService(db).list_groups,
        int(auth_context.identity.id),
        offset,
        limit,
    )


@router.get("/my-groups/{group_id}/apps")
async def list_my_group_apps(
    group_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> MyGroupAppsPage:
    """List app policies contributed by one of the caller's eligible groups."""
    try:
        return await run_in_threadpool(
            MyGroupsService(db).list_group_apps,
            int(auth_context.identity.id),
            group_id,
            offset,
            limit,
        )
    except MyGroupNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found.",
        ) from exc
