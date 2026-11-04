from typing import Annotated, Any, AsyncGenerator, Dict, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session

from db.database import get_db
from models.hitl_approval import ApprovalChannel, HITLApproval
from routers.controls.role_authorization import AppRole, has_min_role, resolve_user_app_role
from routers.internal.auth_utils import get_current_user_oauth
from schemas.hitl_approval_schemas import (
    ApprovalDecisionsRequestSchema,
    ApprovalResultSchema,
    ApprovalStatusSchema,
)
from services import hitl_approval_service as approvals
from services.agent_execution_service import AgentExecutionService, approval_http_exception
from services.agent_streaming_service import AgentStreamingService
from tools.stream_guard import guard_agent_stream

approvals_router = APIRouter()

APPROVAL_ERROR_RESPONSES = {
    404: {"description": "Approval not found (or requested by another user)"},
    409: {"description": "`approval_already_decided`, `approval_expired` or `approval_stale`"},
    422: {"description": "`invalid_decision`: decisions do not match the approval's actions"},
}
STREAM_HEADERS = {"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}


def _requester(auth_context: AuthContext) -> approvals.Requester:
    return approvals.Requester(user_id=int(auth_context.identity.id))


def _ensure_app_access(db: Session, approval: HITLApproval, auth_context: AuthContext) -> None:
    """Playground approvals need the requester to still be a member of the app."""
    if approval.channel != ApprovalChannel.PLAYGROUND.value:
        return
    role = resolve_user_app_role(db, approval.app_id, int(auth_context.identity.id))
    if role is None or not has_min_role(role, AppRole.VIEWER):
        raise approvals.ApprovalNotFoundError("Approval not found.")


def _bearer_token(request: Request) -> Optional[str]:
    header = request.headers.get("Authorization", "")
    return header.split(" ", 1)[1] if header.startswith("Bearer ") else None


def _user_context(auth_context: AuthContext, approval: HITLApproval, request: Request) -> Dict[str, Any]:
    """Same identity the chat that paused used (playground and marketplace share this shape)."""
    return {
        "user_id": int(auth_context.identity.id),
        "email": auth_context.identity.email,
        "oauth": True,
        "app_id": approval.app_id,
        "token": _bearer_token(request),
    }


@approvals_router.get(
    "/{approval_id}",
    summary="Get an approval request",
    tags=["Human Approval"],
    response_model=ApprovalStatusSchema,
    responses={404: APPROVAL_ERROR_RESPONSES[404]},
)
async def get_approval(
    approval_id: str,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
):
    """An approval requested by the current user (only the requester can see or answer it)."""
    try:
        return approvals.status_schema(approvals.get_for_requester(db, approval_id, _requester(auth_context)))
    except approvals.ApprovalError as exc:
        raise approval_http_exception(exc) from exc


@approvals_router.post(
    "/{approval_id}/decisions/stream",
    summary="Answer an approval request and stream the rest of the turn",
    tags=["Human Approval"],
    responses=APPROVAL_ERROR_RESPONSES,
)
async def decide_approval_stream(
    approval_id: str,
    body: ApprovalDecisionsRequestSchema,
    request: Request,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
):
    """One decision per action (by ``action_id``); same SSE contract as the chat stream."""
    try:
        _ensure_app_access(db, approvals.get_for_requester(db, approval_id, _requester(auth_context)), auth_context)
        resume = approvals.prepare_resume(db, approval_id, body.decisions, _requester(auth_context))
    except approvals.ApprovalError as exc:
        raise approval_http_exception(exc) from exc

    base_generator = AgentStreamingService(db).stream_agent_chat(
        agent_id=resume.approval.agent_id,
        message="",
        user_context=_user_context(auth_context, resume.approval, request),
        conversation_id=resume.approval.conversation_id,
        db=db,
        channel=ApprovalChannel(resume.approval.channel),
        resume=resume,
    )

    async def generator() -> AsyncGenerator[str, None]:
        try:
            async for chunk in guard_agent_stream(base_generator):
                yield chunk
        finally:
            # get_db teardown runs too late for a StreamingResponse.
            db.close()

    return StreamingResponse(generator(), media_type="text/event-stream", headers=STREAM_HEADERS)


@approvals_router.post(
    "/{approval_id}/cancel",
    summary="Cancel an approval request",
    tags=["Human Approval"],
    response_model=ApprovalResultSchema,
    responses={404: APPROVAL_ERROR_RESPONSES[404], 409: APPROVAL_ERROR_RESPONSES[409]},
)
async def cancel_approval(
    approval_id: str,
    request: Request,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
):
    """Reject every pending action; the agent answers without running the tools."""
    try:
        _ensure_app_access(db, approvals.get_for_requester(db, approval_id, _requester(auth_context)), auth_context)
        resume = approvals.prepare_cancel(db, approval_id, _requester(auth_context))
    except approvals.ApprovalError as exc:
        raise approval_http_exception(exc) from exc

    result = await AgentExecutionService().resume_approval(
        db, resume, _user_context(auth_context, resume.approval, request), ApprovalChannel(resume.approval.channel)
    )
    return ApprovalResultSchema(
        status=result.get("status", "completed"),
        response=result.get("response", ""),
        conversation_id=result.get("conversation_id"),
        pending_approval=result.get("pending_approval"),
    )
