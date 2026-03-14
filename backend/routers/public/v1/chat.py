import json

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional

from .schemas import (
    AgentResponseSchema,
    MessageResponseSchema,
    PublicConversationSchema,
    PublicConversationListResponseSchema,
    PublicConversationWithHistorySchema,
    CreateConversationRequestSchema,
)
from .auth import (
    get_api_key_auth,
    validate_api_key_for_app,
    create_api_key_user_context,
    validate_agent_ownership,
)
from db.database import get_db

from services.agent_execution_service import AgentExecutionService
from services.agent_streaming_service import AgentStreamingService
from services.conversation_service import ConversationService
from services.file_management_service import FileManagementService, FileReference

from utils.logger import get_logger

logger = get_logger(__name__)

chat_router = APIRouter()


def _parse_json_param(value: Optional[str], param_name: str):
    """Parse an optional JSON string parameter, returning None on failure."""
    if not value:
        return None
    try:
        parsed = json.loads(value)
        if param_name == "file_references" and not isinstance(parsed, list):
            return None
        return parsed
    except json.JSONDecodeError:
        logger.warning(f"Invalid {param_name} JSON, ignoring")
        return None


async def _process_chat_files(
    files: List[UploadFile],
    parsed_file_references: Optional[list],
    agent_id: int,
    user_context: dict,
    conversation_id: Optional[int],
) -> List[FileReference]:
    """
    Process file uploads and merge with existing attached files.
    Shared logic for call_agent and call_agent_stream.
    """
    file_service = FileManagementService()
    all_file_references: List[FileReference] = []
    uploaded_file_ids: set = set()

    if files:
        for upload_file in files:
            if upload_file.filename:
                try:
                    file_ref = await file_service.upload_file(
                        file=upload_file,
                        agent_id=agent_id,
                        user_context=user_context,
                        conversation_id=conversation_id,
                    )
                    all_file_references.append(file_ref)
                    uploaded_file_ids.add(file_ref.file_id)
                except Exception as e:
                    logger.error(f"Error uploading file {upload_file.filename}: {str(e)}")

    existing_files = await file_service.list_attached_files(
        agent_id=agent_id,
        user_context=user_context,
        conversation_id=str(conversation_id) if conversation_id else None,
    )

    if parsed_file_references:
        requested_file_ids = set(parsed_file_references)
        existing_files = [f for f in existing_files if f["file_id"] in requested_file_ids]

    for file_data in existing_files:
        if file_data["file_id"] not in uploaded_file_ids:
            file_ref = FileReference(
                file_id=file_data["file_id"],
                filename=file_data["filename"],
                file_type=file_data["file_type"],
                content=file_data["content"],
                file_path=file_data.get("file_path"),
            )
            all_file_references.append(file_ref)

    return all_file_references


# AGENT CHAT ENDPOINTS

@chat_router.post(
    "/{agent_id}/call",
    summary="Call agent",
    tags=["Agent Chat"],
    response_model=AgentResponseSchema,
)
async def call_agent(
    app_id: int,
    agent_id: int,
    message: str = Form(..., description="The user message to send to the agent"),
    files: List[UploadFile] = File(None, description="Optional files to attach (images, PDFs, text files)"),
    file_references: Optional[str] = Form(None, description="JSON array of existing file_ids to include. If not provided, all files are included."),
    search_params: Optional[str] = Form(None, description="JSON object with search parameters for silo-based agents"),
    conversation_id: Optional[int] = Form(None, description="Optional conversation ID to continue existing conversation"),
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db),
):
    """
    Call an agent for chat completion.

    Supports text messages and file attachments. Files can be:
    - Uploaded directly with this request
    - Previously attached using /files/{agent_id}/attach-file

    **Behavior for agents WITH memory:**
    - If conversation_id is not provided, a new conversation is auto-created
    - The conversation_id is returned in the response - use it for subsequent calls
    - Files are always associated with the conversation

    **Behavior for agents WITHOUT memory:**
    - conversation_id is optional and used only for file grouping
    - Each call is independent (no memory persistence)

    **File handling:**
    - New files uploaded with this request are automatically persisted
    - If file_references is not provided, ALL attached files are included
    - If file_references is provided, only those specific files are included

    **Supported file types:**
    - PDF files (.pdf): Text is extracted automatically
    - Text files (.txt, .md, .json, .csv): Content is read directly
    - Images (.jpg, .jpeg, .png, .gif, .bmp): Sent to vision models
    - Documents (.doc, .docx): Basic support
    """
    validate_api_key_for_app(app_id, api_key, db)
    validate_agent_ownership(db, agent_id, app_id)

    try:
        parsed_search_params = _parse_json_param(search_params, "search_params")
        parsed_file_references = _parse_json_param(file_references, "file_references")

        user_context = create_api_key_user_context(app_id, api_key)

        all_file_references = await _process_chat_files(
            files, parsed_file_references, agent_id, user_context, conversation_id
        )

        execution_service = AgentExecutionService(db)
        result = await execution_service.execute_agent_chat_with_file_refs(
            agent_id=agent_id,
            message=message,
            file_references=all_file_references,
            search_params=parsed_search_params,
            user_context=user_context,
            conversation_id=conversation_id,
            db=db,
        )

        response_data = AgentResponseSchema(
            response=result["response"],
            conversation_id=result.get("conversation_id"),
            usage=result["metadata"],
        )

        logger.info(f"Public API chat request processed for agent {agent_id}, conversation: {result.get('conversation_id')}")
        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in public chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Agent execution failed")


