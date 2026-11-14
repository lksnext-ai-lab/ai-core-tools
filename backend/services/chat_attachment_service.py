"""Attachment operations shared by the agent playground and the flexible App Chat.

The playground routers (``routers/internal/agents.py``) used to hold this logic inline; it lives here so the
App Chat reuses it instead of copying it. The callers decide WHICH conversation / agent a file belongs to and
validate ownership; this module only performs the upload (+ vectorization), listing, removal and download-link
steps on top of ``FileManagementService`` and ``PlaygroundMediaService``. Responses keep the exact shape the
playground has always returned.
"""
import os
from typing import Any, Callable, Dict, List, Optional

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from services.file_management_service import FileManagementService, FileReference
from services.playground_media_service import PlaygroundMediaService, is_vectorizable_file
from utils.logger import get_logger
from utils.security import build_expiring_static_url, generate_signature
from utils.service_lifecycle import ServiceRetiredError

logger = get_logger(__name__)


class ChatAttachmentService:
    """Stateless helpers; every method takes the already-authorized scope (agent, user context, conversation)."""

    @staticmethod
    def require_owned_conversation(
        db: Session,
        conversation_id: Optional[Any],
        user_context: Dict[str, Any],
        agent_id: int,
        has_memory: bool,
    ) -> Optional[Any]:
        """404 unless ``conversation_id`` is a conversation of ``agent_id`` that the caller owns.

        Persistent uploads are stored under ``tmp/conversations/{conversation_id}/`` (no user or App in the path)
        and conversation ids are global, so a client-supplied id must be checked BEFORE the first byte is written.
        "Owns" is the ``ConversationService`` rule: same user, or same API key. The agent is already known to belong
        to the caller's App, so filtering by ``agent_id`` also pins the App. Agents without memory store uploads
        per caller in the ephemeral area (no shared path), so any id is only a grouping label there and is allowed.

        Returns:
            The id to use from now on: the canonical decimal string (``"012"`` -> ``"12"``, so it cannot name a
            different directory than the conversation) for a checked string id, an int unchanged, and the input as is
            when there is nothing to check.

        Raises:
            HTTPException: 404 (the same answer for missing / not yours / other agent or App).
        """
        if conversation_id in (None, "") or not has_memory:
            return conversation_id
        from services.conversation_service import ConversationService

        try:
            numeric_id = int(conversation_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=404, detail="Conversation not found")
        if ConversationService.get_conversation(db, numeric_id, user_context, agent_id) is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return str(numeric_id) if isinstance(conversation_id, str) else conversation_id

    @staticmethod
    async def upload(
        db: Session,
        file: UploadFile,
        *,
        agent_id: int,
        app_id: int,
        user_context: Dict[str, Any],
        conversation_id: Optional[int],
        has_memory: bool,
        resolve_session_id: Callable[[], Optional[str]],
    ) -> Dict[str, Any]:
        """Store ``file`` and, for a persistent vectorizable one, index it into the conversation's temp silo.

        ``resolve_session_id`` is only called when vectorization applies and must return the session id of the
        conversation after the caller validated its ownership (user + agent + App), so a caller cannot inject
        document content into another conversation's silo (IDOR). A retired embedding service discards the file
        and re-raises; any other indexing failure is logged and leaves ``vectorized`` false.

        Returns:
            The upload response payload (``success``, ``file_id``, ``vectorized``, ...).
        """
        file_service = FileManagementService()
        file_ref = await file_service.upload_file(
            file=file,
            agent_id=agent_id,
            user_context=user_context,
            conversation_id=conversation_id,
            has_memory=has_memory,
        )

        vectorized = False
        if (
            has_memory
            and conversation_id
            and is_vectorizable_file(file_ref.file_type, file_ref.filename)
            and file_ref.content
        ):
            session_id = resolve_session_id()
            if session_id:
                try:
                    vectorized = PlaygroundMediaService.vectorize_uploaded_file(
                        app_id=app_id,
                        agent_id=agent_id,
                        session_id=session_id,
                        file_id=file_ref.file_id,
                        filename=file_ref.filename,
                        file_path=file_ref.file_path,
                        content=file_ref.content,
                        db=db,
                    )
                except ServiceRetiredError:
                    await file_service.discard_uploaded_file(file_ref.file_id, agent_id, user_context, conversation_id)
                    raise
                except Exception as vec_err:
                    logger.warning(f"File vectorization at upload failed: {vec_err}")

        return {
            "success": True,
            "file_id": file_ref.file_id,
            "filename": file_ref.filename,
            "file_type": file_ref.file_type,
            "vectorized": vectorized,
            # Visual feedback fields
            "file_size_bytes": file_ref.file_size_bytes,
            "file_size_display": FileReference.format_file_size(file_ref.file_size_bytes),
            "processing_status": file_ref.processing_status,
            "content_preview": file_ref.content_preview,
            "has_extractable_content": file_ref.has_extractable_content,
            "mime_type": file_ref.mime_type,
        }

    @staticmethod
    async def list_files(
        agent_id: int, user_context: Dict[str, Any], conversation_id: Optional[int]
    ) -> Dict[str, Any]:
        """Files of one session (one conversation when given) with the total size."""
        files = await FileManagementService().list_attached_files(
            agent_id=agent_id,
            user_context=user_context,
            conversation_id=str(conversation_id) if conversation_id else None,
        )
        total_size = sum(f.get("file_size_bytes", 0) or 0 for f in files)
        return {
            "files": files,
            "total_size_bytes": total_size,
            "total_size_display": FileReference.format_file_size(total_size),
        }

    @staticmethod
    async def remove(
        file_id: str, agent_id: int, user_context: Dict[str, Any], conversation_id: Optional[int]
    ) -> bool:
        """Remove one file of a session; False when it is not there."""
        return await FileManagementService().remove_file(
            file_id=file_id,
            agent_id=agent_id,
            user_context=user_context,
            conversation_id=str(conversation_id) if conversation_id else None,
        )

    @staticmethod
    async def find(
        file_id: str,
        agent_id: int,
        user_context: Dict[str, Any],
        conversation_ids: List[Optional[str]],
    ) -> Optional[Dict[str, Any]]:
        """First file called ``file_id`` among the sessions in ``conversation_ids`` (tried in order)."""
        file_service = FileManagementService()
        for conv_id in conversation_ids:
            files = await file_service.list_attached_files(
                agent_id=agent_id, user_context=user_context, conversation_id=conv_id
            )
            found = next((f for f in files if f.get("file_id") == file_id), None)
            if found:
                return found
        return None

    @staticmethod
    async def list_file_ids(agent_id: int, user_context: Dict[str, Any], conversation_id: int) -> List[str]:
        """Ids of the files currently attached to one conversation."""
        files = await FileManagementService().list_attached_files(agent_id, user_context, str(conversation_id))
        return [f["file_id"] for f in files if f.get("file_id")]

    @staticmethod
    async def remove_many(
        file_ids: List[str], agent_id: int, user_context: Dict[str, Any], conversation_id: int
    ) -> None:
        """Remove exactly ``file_ids`` from one conversation (best effort; one failure does not stop the rest)."""
        file_service = FileManagementService()
        for file_id in file_ids:
            try:
                await file_service.remove_file(file_id, agent_id, user_context, str(conversation_id))
            except Exception:
                logger.error("Could not remove attachment (conversation_id=%s file_id=%s)", conversation_id, file_id)

    @staticmethod
    def delete_storage(agent_id: int, user_context: Dict[str, Any], conversation_id: int) -> None:
        """Delete everything stored for one conversation: its session metadata and its working directory."""
        FileManagementService().delete_conversation_storage(agent_id, user_context, str(conversation_id))

    @staticmethod
    def build_expiring_download(
        file_data: Dict[str, Any], identity: str, request_base_url: str, ttl_seconds: int
    ) -> Optional[Dict[str, str]]:
        """Short-lived signed ``/static`` URL (query parameters URL-encoded), or None without a stored path."""
        if not file_data or not file_data.get("file_path"):
            return None
        file_path = file_data["file_path"].lstrip("/")
        filename = file_data.get("filename", os.path.basename(file_path))
        base_url = os.getenv("AICT_BASE_URL", "").rstrip("/") or request_base_url.rstrip("/")
        url = build_expiring_static_url(base_url, file_path, identity, ttl_seconds, filename)
        return {"download_url": url, "filename": filename}

    @staticmethod
    def build_download(file_data: Dict[str, Any], user_email: str, request_base_url: str) -> Optional[Dict[str, str]]:
        """Signed ``/static`` URL of a file, or None when it has no stored path."""
        if not file_data or not file_data.get("file_path"):
            return None
        file_path = file_data["file_path"].lstrip("/")
        filename = file_data.get("filename", os.path.basename(file_path))

        # Absolute base URL: prefer the explicit env var, fall back to the request origin.
        base_url = os.getenv("AICT_BASE_URL", "").rstrip("/") or request_base_url.rstrip("/")
        sig = generate_signature(file_path, user_email)
        download_url = f"{base_url}/static/{file_path}?user={user_email}&sig={sig}&filename={filename}"
        return {"download_url": download_url, "filename": filename}

