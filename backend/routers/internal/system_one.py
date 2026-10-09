"""Evaluate a text with a System One agent from the playground. Mounted under /{app_id}/system-one."""
from typing import Annotated, List

from fastapi import APIRouter, Depends, File, Form, UploadFile
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session

from db.database import get_db
from routers.controls.role_authorization import AppRole, require_min_role
from schemas.system_one_schemas import SystemOneResult
from services.agent_execution_service import AgentExecutionService
from utils.logger import get_logger

from .auth_utils import get_current_user_oauth

logger = get_logger(__name__)

system_one_router = APIRouter()


@system_one_router.post(
    "/{agent_id}/evaluate",
    summary="Evaluate a text with a System One agent",
    tags=["System One"],
    response_model=SystemOneResult,
    responses={
        400: {"description": "Nothing to evaluate, an image, or an attachment whose text cannot be read"},
        404: {"description": "System One agent not found in this app"},
        422: {"description": "The System One server rejected the request"},
        503: {"description": "The System One server is unavailable or overloaded"},
    },
)
async def evaluate_system_one_agent(
    app_id: int,
    agent_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
    db: Annotated[Session, Depends(get_db)],
    text: Annotated[str, Form()] = "",
    files: Annotated[List[UploadFile], File()] = [],
):
    user_context = {"user_id": int(auth_context.identity.id), "app_id": app_id, "oauth": True}
    return await AgentExecutionService().execute_agent_system_one(
        agent_id, text, files, user_context, db, app_id=app_id)