@chat_router.post(
    "/{agent_id}/call/stream",
    summary="Call agent (streaming)",
    tags=["Agent Chat"],
)
async def call_agent_stream(
    app_id: int,
    agent_id: int,
    message: str = Form(..., description="The user message to send to the agent"),
    files: List[UploadFile] = File(None, description="Optional files to attach"),
    file_references: Optional[str] = Form(None, description="JSON array of existing file_ids to include"),
    search_params: Optional[str] = Form(None, description="JSON object with search parameters"),
    conversation_id: Optional[int] = Form(None, description="Optional conversation ID to continue"),
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db),
):
    """
    Call an agent with Server-Sent Events streaming response.

    Returns a stream of SSE events (Content-Type: text/event-stream).
    Each event is a JSON object with "type" and "data" fields:
    - **metadata**: Emitted first with conversation_id and agent info
    - **token**: Partial LLM text output
    - **tool_start**: A tool invocation has started
    - **tool_end**: A tool invocation has finished
    - **thinking**: Human-readable status message
    - **done**: Stream complete with full response and generated files
    - **error**: An error occurred

    Supports the same file handling and conversation features as the
    non-streaming `/call` endpoint.
    """
    validate_api_key_for_app(app_id, api_key, db)
    validate_agent_ownership(db, agent_id, app_id)

    try:
        parsed_search_params = _parse_json_param(search_params, "search_params")
        parsed_file_references = _parse_json_param(file_references, "file_references")

        user_context = create_api_key_user_context(app_id, api_key)

        all_file_references = await _process_chat_files(
            files, parsed_file_references, agent_id, user_context, conversation_id
        )

        streaming_service = AgentStreamingService(db)
        generator = streaming_service.stream_agent_chat(
            agent_id=agent_id,
            message=message,
            file_references=all_file_references,
            search_params=parsed_search_params,
            user_context=user_context,
            conversation_id=conversation_id,
            db=db,
        )

        logger.info(f"Public API streaming chat for agent {agent_id}")
        return StreamingResponse(
            generator,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in public streaming chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Agent execution failed")


@chat_router.post(
    "/{agent_id}/reset",
    summary="Reset conversation",
    tags=["Agent Chat"],
    response_model=MessageResponseSchema,
)
async def reset_conversation(
    app_id: int,
    agent_id: int,
    conversation_id: Optional[int] = Query(None, description="Optional conversation ID to reset"),
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db),
):
    """
    Reset the conversation state for an agent.

    This will clear the conversation history and any attached files.
    If conversation_id is provided, resets that specific conversation.
    """
    validate_api_key_for_app(app_id, api_key, db)
    validate_agent_ownership(db, agent_id, app_id)

    user_context = create_api_key_user_context(app_id, api_key)
    if conversation_id is not None:
        user_context["conversation_id"] = conversation_id

    try:
        execution_service = AgentExecutionService(db)
        success = await execution_service.reset_agent_conversation(
            agent_id=agent_id,
            user_context=user_context,
            db=db,
        )

        if success:
            logger.info(f"Conversation reset for agent {agent_id} via public API")
            return MessageResponseSchema(message="Conversation reset successfully")
        else:
            raise HTTPException(status_code=500, detail="Failed to reset conversation")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in reset conversation endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to reset conversation")


