"""Attachment operations shared by the agent playground and the flexible App Chat.

The playground routers (``routers/internal/agents.py``) used to hold this logic inline; it lives here so the
App Chat reuses it instead of copying it. The callers decide WHICH conversation / agent a file belongs to and
validate ownership; this module only performs the upload (+ vectorization), listing, removal and download-link
steps on top of ``FileManagementService`` and ``PlaygroundMediaService``. Responses keep the exact shape the
playground has always returned.
"""
import asyncio
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from db.database import SessionLocal
from services.file_management_service import FileManagementService, FileReference
from services.playground_media_service import PlaygroundMediaService, is_vectorizable_file
from utils.logger import get_logger
from utils.security import build_expiring_static_url, generate_signature
from utils.service_lifecycle import ServiceRetiredError

logger = get_logger(__name__)

# Worker threads of the Chat's attachment indexing. Dedicated and small on purpose: a provider that never answers can
# park these threads (a thread cannot be killed), and that must not starve the default executor other code uses.
_INDEXING_WORKERS = 4
_indexing_executor: Optional[ThreadPoolExecutor] = None
# Upper bound of the embedding work of one attachment (upload or file sent with a turn); on expiry the file is simply
# not indexed and travels in the prompt instead.
ATTACHMENT_INDEXING_TIMEOUT_SECONDS = 60
# At most this many indexing jobs run at once per embedding service: one App's hung provider cannot take every worker
# thread. Jobs beyond the cap are not indexed at once (rather than queued: a queued job would eat the same 60 s
# budget and still end up not indexed, while blocking a worker slot others could use).
MAX_INDEXING_JOBS_PER_SERVICE = 2
_service_slots: Dict[int, threading.BoundedSemaphore] = {}
_service_slots_lock = threading.Lock()


def _slots_for(service_id: int) -> threading.BoundedSemaphore:
    with _service_slots_lock:
        return _service_slots.setdefault(service_id, threading.BoundedSemaphore(MAX_INDEXING_JOBS_PER_SERVICE))


def shutdown_indexing_executor() -> None:
    """App lifespan shutdown: do not wait for (possibly hung) provider calls, drop what was queued."""
    global _indexing_executor
    executor, _indexing_executor = _indexing_executor, None
    if executor is not None:
        executor.shutdown(wait=False, cancel_futures=True)


def _get_indexing_executor() -> ThreadPoolExecutor:
    global _indexing_executor
    if _indexing_executor is None:
        _indexing_executor = ThreadPoolExecutor(max_workers=_INDEXING_WORKERS, thread_name_prefix="chat-indexing")
    return _indexing_executor


