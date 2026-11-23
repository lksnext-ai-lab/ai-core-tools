"""Internal API of the flexible per-App Chat.

Mounted by ``routers/internal/apps.py`` under ``/internal/apps/{app_id}/chat``. HTTP only: every use case lives
in ``InternalChatService`` and every endpoint requires at least the ``viewer`` role of the App (the dependency
runs before anything else). There is deliberately no equivalent under ``/public/v1``, ``/mcp/v1`` or ``/a2a``.

Error mapping (done once, by ``_ChatRoute``): ``NotFoundError`` (the Chat's single "Resource not found"),
``ValidationError`` and ``ConflictError`` become their HTTP status; ``ServiceRetiredError`` is mapped to 409
``SERVICE_RETIRED`` by the global handler; a frozen App raises ``HTTPException(403)`` from the service.

Turns (``/stream`` and ``/messages``) call ``prepare_turn`` BEFORE any response exists, so 403/404/409/422 are
real HTTP errors. Without ``conversation_id`` a turn creates the conversation (its id comes back in the ``metadata`` event / the sync
response); a given id must be one of the caller's.
"""
import contextlib
import json
from typing import Annotated, Any, AsyncGenerator, Awaitable, Callable, Coroutine, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.routing import APIRoute
from lks_idprovider import AuthContext
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from db.database import get_db
from models.hitl_approval import ApprovalChannel
from routers.controls.file_size_limit import enforce_file_size_limit
from routers.controls.role_authorization import AppRole, require_min_role
from routers.internal.auth_utils import get_current_user_oauth
from schemas.chat_schemas import ResetResponseSchema
from schemas.internal_chat_schemas import (
    ChatConversationCreate,
    ChatConversationDetailResponse,
    ChatConversationListResponse,
    ChatConversationRename,
    ChatConversationResponse,
    ChatFileDownloadResponse,
    ChatFileListResponse,
    ChatFileUploadResponse,
    ChatHistoryMessage,
    ChatMessageResponse,
    ChatOptionsResponse,
    ChatSelection,
)
from services.agent_execution_service import AgentExecutionService
from services.agent_streaming_service import AgentStreamingService
from services.file_management_service import FileManagementService
from services.internal_chat.chat_service import InternalChatService
from services.internal_chat.errors import ChatStepLimitError, ChatTooManyFilesError
from tools.stream_guard import guard_agent_stream
from utils.error_handlers import ConflictError, NotFoundError
from utils.error_handlers import ValidationError as AppValidationError
from utils.logger import get_logger

logger = get_logger(__name__)

MAX_PAGE_SIZE = 100
INVALID_SELECTION_MESSAGE = "Invalid selection"


