import os

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Form, Query, Request
from sqlalchemy.orm import Session
from typing import Optional, Annotated

from .schemas import (
    AttachFileResponseSchema,
    DetachFileResponseSchema,
    ListFilesResponseSchema,
    FileAttachmentSchema,
    FileDownloadResponseSchema,
)
from .auth import (
    get_api_key_auth,
    validate_api_key_for_app,
    create_api_key_user_context,
    validate_agent_ownership,
)
from db.database import get_db

from services.file_management_service import FileManagementService, FileReference
from services.conversation_service import ConversationService
from utils.security import generate_signature

from utils.logger import get_logger

logger = get_logger(__name__)

files_router = APIRouter()


# FILE OPERATION ENDPOINTS

@files_router.post(
    "/{agent_id}/attach-file",
    summary="Attach file for chat",
    tags=["File Operations"],
    response_model=AttachFileResponseSchema,
    responses={500: {"description": "Failed to attach file"}},
)
async def attach_file(
    app_id: int,
    agent_id: int,
    file: Annotated[UploadFile, File(...)],
    api_key: Annotated[str, Depends(get_api_key_auth)],
    db: Annotated[Session, Depends(get_db)],
    conversation_id: Annotated[
        Optional[str],
        Form(
            None,
            description="Optional conversation ID for memory-enabled agents. If not provided for a memory-enabled agent, a new conversation will be created.",
        ),
    ] = None,
):
    """
    Attach a file to an agent for chat context.

    The file will be processed and stored for use in subsequent chat calls.
    Supported file types: PDF, TXT, MD, JSON, CSV, images (JPG, PNG, etc.)

    **For agents with memory:**
    - If conversation_id is provided, the file is associated with that specific conversation
    - If conversation_id is NOT provided, a new conversation is auto-created
    - The conversation_id is returned in the response - use it for subsequent calls

    **For agents without memory:**
    - conversation_id is optional (files are session-global)
    """
    validate_api_key_for_app(app_id, api_key, db)
    agent = validate_agent_ownership(db, agent_id, app_id)

    try:
        user_context = create_api_key_user_context(app_id, api_key, conversation_id)

        # For agents WITH memory: ensure we have a conversation_id
        effective_conversation_id = conversation_id

        if agent.has_memory and not conversation_id:
            new_conversation = ConversationService.create_conversation(
                db=db,
                agent_id=agent_id,
                user_context=user_context,
                title=None,
            )
            effective_conversation_id = str(new_conversation.conversation_id)
            user_context["conversation_id"] = effective_conversation_id
            logger.info(f"Auto-created conversation {effective_conversation_id} for file attachment to agent {agent_id}")

        file_service = FileManagementService()
        file_ref = await file_service.upload_file(
            file=file,
            agent_id=agent_id,
            user_context=user_context,
            conversation_id=effective_conversation_id,
        )

        logger.info(f"File {file.filename} attached to agent {agent_id}, conversation {effective_conversation_id} via public API")

        return AttachFileResponseSchema(
            success=True,
            file_id=file_ref.file_id,
            filename=file_ref.filename,
            file_type=file_ref.file_type,
            message="File attached successfully",
            conversation_id=effective_conversation_id,
            file_size_bytes=file_ref.file_size_bytes,
            file_size_display=FileReference.format_file_size(file_ref.file_size_bytes),
            processing_status=file_ref.processing_status,
            content_preview=file_ref.content_preview,
            has_extractable_content=file_ref.has_extractable_content,
            mime_type=file_ref.mime_type,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error attaching file for agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to attach file")


@files_router.delete(
    "/{agent_id}/detach-file/{file_id}",
    summary="Remove attached file",
    tags=["File Operations"],
    response_model=DetachFileResponseSchema,
    responses={500: {"description": "Failed to detach file"}},
)
async def detach_file(
    app_id: int,
    agent_id: int,
    file_id: str,
    api_key: Annotated[str, Depends(get_api_key_auth)],
    db: Annotated[Session, Depends(get_db)],
    conversation_id: Annotated[
        Optional[str],
        Query(None, description="Optional conversation ID to scope file removal"),
    ] = None,
):
    """
    Remove an attached file from an agent's context.

    The file will no longer be included in subsequent chat calls.

    **For agents with memory:**
    - If conversation_id is provided, removes the file from that specific conversation
    - If conversation_id is not provided, removes from the global session
    """
    validate_api_key_for_app(app_id, api_key, db)
    validate_agent_ownership(db, agent_id, app_id)

    try:
        user_context = create_api_key_user_context(app_id, api_key, conversation_id)

        file_service = FileManagementService()
        success = await file_service.remove_file(
            file_id=file_id,
            agent_id=agent_id,
            user_context=user_context,
            conversation_id=conversation_id,
        )

        if success:
            logger.info(f"File {file_id} detached from agent {agent_id} via public API")
            return DetachFileResponseSchema(
                success=True,
                message="File detached successfully",
            )
        else:
            return DetachFileResponseSchema(
                success=False,
                message="File not found or already removed",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error detaching file {file_id} for agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to detach file")


@files_router.get(
    "/{agent_id}/attached-files",
    summary="List attached files",
    tags=["File Operations"],
    response_model=ListFilesResponseSchema,
    responses={500: {"description": "Failed to list files"}},
)
async def list_attached_files(
    app_id: int,
    agent_id: int,
    api_key: Annotated[str, Depends(get_api_key_auth)],
    db: Annotated[Session, Depends(get_db)],
    conversation_id: Annotated[
        Optional[str],
        Query(None, description="Optional conversation ID to filter files"),
    ] = None,
):
    """
    List all files attached to an agent for the current session.

    Returns a list of files that will be included in chat context.

    **For agents with memory:**
    - If conversation_id is provided, returns only files for that conversation
    - If conversation_id is not provided, returns files from the global session
    """
    validate_api_key_for_app(app_id, api_key, db)
    validate_agent_ownership(db, agent_id, app_id)

    try:
        user_context = create_api_key_user_context(app_id, api_key, conversation_id)

        file_service = FileManagementService()
        files_data = await file_service.list_attached_files(
            agent_id=agent_id,
            user_context=user_context,
            conversation_id=conversation_id,
        )

        files = [
            FileAttachmentSchema(
                file_id=f["file_id"],
                filename=f["filename"],
                file_type=f["file_type"],
                uploaded_at=f.get("uploaded_at"),
                file_size_bytes=f.get("file_size_bytes"),
                file_size_display=f.get("file_size_display"),
                processing_status=f.get("processing_status"),
                content_preview=f.get("content_preview"),
                has_extractable_content=f.get("has_extractable_content"),
                mime_type=f.get("mime_type"),
                conversation_id=f.get("conversation_id"),
            )
            for f in files_data
        ]

        total_size = sum(f.get("file_size_bytes", 0) or 0 for f in files_data)

        logger.info(f"Listed {len(files)} files for agent {agent_id} via public API")
        return ListFilesResponseSchema(
            files=files,
            total_size_bytes=total_size,
            total_size_display=FileReference.format_file_size(total_size),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing files for agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list files")


@files_router.get(
    "/{agent_id}/files/{file_id}/download",
    summary="Download a file",
    tags=["File Operations"],
    response_model=FileDownloadResponseSchema,
    responses={
        404: {"description": "File not found"},
        500: {"description": "Failed to generate download URL"},
    },
)
async def download_file(
    app_id: int,
    agent_id: int,
    file_id: str,
    request: Request,
    api_key: Annotated[str, Depends(get_api_key_auth)],
    db: Annotated[Session, Depends(get_db)],
    conversation_id: Annotated[
        Optional[str],
        Query(None, description="Optional conversation ID to scope file lookup"),
    ] = None,
):
    """
    Get a signed download URL for an attached file.

    Returns a URL that can be used to download the file directly.
    The URL is signed and time-limited for security.
    """
    validate_api_key_for_app(app_id, api_key, db)
    validate_agent_ownership(db, agent_id, app_id)

    try:
        user_context = create_api_key_user_context(app_id, api_key, conversation_id)

        file_service = FileManagementService()

        # Try with conversation_id first, then fall back to global session
        file_data = None
        conv_ids_to_try = [conversation_id, None] if conversation_id else [None]
        for try_conv_id in conv_ids_to_try:
            files = await file_service.list_attached_files(
                agent_id=agent_id,
                user_context=user_context,
                conversation_id=try_conv_id,
            )
            file_data = next((f for f in files if f.get("file_id") == file_id), None)
            if file_data:
                break

        if not file_data or not file_data.get("file_path"):
            raise HTTPException(status_code=404, detail="File not found")

        file_path = file_data["file_path"].lstrip("/")
        filename = file_data.get("filename", os.path.basename(file_path))
        user_id = user_context["user_id"]

        aict_base_url = os.getenv("AICT_BASE_URL", "").rstrip("/")
        if not aict_base_url:
            aict_base_url = str(request.base_url).rstrip("/")

        sig = generate_signature(file_path, user_id)
        download_url = (
            f"{aict_base_url}/static/{file_path}"
            f"?user={user_id}&sig={sig}"
            f"&filename={filename}"
        )

        return FileDownloadResponseSchema(
            download_url=download_url,
            filename=filename,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading file {file_id} for agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate download URL")
