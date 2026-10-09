"""Evaluate a text with a System One agent through the public API (API key)."""
from typing import Annotated, List

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from db.database import get_db
from schemas.system_one_schemas import SystemOneResult
from services.agent_execution_service import AgentExecutionService
from utils.logger import get_logger

from .auth import create_api_key_user_context, get_api_key_auth, validate_api_key_for_app

logger = get_logger(__name__)

system_one_router = APIRouter()


@system_one_router.post(
    "/{agent_id}/evaluate",
    summary="Evaluate a text with a System One agent",
    tags=["System One"],
    response_model=SystemOneResult,
    responses={
        400: {"description": "Nothing to evaluate, an image, or an attachment whose text cannot be read"},
        401: {"description": "Missing or invalid API key"},
        404: {"description": "System One agent not found in this app"},
        422: {"description": "The System One server rejected the request"},
        503: {"description": "The System One server is unavailable or overloaded"},
    },
)
async def evaluate_system_one_agent(
    app_id: int,
    agent_id: int,
    api_key: Annotated[str, Depends(get_api_key_auth)],
    db: Annotated[Session, Depends(get_db)],
    text: Annotated[str, Form()] = "",
    files: Annotated[List[UploadFile], File()] = [],
):
    """Send ``text`` (and optional text attachments) and get one typed answer per question of the agent."""
    auth = validate_api_key_for_app(app_id, api_key, db)
    user_context = create_api_key_user_context(app_id, api_key)
    user_context["api_key_id"] = auth.key_id
    return await AgentExecutionService().execute_agent_system_one(
        agent_id, text, files, user_context, db, app_id=app_id)