@contextmanager
def open_indexing_session() -> Iterator[Session]:
    """A DB session of its own for one indexing job (never the request's session, which is not thread-safe)."""
    session = SessionLocal()
    try:
        yield session
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


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
        embedding_service_id: Optional[int] = None,
        degrade_when_retired: bool = False,
        index_timeout_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Store ``file`` and, for a persistent vectorizable one, index it into the conversation's temp silo.

        ``resolve_session_id`` is only called when vectorization applies and must return the session id of the
        conversation after the caller validated its ownership (user + agent + App), so a caller cannot inject
        document content into another conversation's silo (IDOR). A retired embedding service discards the file
        and re-raises; any other indexing failure is logged and leaves ``vectorized`` false.

        ``embedding_service_id`` (the Chat passes the App's active default) is the service a NEW temp silo is
        created with; a conversation whose temp silo already exists keeps indexing with the service that silo was
        created with, so a collection never mixes embedding models. With ``degrade_when_retired`` (the Chat, together
        with ``index_timeout_seconds``) a retired service does not fail the upload: the file is kept and simply not
        indexed (it goes in the prompt).

        With ``index_timeout_seconds`` (the Chat) the indexing runs in a worker thread, on a database session opened
        inside that thread, and is abandoned after the timeout: embedding clients have no timeout of their own and
        run synchronously, so inline they would freeze every request of the worker. A timeout or any provider error
        leaves ``vectorized`` false (the file stays and travels in the prompt); only the exception class is logged
        (messages can carry document text). Without it (the playground, unchanged) the indexing runs inline.

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
            if session_id and index_timeout_seconds is not None:
                vectorized = await ChatAttachmentService._vectorize_in_worker(
                    file_ref, app_id=app_id, agent_id=agent_id, session_id=session_id,
                    embedding_service_id=embedding_service_id, timeout=index_timeout_seconds,
                    degrade_when_retired=degrade_when_retired,
                    on_retired=lambda: file_service.discard_uploaded_file(
                        file_ref.file_id, agent_id, user_context, conversation_id
                    ),
                )
            elif session_id:
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
                        embedding_service_id=embedding_service_id,
                    )
                except ServiceRetiredError:
                    await file_service.discard_uploaded_file(
                        file_ref.file_id, agent_id, user_context, conversation_id
                    )
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
    async def vectorize_in_worker(
        *,
        app_id: int,
        agent_id: int,
        session_id: str,
        file_id: str,
        filename: str,
        file_path: Optional[str],
        content: str,
        embedding_service_id: Optional[int],
        timeout: float = ATTACHMENT_INDEXING_TIMEOUT_SECONDS,
    ) -> bool:
        """Index one file in a worker thread (own session, plain values only) within ``timeout``; False on failure.

        Never touches the caller's session. Retired service, provider error, timeout and "too many jobs for this
        embedding service" all end in False (the file travels in the prompt); only exception classes are logged.
        A timed-out job cannot be killed: it is abandoned and keeps its per-service slot until it returns.
        """
        def job() -> bool:
            with open_indexing_session() as worker_db:
                repo = PlaygroundMediaService.get_temp_repository(app_id, agent_id, session_id, worker_db)
                key = (repo.silo.embedding_service_id if repo is not None and repo.silo is not None else None) \
                    or embedding_service_id or 0
                slots = _slots_for(key)
                if not slots.acquire(blocking=False):
                    logger.warning("Chat attachment not indexed: too many indexing jobs for embedding service %s", key)
                    return False
                try:
                    return PlaygroundMediaService.vectorize_uploaded_file(
                        app_id=app_id, agent_id=agent_id, session_id=session_id, file_id=file_id, filename=filename,
                        file_path=file_path, content=content, db=worker_db, embedding_service_id=embedding_service_id,
                    )
                finally:
                    slots.release()

        loop = asyncio.get_running_loop()
        try:
            return bool(await asyncio.wait_for(loop.run_in_executor(_get_indexing_executor(), job), timeout))
        except ServiceRetiredError:
            logger.warning("Chat attachment not indexed: its embedding service is retired")
            raise
        except asyncio.TimeoutError:
            logger.warning("Chat attachment not indexed: the embedding provider did not answer in %ss", timeout)
            return False
        except Exception as exc:  # noqa: BLE001
            logger.warning("Chat attachment not indexed: indexing failed (%s)", type(exc).__name__)
            return False

    @staticmethod
    async def _vectorize_in_worker(
        file_ref: Any,
        *,
        app_id: int,
        agent_id: int,
        session_id: str,
        embedding_service_id: Optional[int],
        timeout: float,
        degrade_when_retired: bool,
        on_retired: Callable[[], Any],
    ) -> bool:
        """``vectorize_in_worker`` for an upload: a retired service degrades (Chat) or discards the file and raises."""
        try:
            return await ChatAttachmentService.vectorize_in_worker(
                app_id=app_id, agent_id=agent_id, session_id=session_id, file_id=file_ref.file_id,
                filename=file_ref.filename, file_path=file_ref.file_path, content=file_ref.content,
                embedding_service_id=embedding_service_id, timeout=timeout,
            )
        except ServiceRetiredError:
            if degrade_when_retired:
                return False  # the failed transaction was the worker session's; the request's was not involved
            await on_retired()
            raise

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