# CONVERSATION MANAGEMENT ENDPOINTS

@chat_router.post(
    "/{agent_id}/conversations",
    summary="Create a new conversation",
    tags=["Conversations"],
    response_model=PublicConversationSchema,
    status_code=201,
)
async def create_conversation(
    app_id: int,
    agent_id: int,
    body: CreateConversationRequestSchema,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db),
):
    """
    Create a new conversation for an agent.

    Useful for explicitly managing conversation sessions.
    The returned conversation_id can be used in subsequent chat calls.
    """
    validate_api_key_for_app(app_id, api_key, db)
    validate_agent_ownership(db, agent_id, app_id)

    try:
        user_context = create_api_key_user_context(app_id, api_key)

        conversation = ConversationService.create_conversation(
            db=db,
            agent_id=agent_id,
            user_context=user_context,
            title=body.title,
        )

        logger.info(f"Created conversation {conversation.conversation_id} for agent {agent_id} via public API")
        return PublicConversationSchema.model_validate(conversation)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating conversation for agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create conversation")


@chat_router.get(
    "/{agent_id}/conversations",
    summary="List conversations",
    tags=["Conversations"],
    response_model=PublicConversationListResponseSchema,
)
async def list_conversations(
    app_id: int,
    agent_id: int,
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db),
):
    """
    List all conversations for an agent.

    Returns a paginated list of conversations ordered by most recent first.
    """
    validate_api_key_for_app(app_id, api_key, db)
    validate_agent_ownership(db, agent_id, app_id)

    try:
        user_context = create_api_key_user_context(app_id, api_key)

        conversations, total = ConversationService.list_conversations(
            db=db,
            agent_id=agent_id,
            user_context=user_context,
            limit=limit,
            offset=offset,
        )

        return PublicConversationListResponseSchema(
            conversations=[PublicConversationSchema.model_validate(c) for c in conversations],
            total=total,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing conversations for agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list conversations")


@chat_router.get(
    "/{agent_id}/conversations/{conversation_id}",
    summary="Get conversation with history",
    tags=["Conversations"],
    response_model=PublicConversationWithHistorySchema,
)
async def get_conversation_with_history(
    app_id: int,
    agent_id: int,
    conversation_id: int,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db),
):
    """
    Get a conversation with its complete message history.

    Returns conversation metadata and all messages exchanged.
    """
    validate_api_key_for_app(app_id, api_key, db)
    validate_agent_ownership(db, agent_id, app_id)

    try:
        user_context = create_api_key_user_context(app_id, api_key)

        conversation = ConversationService.get_conversation(
            db=db,
            conversation_id=conversation_id,
            user_context=user_context,
            agent_id=agent_id,
        )

        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        history = await ConversationService.get_conversation_history(
            db=db,
            conversation_id=conversation_id,
            user_context=user_context,
        )

        return PublicConversationWithHistorySchema(
            conversation_id=conversation.conversation_id,
            agent_id=conversation.agent_id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            messages=history or [],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation {conversation_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get conversation")


@chat_router.delete(
    "/{agent_id}/conversations/{conversation_id}",
    summary="Delete a conversation",
    tags=["Conversations"],
    response_model=MessageResponseSchema,
)
async def delete_conversation(
    app_id: int,
    agent_id: int,
    conversation_id: int,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db),
):
    """
    Delete a conversation and its associated chat history.

    This action is irreversible.
    """
    validate_api_key_for_app(app_id, api_key, db)
    validate_agent_ownership(db, agent_id, app_id)

    try:
        user_context = create_api_key_user_context(app_id, api_key)

        success = await ConversationService.delete_conversation(
            db=db,
            conversation_id=conversation_id,
            user_context=user_context,
        )

        if not success:
            raise HTTPException(status_code=404, detail="Conversation not found")

        logger.info(f"Deleted conversation {conversation_id} for agent {agent_id} via public API")
        return MessageResponseSchema(message="Conversation deleted successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting conversation {conversation_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete conversation")
