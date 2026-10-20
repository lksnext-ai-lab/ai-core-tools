from typing import Annotated, AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from db.database import get_db
from models.hitl_approval import ApprovalChannel
from schemas.hitl_approval_schemas import ApprovalDecisionsRequestSchema, ApprovalStatusSchema
from services import hitl_approval_service as approvals
from services.agent_execution_service import AgentExecutionService, approval_http_exception
from services.agent_streaming_service import AgentStreamingService
from tools.stream_guard import guard_agent_stream
from utils.logger import get_logger

from .auth import create_api_key_user_context, get_api_key_auth, validate_api_key_for_app
from .schemas import AgentResponseSchema

logger = get_logger(__name__)

approvals_router = APIRouter()

APPROVAL_ERROR_RESPONSES = {
    404: {"description": "Approval not found (or created with another API key)"},
    409: {
        "description": "Approval cannot be answered: `approval_already_decided`, `approval_expired` or `approval_stale`",
        "content": {"application/json": {"example": {
            "detail": {"code": "approval_expired", "message": "This approval request has expired; the tool was not executed."}
        }}},
    },
    422: {"description": "`invalid_decision`: decisions do not match the approval's actions"},
}
STREAM_HEADERS = {"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}


@approvals_router.get(
    "/{approval_id}",
    summary="Get an approval request",
    tags=["Human Approval"],
    response_model=ApprovalStatusSchema,
    responses={404: APPROVAL_ERROR_RESPONSES[404]},
)
async def get_approval(
    app_id: int,
    approval_id: str,
    api_key: Annotated[str, Depends(get_api_key_auth)],
    db: Annotated[Session, Depends(get_db)],
):
    """Status of an approval created by this API key: pending actions, expiry and outcome.

    A pending approval past ``expires_at`` is reported as ``expired``; the server rejects it
    (the tool is never executed) and the conversation receives the agent's final answer.
    """
    validate_api_key_for_app(app_id, api_key, db)
    requester = approvals.Requester.from_user_context(create_api_key_user_context(app_id, api_key))
    try:
        return approvals.status_schema(approvals.get_for_requester(db, approval_id, requester, app_id))
    except approvals.ApprovalError as exc:
        raise approval_http_exception(exc) from exc


@approvals_router.post(
    "/{approval_id}/decisions",
    summary="Answer an approval request",
    tags=["Human Approval"],
    response_model=AgentResponseSchema,
    responses=APPROVAL_ERROR_RESPONSES,
)
async def decide_approval(
    app_id: int,
    approval_id: str,
    body: ApprovalDecisionsRequestSchema,
    api_key: Annotated[str, Depends(get_api_key_auth)],
    db: Annotated[Session, Depends(get_db)],
):
    """Approve, edit or reject every pending action and run the rest of the agent turn.

    Send exactly one decision per action, addressed by ``action_id``. ``edit`` replaces the
    tool arguments (``args``); ``reject`` may include a ``message`` for the agent. The answer
    has the same shape as ``/chat/{agent_id}/call`` and may be ``requires_approval`` again if
    the agent asks for another tool that needs approval. Each approval can be answered once.
    """
    validate_api_key_for_app(app_id, api_key, db)
    user_context = create_api_key_user_context(app_id, api_key)
    requester = approvals.Requester.from_user_context(user_context)
    try:
        resume = approvals.prepare_resume(db, approval_id, body.decisions, requester, app_id)
    except approvals.ApprovalError as exc:
        raise approval_http_exception(exc) from exc

    result = await AgentExecutionService().resume_approval(db, resume, user_context, ApprovalChannel.PUBLIC_API)
    return AgentResponseSchema(
        status=result.get("status", "completed"),
        response=result["response"],
        conversation_id=result.get("conversation_id"),
        usage=result["metadata"],
        pending_approval=result.get("pending_approval"),
    )


@approvals_router.post(
    "/{approval_id}/decisions/stream",
    summary="Answer an approval request (streaming)",
    tags=["Human Approval"],
    responses=APPROVAL_ERROR_RESPONSES,
)
async def decide_approval_stream(
    app_id: int,
    approval_id: str,
    body: ApprovalDecisionsRequestSchema,
    api_key: Annotated[str, Depends(get_api_key_auth)],
    db: Annotated[Session, Depends(get_db)],
):
    """Same as ``/decisions`` but streams the rest of the turn with the ``/call/stream`` SSE contract."""
    validate_api_key_for_app(app_id, api_key, db)
    user_context = create_api_key_user_context(app_id, api_key)
    requester = approvals.Requester.from_user_context(user_context)
    try:
        resume = approvals.prepare_resume(db, approval_id, body.decisions, requester, app_id)
    except approvals.ApprovalError as exc:
        raise approval_http_exception(exc) from exc

    base_generator = AgentStreamingService(db).stream_agent_chat(
        agent_id=resume.approval.agent_id,
        message="",
        user_context=user_context,
        conversation_id=resume.approval.conversation_id,
        db=db,
        channel=ApprovalChannel.PUBLIC_API,
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