class _ClaimReleasingStreamingResponse(StreamingResponse):
    """``StreamingResponse`` that always runs ``on_finish`` when the response ends, started or not.

    A generator that never started (the client left before the first chunk, the server failed on response start)
    never runs its own ``finally``, so the busy marker of the turn would stay set for the whole TTL. The ASGI call
    is the one place that always runs, so the release is also tied to it. ``on_finish`` must be idempotent (the
    generator's ``finally`` calls it too) and releases the claim synchronously before anything else.
    """

    def __init__(self, *args: Any, on_finish: Callable[[], Awaitable[None]], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._on_finish = on_finish

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self._on_finish()


class _ChatRoute(APIRoute):
    """Map the application errors the Chat services raise to HTTP, once, for every route of this router."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def mapped(request: Request) -> Response:
            try:
                return await handler(request)
            except (NotFoundError, AppValidationError, ConflictError, ChatStepLimitError, ChatTooManyFilesError) as exc:
                # Same body shape as the global ``ServiceRetiredError`` handler in ``main.py``
                # (``detail`` + ``error_code``), so clients parse every Chat error alike.
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.message, "error_code": exc.error_code},
                    headers=getattr(exc, "headers", None),  # e.g. Retry-After of CONVERSATION_BUSY
                )

        return mapped


internal_chat_router = APIRouter(route_class=_ChatRoute)

ViewerRole = Annotated[AppRole, Depends(require_min_role("viewer"))]
AuthDep = Annotated[AuthContext, Depends(get_current_user_oauth)]
DbDep = Annotated[Session, Depends(get_db)]
FileSizeGuard = Annotated[None, Depends(enforce_file_size_limit)]


def _enforce_file_cap(files: Optional[List[UploadFile]], file_references: Optional[List[str]]) -> None:
    """422 when one message carries more files (new uploads + references) than ``CHAT_MAX_FILES_PER_TURN``."""
    import config as settings

    limit = int(getattr(settings, "CHAT_MAX_FILES_PER_TURN", 10) or 0)
    if limit and len(files or []) + len(file_references or []) > limit:
        raise ChatTooManyFilesError(limit)


def _jwt_token(request: Request) -> Optional[str]:
    parts = request.headers.get("Authorization", "").split(" ")
    return parts[1] if len(parts) > 1 and parts[0] == "Bearer" else None


def _service(db: Session, auth_context: AuthContext, app_id: int, request: Optional[Request] = None) -> InternalChatService:
    """One service per request, on the request's own session (the execution stack must use the same one)."""
    user_context = {
        "user_id": int(auth_context.identity.id),
        "email": auth_context.identity.email,
        "app_id": app_id,
        "oauth": True,
        "token": _jwt_token(request) if request is not None else None,
    }
    return InternalChatService(db, user_context)


def _parse_file_references(value: Optional[str]) -> Optional[list]:
    """Optional JSON array of file ids. Malformed input is a 422: ignoring it would attach EVERY stored file."""
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Invalid file_references") from exc
    if not isinstance(parsed, list):
        raise HTTPException(status_code=422, detail="Invalid file_references")
    return parsed


def _parse_search_params(value: Optional[str]) -> Optional[dict]:
    """Optional JSON object of silo search parameters; anything else is a 422."""
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Invalid search_params") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail="Invalid search_params")
    return parsed


def _sse_event_type(chunk: str) -> Optional[str]:
    """``type`` of one SSE chunk (``data: {"type": ...}``); None for heartbeats and anything else."""
    if not chunk.startswith("data: "):
        return None
    try:
        payload = json.loads(chunk[len("data: "):])
    except ValueError:
        return None
    return payload.get("type") if isinstance(payload, dict) else None


def _parse_selection(raw: str) -> ChatSelection:
    """``selection`` form field -> ``ChatSelection`` (422 on bad JSON or shape; the input is never echoed)."""
    try:
        return ChatSelection.model_validate_json(raw)
    except PydanticValidationError as exc:
        raise HTTPException(status_code=422, detail=INVALID_SELECTION_MESSAGE) from exc


# ------------------------------------------------------------------ options and defaults


@internal_chat_router.get(
    "/options",
    response_model=ChatOptionsResponse,
    summary="Models, knowledge sources, skills and MCP configs the caller can pick",
    responses={403: {"description": "No access to the App, or the App is frozen"}},
)
async def get_options(app_id: int, auth_context: AuthDep, role: ViewerRole, db: DbDep):
    return _service(db, auth_context, app_id).get_options(app_id)


@internal_chat_router.get(
    "/defaults",
    response_model=Optional[ChatSelection],
    summary="The caller's default selection (null when the App has no usable model)",
    responses={403: {"description": "No access to the App, or the App is frozen"}},
)
async def get_defaults(app_id: int, auth_context: AuthDep, role: ViewerRole, db: DbDep):
    return _service(db, auth_context, app_id).get_defaults(app_id)


@internal_chat_router.put(
    "/defaults",
    response_model=ChatSelection,
    summary="Pin the caller's default selection",
    responses={
        403: {"description": "No access to the App, or the App is frozen"},
        404: {"description": "Resource not found"},
        409: {"description": "A service used by the selection was retired"},
    },
)
async def put_defaults(app_id: int, selection: ChatSelection, auth_context: AuthDep, role: ViewerRole, db: DbDep):
    return _service(db, auth_context, app_id).set_defaults(app_id, selection)


# ------------------------------------------------------------------ conversations


@internal_chat_router.get(
    "/conversations",
    response_model=ChatConversationListResponse,
    summary="The caller's Chat conversations (newest first)",
)
async def list_conversations(
    app_id: int,
    auth_context: AuthDep,
    role: ViewerRole,
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    conversations, total = _service(db, auth_context, app_id).list_conversations(app_id, limit=limit, offset=offset)
    return ChatConversationListResponse(
        conversations=[ChatConversationResponse.model_validate(c) for c in conversations], total=total
    )


@internal_chat_router.post(
    "/conversations",
    response_model=ChatConversationResponse,
    summary="Create a Chat conversation",
    responses={
        403: {"description": "No access to the App, or the App is frozen"},
        404: {"description": "Resource not found (invalid selection)"},
        409: {"description": "A service used by the selection was retired"},
    },
)
async def create_conversation(
    app_id: int, data: ChatConversationCreate, auth_context: AuthDep, role: ViewerRole, db: DbDep
):
    conversation, selection = _service(db, auth_context, app_id).create_conversation(
        app_id, selection=data.selection, title=data.title
    )
    response = ChatConversationResponse.model_validate(conversation)
    response.selection = selection
    return response


@internal_chat_router.get(
    "/conversations/{conversation_id}",
    response_model=ChatConversationDetailResponse,
    summary="A Chat conversation with its history and current selection",
    responses={404: {"description": "Conversation not found"}},
)
async def get_conversation(app_id: int, conversation_id: int, auth_context: AuthDep, role: ViewerRole, db: DbDep):
    detail = await _service(db, auth_context, app_id).get_conversation_detail(app_id, conversation_id)
    base = ChatConversationResponse.model_validate(detail.conversation)
    return ChatConversationDetailResponse(
        **base.model_dump(),
        messages=[ChatHistoryMessage.model_validate(m) for m in detail.messages],
        current_selection=detail.current_selection,
        warnings=detail.warnings,
        pending_approval=detail.pending_approval,
    )


@internal_chat_router.patch(
    "/conversations/{conversation_id}",
    response_model=ChatConversationResponse,
    summary="Rename a Chat conversation",
    responses={404: {"description": "Conversation not found"}},
)
async def rename_conversation(
    app_id: int,
    conversation_id: int,
    data: ChatConversationRename,
    auth_context: AuthDep,
    role: ViewerRole,
    db: DbDep,
):
    conversation = _service(db, auth_context, app_id).rename_conversation(app_id, conversation_id, data.title)
    return ChatConversationResponse.model_validate(conversation)


@internal_chat_router.delete(
    "/conversations/{conversation_id}",
    status_code=204,
    summary="Delete a Chat conversation",
    responses={404: {"description": "Conversation not found"}},
)
async def delete_conversation(app_id: int, conversation_id: int, auth_context: AuthDep, role: ViewerRole, db: DbDep):
    await _service(db, auth_context, app_id).delete_conversation(app_id, conversation_id)
    return Response(status_code=204)


@internal_chat_router.post(
    "/conversations/{conversation_id}/reset",
    response_model=ResetResponseSchema,
    summary="Forget the history of a Chat conversation (the selection is kept)",
    responses={404: {"description": "Conversation not found"}},
)
async def reset_conversation(app_id: int, conversation_id: int, auth_context: AuthDep, role: ViewerRole, db: DbDep):
    await _service(db, auth_context, app_id).reset_conversation(app_id, conversation_id)
    return ResetResponseSchema(success=True, message="Conversation reset successfully")


# ------------------------------------------------------------------ turns


@internal_chat_router.post(
    "/stream",
    summary="Send a message (Server-Sent Events)",
    responses={
        200: {"content": {"text/event-stream": {}}, "description": "SSE: metadata, token, tool_*, done, error"},
        403: {"description": "No access to the App, or the App is frozen"},
        404: {"description": "Conversation or selected resource not found"},
        409: {"description": "A service used by the turn was retired, or CONVERSATION_BUSY (Retry-After)"},
        422: {"description": "Invalid selection, file_references or search_params"},
    },
)
async def chat_stream(
    app_id: int,
    request: Request,
    message: Annotated[str, Form()],
    selection: Annotated[str, Form()],
    auth_context: AuthDep,
    role: ViewerRole,
    db: DbDep,
    _: FileSizeGuard,
    conversation_id: Annotated[Optional[int], Form()] = None,
    files: Annotated[Optional[List[UploadFile]], File()] = None,
    file_references: Annotated[Optional[str], Form()] = None,
    search_params: Annotated[Optional[str], Form()] = None,
):
    chat_selection = _parse_selection(selection)
    parsed_file_references = _parse_file_references(file_references)
    parsed_search_params = _parse_search_params(search_params)
    _enforce_file_cap(files, parsed_file_references)
    service = _service(db, auth_context, app_id, request)
    prepared = service.prepare_turn(app_id, chat_selection, conversation_id)
    turn_conversation_id = prepared.conversation_id  # plain value (the ORM conversation expires on commit)

    # From here on the turn owns a claim on its conversation. ``finish`` is its ONLY release point: the failure path
    # below, the generator's ``finally`` and the response wrapper all call it, whichever runs first wins.
    fms: Optional[FileManagementService] = None
    file_refs: list = []
    finished = False

    async def finish(close_session: bool = True) -> None:
        nonlocal finished
        # FIRST statement, synchronous (a cancelled / aclose()d task must not await before it): give the
        # conversation back, whatever ended the turn. Idempotent; it also retries a release that failed before.
        service.release_turn(prepared.claim)
        if finished:
            return
        finished = True
        # Release the request DB session: get_db teardown runs too late for a StreamingResponse.
        if close_session:
            db.close()
        if fms is not None:
            await fms.cleanup_ephemeral_refs(file_refs)

    try:
        fms = FileManagementService()
        file_refs = await fms.resolve_chat_files(
            files=files,
            file_reference_ids=parsed_file_references,
            agent_id=prepared.agent_id,
            user_context=prepared.user_context,
            conversation_id=turn_conversation_id,
            has_memory=True,
        )
        base_generator = AgentStreamingService(db).stream_agent_chat(
            agent_id=prepared.agent_id,
            message=message,
            file_references=file_refs,
            search_params=parsed_search_params,
            user_context=prepared.user_context,
            conversation_id=turn_conversation_id,
            db=db,
            channel=ApprovalChannel.INTERNAL_CHAT,
            turn_config=prepared.turn_config,
            on_turn_completed=prepared.on_turn_completed,
        )
    except BaseException:
        # No response will exist: release, clean up (the session stays open for the discard; ``get_db`` closes it).
        await finish(close_session=False)
        await service.discard_created_conversation(app_id, prepared)
        raise

    async def generator() -> AsyncGenerator[str, None]:
        completed = False
        pending_error: Optional[str] = None  # an ``error`` chunk is held back until the discard has run
        try:
            # ``aclosing`` stops the guard's producer task (the running turn) deterministically when the client
            # goes away, BEFORE the claim is released below, so a turn admitted right after cannot race the old
            # turn's last checkpoint write. If that await is itself cancelled again, the ``finally`` still releases.
            # Known residual window (documented, not closed): when the disconnect arrives as a level-triggered anyio
            # cancellation, the awaits of this cleanup re-raise at once, so ``guarded.aclose()`` has already called
            # ``producer.cancel()`` (synchronously, before its first await) but the producer may still be unwinding
            # for a few event-loop iterations when the claim is released. Awaiting it under ``anyio.CancelScope(
            # shield=True)`` would close it, at the price of a bounded stall inside a cancelled request; a turn
            # admitted in that instant can race only the cancelled turn's last checkpoint write.
            async with contextlib.aclosing(guard_agent_stream(base_generator)) as guarded:
                async for chunk in guarded:
                    event_type = _sse_event_type(chunk)
                    if event_type is None and chunk.startswith(":"):
                        yield chunk  # heartbeat: flows unchanged, the held error (if any) keeps waiting
                        continue
                    if pending_error is not None:
                        held, pending_error = pending_error, None
                        yield held  # something follows the error: it was not the end of the turn
                    if event_type == "error":
                        pending_error = chunk
                        continue
                    completed = completed or event_type == "done"
                    yield chunk
            # The stream ended by itself on an error event with no answer: the first turn of a conversation this
            # request created failed. Drop the empty conversation (it re-checks that it is still empty) BEFORE the
            # error is delivered, so a client that hangs up on the first ``error`` event cannot leave it behind. A
            # client disconnect or cancellation never reaches this point (the turn may still be persisting).
            if pending_error is not None:
                if not completed:
                    await service.discard_created_conversation(app_id, prepared)
                yield pending_error
        finally:
            await finish()

    logger.info(
        "Chat stream app_id=%s conversation_id=%s user_id=%s", app_id, turn_conversation_id,
        prepared.user_context.get("user_id"),
    )
    return _ClaimReleasingStreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        on_finish=finish,
    )


@internal_chat_router.post(
    "/messages",
    response_model=ChatMessageResponse,
    summary="Send a message (single JSON answer)",
    responses={
        403: {"description": "No access to the App, or the App is frozen"},
        404: {"description": "Conversation or selected resource not found"},
        409: {"description": "A service used by the turn was retired, or CONVERSATION_BUSY (Retry-After)"},
        422: {"description": "Invalid selection, file_references or search_params"},
        500: {"description": "Internal server error"},
    },
)
async def chat_message(
    app_id: int,
    request: Request,
    message: Annotated[str, Form()],
    selection: Annotated[str, Form()],
    auth_context: AuthDep,
    role: ViewerRole,
    db: DbDep,
    _: FileSizeGuard,
    conversation_id: Annotated[Optional[int], Form()] = None,
    files: Annotated[Optional[List[UploadFile]], File()] = None,
    file_references: Annotated[Optional[str], Form()] = None,
    search_params: Annotated[Optional[str], Form()] = None,
):
    chat_selection = _parse_selection(selection)
    parsed_file_references = _parse_file_references(file_references)
    parsed_search_params = _parse_search_params(search_params)
    _enforce_file_cap(files, parsed_file_references)
    service = _service(db, auth_context, app_id, request)
    prepared = service.prepare_turn(app_id, chat_selection, conversation_id)
    turn_conversation_id = prepared.conversation_id  # plain value (the ORM conversation expires on commit)

    # ``turn_scope`` is the single owner of the claim: whatever ends this block releases it.
    with service.turn_scope(prepared):
        fms: Optional[FileManagementService] = None
        file_refs: list = []
        try:
            fms = FileManagementService()
            file_refs = await fms.resolve_chat_files(
                files=files,
                file_reference_ids=parsed_file_references,
                agent_id=prepared.agent_id,
                user_context=prepared.user_context,
                conversation_id=turn_conversation_id,
                has_memory=True,
            )
            result = await AgentExecutionService().execute_agent_chat_with_file_refs(
                agent_id=prepared.agent_id,
                message=message,
                file_references=file_refs,
                search_params=parsed_search_params,
                user_context=prepared.user_context,
                conversation_id=turn_conversation_id,
                db=db,
                channel=ApprovalChannel.INTERNAL_CHAT,
                turn_config=prepared.turn_config,
                on_turn_completed=prepared.on_turn_completed,
            )
            # Plain data (ids and names) read BEFORE the claim is released: the release commits and expires the
            # session's ORM objects.
            turn_config_summary = prepared.turn_config.to_client_summary()
        except BaseException:
            if fms is not None:
                await fms.cleanup_ephemeral_refs(file_refs)
            file_refs = []
            await service.discard_created_conversation(app_id, prepared)
            raise
        finally:
            if fms is not None:
                await fms.cleanup_ephemeral_refs(file_refs)

    logger.info(
        "Chat message app_id=%s conversation_id=%s user_id=%s", app_id, turn_conversation_id,
        prepared.user_context.get("user_id"),
    )
    return ChatMessageResponse(
        response=result["response"],
        conversation_id=turn_conversation_id,
        metadata={
            "files_processed": (result.get("metadata") or {}).get("files_processed", 0),
            "turn_config": turn_config_summary,
        },
        turn=result.get("turn"),
    )


# ------------------------------------------------------------------ attachments (scoped to one conversation)


@internal_chat_router.post(
    "/conversations/{conversation_id}/files",
    response_model=ChatFileUploadResponse,
    summary="Attach a file to a Chat conversation",
    responses={
        404: {"description": "Conversation not found"},
        409: {"description": "A service used by this resource was retired"},
    },
)
async def upload_file(
    app_id: int,
    conversation_id: int,
    file: Annotated[UploadFile, File()],
    auth_context: AuthDep,
    role: ViewerRole,
    db: DbDep,
    _: FileSizeGuard,
):
    return await _service(db, auth_context, app_id).upload_attachment(app_id, conversation_id, file)


@internal_chat_router.get(
    "/conversations/{conversation_id}/files",
    response_model=ChatFileListResponse,
    summary="Files attached to a Chat conversation",
    responses={404: {"description": "Conversation not found"}},
)
async def list_files(app_id: int, conversation_id: int, auth_context: AuthDep, role: ViewerRole, db: DbDep):
    return await _service(db, auth_context, app_id).list_attachments(app_id, conversation_id)


@internal_chat_router.delete(
    "/conversations/{conversation_id}/files/{file_id}",
    response_model=ResetResponseSchema,
    summary="Remove a file of a Chat conversation",
    responses={404: {"description": "Conversation or file not found"}},
)
async def remove_file(
    app_id: int, conversation_id: int, file_id: str, auth_context: AuthDep, role: ViewerRole, db: DbDep
):
    await _service(db, auth_context, app_id).remove_attachment(app_id, conversation_id, file_id)
    return ResetResponseSchema(success=True, message="File removed successfully")


@internal_chat_router.get(
    "/conversations/{conversation_id}/files/{file_id}/download",
    response_model=ChatFileDownloadResponse,
    summary="Signed download link of a file of a Chat conversation",
    responses={404: {"description": "Conversation or file not found"}},
)
async def download_file(
    app_id: int,
    conversation_id: int,
    file_id: str,
    request: Request,
    auth_context: AuthDep,
    role: ViewerRole,
    db: DbDep,
):
    return await _service(db, auth_context, app_id).attachment_download(
        app_id, conversation_id, file_id, str(request.base_url)
    )
