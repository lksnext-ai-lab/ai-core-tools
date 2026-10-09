import asyncio
import json
import os
import shutil
import uuid
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import UploadFile, HTTPException

from tools.PDFTools import extract_text_from_pdf, convert_pdf_to_images, check_pdf_has_text
from utils.logger import get_logger
from utils.log_safety import sanitize_for_log
from utils.path_safety import UnsafePathError, resolve_within
from utils.async_files import read_json, read_text, write_json, write_temp_file, write_text

logger = get_logger(__name__)


# Storage strategies for uploaded files.
# - "ephemeral": the file is only needed for the current request (e.g. a
#   one-shot Vision agent call via public API key). It lives under
#   ``data/tmp/ephemeral/{session_key}/`` and is removed by the caller in
#   a ``finally`` block (or by the background cleanup worker if missed).
# - "persistent": the file may be referenced again in later messages of the
#   same conversation (agent has memory AND an explicit ``conversation_id``).
#   It lives under ``data/tmp/persistent/{session_key}/`` and is removed by
#   the background cleanup worker after TMP_PERSISTENT_TTL_DAYS of inactivity.
STORAGE_STRATEGY_EPHEMERAL = "ephemeral"
STORAGE_STRATEGY_PERSISTENT = "persistent"


class UnsupportedFileTypeError(Exception):
    """Raised by ``_process_file_content(strict=True)`` for a file type that would
    otherwise fall back to a placeholder ("not implemented"/"type: unknown") sentence
    instead of real extracted content. Callers with ``strict=False`` (the default,
    used by every existing caller) never see this: they keep getting the placeholder.

    Carries ``temp_path`` (the already-spooled upload on disk, if one was
    created before the rejection) so ``upload_file``'s existing ``finally``
    cleanup can remove it; otherwise that spool file would leak."""

    def __init__(self, message: str, *, temp_path: Optional[str] = None) -> None:
        super().__init__(message)
        self.temp_path = temp_path


class FileProcessingError(Exception):
    """Raised by ``_process_file_content(strict=True)`` when extraction for an
    otherwise-supported type fails. ``strict=False`` callers keep getting the
    "Error processing file: ..." placeholder string instead.

    Carries ``temp_path`` for the same reason as :class:`UnsupportedFileTypeError`."""

    def __init__(self, message: str, *, temp_path: Optional[str] = None) -> None:
        super().__init__(message)
        self.temp_path = temp_path


class FileReference:
    """Represents a file reference for agent consumption with visual feedback data"""
    
    # MIME type mapping
    MIME_TYPES = {
        "pdf": "application/pdf",
        "text": "text/plain",
        "image": "image/jpeg",  # Default, will be overridden based on extension
        "document": "application/msword",
        "unknown": "application/octet-stream"
    }
    
    IMAGE_MIME_TYPES = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".webp": "image/webp"
    }
    
    def __init__(
        self, 
        file_id: str, 
        filename: str, 
        file_type: str, 
        content: str, 
        file_path: str = None,
        file_size_bytes: int = None,
        conversation_id: str = None
    ):
        self.file_id = file_id
        self.filename = filename
        self.file_type = file_type
        self.content = content
        self.file_path = file_path  # Relative path to TMP_BASE_FOLDER
        self.file_size_bytes = file_size_bytes
        self.conversation_id = conversation_id
        self.uploaded_at = datetime.utcnow()
        
        # Determine MIME type
        self.mime_type = self._get_mime_type()
        
        # Calculate processing status and content info
        self.processing_status = self._get_processing_status()
        self.has_extractable_content = self._has_extractable_content()
        self.content_preview = self._get_content_preview()
    
    def _get_mime_type(self) -> str:
        """Get MIME type based on file type and extension"""
        if self.file_type == "image":
            ext = os.path.splitext(self.filename)[1].lower() if self.filename else ""
            return self.IMAGE_MIME_TYPES.get(ext, "image/jpeg")
        return self.MIME_TYPES.get(self.file_type, "application/octet-stream")
    
    def _get_processing_status(self) -> str:
        """Determine processing status based on content and file type"""
        if not self.content:
            return "error"
        if self.content.startswith("Error"):
            return "error"
        # Images are always "ready" - they're sent directly to vision models
        # No text extraction needed for images
        if self.file_type == "image":
            return "ready"
        # Processing status reflects upload availability. Text extraction support
        # is exposed separately via has_extractable_content/content_preview.
        return "ready"
    
    def _has_extractable_content(self) -> bool:
        """Check if meaningful content was extracted"""
        if not self.content:
            return False
        # Check for placeholder messages
        placeholder_indicators = [
            "not implemented",
            "Error processing",
            "Image file:",
            "Document file:",
            "File:"
        ]
        return not any(indicator in self.content for indicator in placeholder_indicators)
    
    def _get_content_preview(self, max_length: int = 200) -> Optional[str]:
        """Get preview of extracted content"""
        if not self.has_extractable_content:
            return None
        if len(self.content) <= max_length:
            return self.content
        return self.content[:max_length] + "..."
    
    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        """Format file size to human readable string"""
        if size_bytes is None:
            return "Unknown"
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with visual feedback data"""
        return {
            "file_id": self.file_id,
            "filename": self.filename,
            "file_type": self.file_type,
            "content": self.content,
            "file_path": self.file_path,
            "uploaded_at": self.uploaded_at.isoformat(),
            # Visual feedback fields
            "file_size_bytes": self.file_size_bytes,
            "file_size_display": self.format_file_size(self.file_size_bytes),
            "processing_status": self.processing_status,
            "content_preview": self.content_preview,
            "has_extractable_content": self.has_extractable_content,
            "mime_type": self.mime_type,
            "conversation_id": self.conversation_id
        }


class FileManagementService:
    """Unified file management - used by both public and internal APIs"""
    
    def __init__(self):
        # Persistent file storage on disk
        # Structure: {session_key: {file_id: FileReference}}
        self._files: Dict[str, Dict[str, FileReference]] = {}
        
        # Get TMP_BASE_FOLDER from config
        from utils.config import get_app_config
        app_config = get_app_config()
        self._tmp_base_folder = app_config['TMP_BASE_FOLDER']
        self._persistent_dir = os.path.join(self._tmp_base_folder, "persistent")
        self._ephemeral_dir = os.path.join(self._tmp_base_folder, "ephemeral")
        self._temp_dir = os.path.join(self._tmp_base_folder, "uploads")

        # Ensure directories exist
        os.makedirs(self._persistent_dir, exist_ok=True)
        os.makedirs(self._ephemeral_dir, exist_ok=True)
        os.makedirs(self._temp_dir, exist_ok=True)
        os.makedirs(os.path.join(self._tmp_base_folder, "downloads"), exist_ok=True)
        os.makedirs(os.path.join(self._tmp_base_folder, "images"), exist_ok=True)
        
        # Files will be loaded on-demand per session

    @property
    def tmp_base_folder(self) -> str:
        """Public read-only accessor for ``TMP_BASE_FOLDER``.

        Lets external callers (e.g. the A2A output mapper's file resolver)
        join a ``FileReference.file_path`` into an absolute path through
        ``utils.path_safety.resolve_within`` without reaching into the
        ``_tmp_base_folder`` private attribute.
        """
        return self._tmp_base_folder

    async def upload_file(
        self,
        file: UploadFile,
        agent_id: int,
        user_context: Dict = None,
        conversation_id: Optional[int] = None,
        has_memory: bool = False,
        strict: bool = False,
    ) -> FileReference:
        """
        Upload file for agent consumption.

        The storage strategy is decided here based on ``has_memory`` and
        ``conversation_id``:

        - **Ephemeral** (default): no memory, or memory enabled but no
          ``conversation_id``. The file is stored under
          ``data/tmp/ephemeral/{session_key}/`` and the caller is expected to
          remove it in a ``finally`` block via
          :meth:`cleanup_ephemeral_refs`. A background sweep also reaps any
          ephemeral file older than ``TMP_EPHEMERAL_ORPHAN_HOURS``.
        - **Persistent**: ``has_memory=True`` AND ``conversation_id`` is set.
          The file lives under the existing ``data/tmp/persistent/{session_key}/``
          layout and the background worker expires it after
          ``TMP_PERSISTENT_TTL_DAYS`` of inactivity.

        Args:
            file: Uploaded file.
            agent_id: ID of the agent.
            user_context: User context (api_key, user_id, etc.).
            conversation_id: Optional conversation ID to organize files.
            has_memory: Whether the target agent persists conversation state.
                Callers MUST pass this so the storage strategy is correct;
                defaulting to ``False`` keeps backward compatibility with
                callers that have not been migrated yet.
            strict: When ``True``, never substitute placeholder content.
                An unsupported/unrecognized file type (anything that would
                otherwise fall back to a "not implemented"/"type: unknown"
                sentence) raises ``HTTPException(415)``; a genuine extraction
                failure (e.g. a corrupt PDF, instead of the "Error processing
                file: ..." placeholder, which would otherwise leak the raw
                exception text to the LLM) raises ``HTTPException(422)``.
                Defaults to ``False``, so every existing caller (public/
                internal chat) keeps today's placeholder behaviour unchanged;
                only the A2A input pipeline (FR-18: never a placeholder) opts in.

        Returns:
            FileReference object. The instance is decorated with two
            attributes used by :meth:`cleanup_ephemeral_refs`:
            ``storage_strategy`` (``"ephemeral"`` or ``"persistent"``) and
            ``_session_key`` (used to locate the sidecar metadata).
        """
        temp_path: Optional[str] = None
        try:
            # Validate file
            if not file.filename:
                raise HTTPException(status_code=400, detail="No filename provided")

            file_id = str(uuid.uuid4())
            file_type = self._get_file_type(file.filename)

            # Process file based on type (also returns file size)
            content, temp_path, file_size = await self._process_file_content(file, file_type, strict=strict)

            storage_strategy = self._resolve_storage_strategy(has_memory, conversation_id)

            file_ref = FileReference(
                file_id=file_id,
                filename=file.filename,
                file_type=file_type,
                content=content,
                file_path=None,  # Will be set by _save_file_to_disk
                file_size_bytes=file_size,
                conversation_id=str(conversation_id) if conversation_id else None,
            )

            # Session key for this agent, user, and conversation.
            session_key = self._get_session_key(
                agent_id,
                user_context,
                str(conversation_id) if conversation_id else None,
            )

            # Stamp metadata used by cleanup_ephemeral_refs and the
            # background sweep. These attributes are not part of the public
            # FileReference contract; they are internal annotations.
            file_ref.storage_strategy = storage_strategy
            file_ref._session_key = session_key

            if session_key not in self._files:
                self._files[session_key] = {}

            await self._save_file_to_disk(
                session_key,
                file_id,
                file_ref,
                temp_path,
                conversation_id,
                storage_strategy=storage_strategy,
            )

            self._files[session_key][file_id] = file_ref

            logger.info(
                "Uploaded file %s for agent %s, session %s (strategy=%s)",
                file.filename, agent_id, session_key, storage_strategy,
            )
            return file_ref

        except HTTPException:
            raise
        except UnsupportedFileTypeError as e:
            # Recover the spooled temp file (if any) so the `finally` below
            # removes it — _process_file_content raised before returning it,
            # so this function's own `temp_path` local was never assigned.
            temp_path = e.temp_path
            logger.info(
                "Rejected unsupported file type for %s: %s",
                sanitize_for_log(file.filename), sanitize_for_log(str(e)),
            )
            raise HTTPException(status_code=415, detail="Unsupported file type") from e
        except FileProcessingError as e:
            temp_path = e.temp_path
            logger.warning(
                "File processing failed for %s: %s",
                sanitize_for_log(file.filename), sanitize_for_log(str(e)),
            )
            raise HTTPException(status_code=422, detail="File processing failed") from e
        except Exception as e:
            logger.error(f"Error uploading file: {str(e)}")
            raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")
        finally:
            # Always remove the spool file, even when the persistent copy
            # failed (e.g. ENOSPC). Without this the temp directory leaks.
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError as cleanup_err:
                    logger.warning(
                        "Failed to remove temp upload %s: %s",
                        temp_path, cleanup_err,
                    )
    
    async def process_file_for_agent(
        self, 
        file_path: str, 
        agent: Any
    ) -> str:
        """
        Process file for agent consumption - reuse existing PDF tools
        
        Args:
            file_path: Path to the file
            agent: Agent object
            
        Returns:
            Processed content string
        """
        try:
            # Determine file type from path
            file_type = self._get_file_type_from_path(file_path)
            
            if file_type == "pdf":
                # Use existing PDF tools
                return extract_text_from_pdf(file_path)
            elif file_type in ["txt", "md", "json"]:
                # Read text files directly
                return await read_text(file_path)
            else:
                # For other file types, return basic info
                return f"File: {os.path.basename(file_path)} (type: {file_type})"
                
        except Exception as e:
            logger.error(f"Error processing file for agent: {str(e)}")
            return f"Error processing file: {str(e)}"
    
    async def get_file_reference(self, file_id: str) -> Optional[FileReference]:
        """
        Get file reference by ID
        
        Args:
            file_id: File ID
            
        Returns:
            FileReference or None if not found
        """
        return self._files.get(file_id)

    async def get_session_file(
        self,
        agent_id: int,
        user_context: Optional[Dict],
        conversation_id: Optional[str],
        file_id: str,
    ) -> Optional[FileReference]:
        """Look up ``file_id`` strictly within one ``(agent, user, conversation)`` session.

        Unlike :meth:`get_file_reference` (which indexes the in-memory,
        per-instance ``self._files`` mapping directly by ``file_id`` and
        therefore only ever succeeds inside the exact instance that
        registered the file), this recomputes the session key and
        rehydrates it from the on-disk sidecars first -- the same pattern
        :meth:`list_attached_files` already relies on to see files a
        *different* ``FileManagementService`` instance registered earlier
        in the same turn (e.g. the one ``_finalize_turn`` builds and
        discards internally for ``sync_output_files``).

        The lookup is strictly scoped to the session key derived from
        ``agent_id``/``user_context``/``conversation_id``: a file
        registered under a different agent, user, app or conversation is
        invisible here even if its ``file_id`` is known. The resolved
        ``file_path`` is also verified to still resolve inside
        ``TMP_BASE_FOLDER`` (catching both a tampered/traversal sidecar and
        a symlink that points outside it) before the reference is
        returned; a reference whose path fails that check is treated as
        not found rather than raised.

        Args:
            agent_id: ID of the agent the file was produced for.
            user_context: Caller context used to derive the session key.
            conversation_id: Conversation scope, or ``None`` for a
                conversation-less (global agent) session.
            file_id: The file's id.

        Returns:
            The :class:`FileReference`, or ``None`` if it does not exist in
            this exact session or its path fails the containment check.
        """
        session_key = self._get_session_key(agent_id, user_context, conversation_id)
        await asyncio.to_thread(self._load_session_files, session_key)

        ref = self._files.get(session_key, {}).get(file_id)
        if ref is None or not ref.file_path:
            return None

        try:
            resolve_within(self._tmp_base_folder, ref.file_path)
        except UnsafePathError:
            logger.warning(
                "get_session_file: file_path for file_id=%s escapes TMP_BASE_FOLDER "
                "(tampered sidecar or symlink); treating as not found",
                file_id,
            )
            return None

        return ref

    async def list_attached_files(
        self, 
        agent_id: int, 
        user_context: Dict = None,
        conversation_id: str = None
    ) -> List[Dict[str, Any]]:
        """
        List attached files for a user session, optionally filtered by conversation.
        
        Args:
            agent_id: ID of the agent
            user_context: User context
            conversation_id: Optional conversation ID for conversation-specific files
            
        Returns:
            List of file references
        """
        try:
            # Get session key for this agent, user, and optionally conversation
            session_key = self._get_session_key(agent_id, user_context, conversation_id)

            # Always re-sync from disk. The in-memory cache is per-worker, so
            # an upload handled by worker A is invisible to worker B unless
            # worker B re-reads the on-disk sidecars. The previous guard
            # (only load when the key was missing) was wrong: an earlier
            # listing on worker B would create an empty entry that then
            # masked subsequent disk uploads.
            self._load_session_files(session_key)

            # Return files for this session
            if session_key in self._files:
                files_list = [file_ref.to_dict() for file_ref in self._files[session_key].values()]
                logger.info(f"Returning {len(files_list)} files for session {session_key}")
                for file_data in files_list:
                    logger.info(f"File: {file_data['filename']}, Path: {file_data.get('file_path', 'None')}")
                return files_list
            else:
                return []
            
        except Exception as e:
            logger.error(f"Error listing attached files: {str(e)}")
            return []
    
    async def remove_file(
        self, 
        file_id: str, 
        agent_id: int,
        user_context: Dict = None,
        conversation_id: str = None
    ) -> bool:
        """
        Remove attached file from a session (optionally conversation-specific).
        
        Args:
            file_id: File ID to remove
            agent_id: ID of the agent
            user_context: User context
            conversation_id: Optional conversation ID for conversation-specific files
            
        Returns:
            True if removed successfully
        """
        try:
            # Get session key for this agent, user, and optionally conversation
            session_key = self._get_session_key(agent_id, user_context, conversation_id)

            # Always re-sync from disk so removals work consistently across
            # uvicorn workers (the in-memory cache is per-process).
            self._load_session_files(session_key)

            if session_key in self._files and file_id in self._files[session_key]:
                del self._files[session_key][file_id]
                
                # Also remove from disk
                await self._remove_file_from_disk(session_key, file_id)
                
                logger.info(f"Removed file {file_id} from session {session_key}")
                return True
            else:
                logger.warning(f"File {file_id} not found for removal in session {session_key}")
                return False
                
        except Exception as e:
            logger.error(f"Error removing file: {str(e)}")
            return False
    
    async def register_output_file(
        self,
        file_path: str,
        agent_id: int,
        user_context: Dict = None,
        conversation_id: Optional[str] = None
    ) -> Optional["FileReference"]:
        """
        Register an already-existing file on disk as a FileReference so it appears
        in list_attached_files() and can be downloaded by the user.

        Used by the code interpreter to surface agent-generated output files
        (e.g. modified Excel files, CSVs, charts) in the same UI panel as uploads.

        Args:
            file_path: Absolute path to the file on disk
            agent_id: ID of the agent that generated the file
            user_context: User context
            conversation_id: Optional conversation ID for scoping

        Returns:
            FileReference if registration succeeded, None on error
        """
        try:
            if not os.path.exists(file_path):
                logger.warning(f"register_output_file: file not found at {file_path}")
                return None

            filename = os.path.basename(file_path)
            file_id = str(uuid.uuid4())
            file_size = os.path.getsize(file_path)
            relative_path = os.path.relpath(file_path, self._tmp_base_folder).replace(os.sep, '/')

            detected_type = self._get_file_type(filename)
            file_type = detected_type if detected_type != "unknown" else "output"

            file_ref = FileReference(
                file_id=file_id,
                filename=filename,
                file_type=file_type,
                content=f"Generated file: {filename}",
                file_path=relative_path,
                file_size_bytes=file_size,
                conversation_id=str(conversation_id) if conversation_id else None
            )
            file_ref.processing_status = "ready"

            session_key = self._get_session_key(agent_id, user_context, str(conversation_id) if conversation_id else None)
            if session_key not in self._files:
                self._files[session_key] = {}
            self._files[session_key][file_id] = file_ref

            # Persist metadata so it survives restarts
            session_dir = os.path.join(self._persistent_dir, session_key)
            os.makedirs(session_dir, exist_ok=True)
            metadata_file = os.path.join(session_dir, f"{file_id}.json")
            await write_json(metadata_file, file_ref.to_dict())
            # _load_session_files requires a matching .content file to load the entry
            content_file = os.path.join(session_dir, f"{file_id}.content")
            await write_text(content_file, file_ref.content)

            logger.info(f"Registered output file {filename} (id={file_id}) for session {session_key}")
            return file_ref

        except Exception as e:
            logger.error(f"Error registering output file: {e}")
            return None

    def _get_file_type(self, filename: str) -> str:
        """Get file type from filename"""
        if not filename:
            return "unknown"
        
        ext = os.path.splitext(filename)[1].lower()
        
        # PDF files
        if ext == '.pdf':
            return "pdf"
        
        # Text files
        elif ext in ['.txt', '.md', '.json', '.csv']:
            return "text"
        
        # Image files
        elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
            return "image"
        
        # Document files
        elif ext in ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']:
            return "document"
        
        else:
            return "unknown"
    
    def _get_file_type_from_path(self, file_path: str) -> str:
        """Get file type from file path"""
        return self._get_file_type(os.path.basename(file_path))
    
    async def _process_file_content(
        self, file: UploadFile, file_type: str, *, strict: bool = False
    ) -> tuple[str, str, int]:
        """
        Process file content based on file type

        Args:
            file: Uploaded file
            file_type: Type of file
            strict: When True, never return a placeholder/"not implemented"
                content string: raise UnsupportedFileTypeError for an
                unsupported type, or FileProcessingError if extraction fails
                for an otherwise-supported type. See upload_file's docstring.

        Returns:
            Tuple of (processed_content, temp_file_path, file_size_bytes)
        """
        try:
            # Save file temporarily and get size
            temp_path, file_size = await self._save_uploaded_file_with_size(file)

            try:
                if file_type == "pdf":
                    # Use existing PDF tools
                    content = extract_text_from_pdf(temp_path)
                    return content, temp_path, file_size

                elif file_type == "text":
                    # Read text files
                    content = await read_text(temp_path)
                    return content, temp_path, file_size

                elif file_type == "image":
                    # For images, return basic info (in production, use OCR).
                    # Not a lie under strict=True: images are genuinely usable —
                    # AgentExecutionService sends them to a vision model via
                    # file_path/base64, never via this content string.
                    content = f"Image file: {file.filename} (OCR processing not implemented)"
                    return content, temp_path, file_size

                elif file_type == "document" and file.filename.lower().endswith(".docx"):
                    import docx2txt
                    content = docx2txt.process(temp_path) or ""
                    return content, temp_path, file_size

                elif file_type == "document":
                    # .doc / spreadsheets / presentations: no text extraction yet
                    if strict:
                        raise UnsupportedFileTypeError(
                            f"Document type not supported in strict mode: {file.filename}",
                            temp_path=temp_path,
                        )
                    content = f"Document file: {file.filename} (Document processing not implemented)"
                    return content, temp_path, file_size

                else:
                    # Unrecognized extension.
                    if strict:
                        raise UnsupportedFileTypeError(
                            f"Unrecognized file type: {file.filename}", temp_path=temp_path
                        )
                    content = f"File: {file.filename} (type: {file_type})"
                    return content, temp_path, file_size

            except UnsupportedFileTypeError:
                raise
            except Exception as e:
                logger.error(f"Error processing file content: {str(e)}")
                if strict:
                    raise FileProcessingError(str(e), temp_path=temp_path) from e
                return f"Error processing file: {str(e)}", temp_path, file_size

        except (UnsupportedFileTypeError, FileProcessingError):
            raise
        except Exception as e:
            logger.error(f"Error processing file content: {str(e)}")
            if strict:
                # _save_uploaded_file_with_size itself failed: no temp_path exists yet.
                raise FileProcessingError(str(e), temp_path=None) from e
            return f"Error processing file: {str(e)}", None, 0
    
    async def _save_uploaded_file_with_size(self, file: UploadFile) -> tuple[str, int]:
        """Save uploaded file to temporary location and return path with file size"""
        # Create temporary file in TMP_BASE_FOLDER/uploads
        suffix = os.path.splitext(file.filename)[1] if file.filename else ""
        content = await file.read()
        return await write_temp_file(content, suffix=suffix, dir=self._temp_dir), len(content)
    
    async def _save_uploaded_file(self, file: UploadFile) -> str:
        """Save uploaded file to temporary location (legacy method for compatibility)"""
        path, _ = await self._save_uploaded_file_with_size(file)
        return path
    
    def _get_session_key(self, agent_id: int, user_context: Dict = None, conversation_id: str = None) -> str:
        """
        Generate session key for agent, user, and optionally conversation combination.
        
        When conversation_id is provided, files are isolated to that specific conversation.
        This allows users to have separate file contexts for different conversations with the same agent.
        
        Args:
            agent_id: ID of the agent
            user_context: User context (api_key, user_id, etc.)
            conversation_id: Optional conversation ID for conversation-specific file isolation
            
        Returns:
            Session key string
        """
        if user_context:
            user_id = user_context.get('user_id', 'anonymous')
            app_id = user_context.get('app_id', 'default')
            # Check if conversation_id is in user_context or passed explicitly
            conv_id = conversation_id or user_context.get('conversation_id')
            
            if conv_id:
                # Conversation-specific file storage
                return f"agent_{agent_id}_user_{user_id}_app_{app_id}_conv_{conv_id}"
            else:
                # Global agent session (files shared across all conversations)
                return f"agent_{agent_id}_user_{user_id}_app_{app_id}"
        else:
            return f"agent_{agent_id}_anonymous"

    @staticmethod
    def _resolve_storage_strategy(
        has_memory: bool,
        conversation_id: Optional[int],
    ) -> str:
        """Decide whether an upload should be stored as ephemeral or persistent.

        Persistent storage is only chosen when both conditions hold:
        - the target agent persists conversation state (``has_memory=True``)
        - the caller supplied an explicit ``conversation_id``

        Either condition missing implies the upload is for a single turn
        only (e.g. one-shot Vision API call) and qualifies as ephemeral.
        """
        if has_memory and conversation_id is not None:
            return STORAGE_STRATEGY_PERSISTENT
        return STORAGE_STRATEGY_EPHEMERAL

    async def _save_file_to_disk(
        self,
        session_key: str,
        file_id: str,
        file_ref: FileReference,
        original_file_path: str = None,
        conversation_id: Optional[int] = None,
        storage_strategy: str = STORAGE_STRATEGY_PERSISTENT,
    ):
        """Save the uploaded file and its sidecars under the right directory.

        Layout:

        - ``ephemeral``: original file, ``{file_id}.json`` and
          ``{file_id}.content`` are co-located under
          ``ephemeral/{session_key}/`` so cleanup is a single ``rmdir``.
        - ``persistent`` with ``conversation_id``: keeps the legacy layout —
          original file goes to ``conversations/{conversation_id}/`` while
          metadata sidecars stay in ``persistent/{session_key}/`` so
          ``_load_session_files`` keeps working.
        - ``persistent`` without ``conversation_id``: everything in
          ``persistent/{session_key}/`` (same as before).
        """
        try:
            base_dir = (
                self._ephemeral_dir
                if storage_strategy == STORAGE_STRATEGY_EPHEMERAL
                else self._persistent_dir
            )
            session_dir = resolve_within(base_dir, session_key)
            os.makedirs(session_dir, exist_ok=True)

            # Save original file FIRST (to set file_path before saving metadata)
            if original_file_path and os.path.exists(original_file_path):
                # Ephemeral files always co-locate with their sidecars; this
                # keeps cleanup atomic. Persistent + conversation keeps the
                # legacy `conversations/{id}/` layout.
                if storage_strategy == STORAGE_STRATEGY_EPHEMERAL:
                    target_dir = session_dir
                elif conversation_id:
                    target_dir = resolve_within(
                        self._tmp_base_folder, "conversations", str(conversation_id),
                    )
                else:
                    target_dir = session_dir

                os.makedirs(target_dir, exist_ok=True)

                # Use the original user-facing filename so the code interpreter can
                # reference files by the name the user knows (e.g. 'report.xlsx').
                # Path separators are stripped, and the result must stay inside
                # target_dir (rejects names such as '..').
                safe_filename = file_ref.filename.replace('/', '_').replace('\\', '_')
                original_file = resolve_within(target_dir, safe_filename)
                if original_file == target_dir:
                    raise ValueError(f"Invalid filename: {file_ref.filename!r}")

                shutil.copy2(original_file_path, original_file)

                # Calculate relative path from TMP_BASE_FOLDER
                relative_path = os.path.relpath(original_file, self._tmp_base_folder)
                # Ensure forward slashes for URLs
                file_ref.file_path = relative_path.replace(os.sep, '/')

                logger.info(
                    "Saved file as '%s' in %s (relative: %s, strategy: %s)",
                    safe_filename, target_dir, relative_path, storage_strategy,
                )
                logger.info(f"FileReference file_path set to: {file_ref.file_path}")

            # Save file metadata AFTER setting file_path
            metadata_file = resolve_within(session_dir, f"{file_id}.json")
            await write_json(metadata_file, file_ref.to_dict())

            # Save file content (extracted text)
            content_file = resolve_within(session_dir, f"{file_id}.content")
            await write_text(content_file, file_ref.content)

            logger.info(
                "Saved file %s to disk: %s (strategy: %s)",
                file_id, session_dir, storage_strategy,
            )

        except Exception as e:
            logger.error(f"Error saving file to disk: {str(e)}")

    async def cleanup_ephemeral_refs(self, refs: List["FileReference"]) -> None:
        """Best-effort removal of ephemeral artifacts for a chat turn.

        Idempotent: silently skips refs that are persistent, already removed,
        or missing the internal ``_session_key`` annotation. Designed to be
        called from a router's ``finally`` block so a single request never
        leaks files.

        Each ephemeral ref has at most three on-disk artifacts to clean:
        the original file (via ``file_path``), the ``{file_id}.json``
        metadata sidecar, and the ``{file_id}.content`` sidecar — all under
        ``ephemeral/{session_key}/``. After removing the per-file artifacts
        the session directory is removed if it becomes empty.
        """
        session_keys_seen: set = set()
        removed_count = 0
        skipped_count = 0
        for ref in refs:
            if getattr(ref, "storage_strategy", STORAGE_STRATEGY_PERSISTENT) != STORAGE_STRATEGY_EPHEMERAL:
                skipped_count += 1
                continue
            session_key = getattr(ref, "_session_key", None)
            file_id = ref.file_id
            try:
                # Original file (relative to tmp_base_folder).
                if ref.file_path:
                    abs_path = os.path.join(self._tmp_base_folder, ref.file_path)
                    if os.path.isfile(abs_path):
                        os.remove(abs_path)
                # Sidecars live next to each other under ephemeral/{session_key}/.
                if session_key:
                    session_dir = os.path.join(self._ephemeral_dir, session_key)
                    for suffix in (".json", ".content"):
                        sidecar = os.path.join(session_dir, f"{file_id}{suffix}")
                        if os.path.isfile(sidecar):
                            os.remove(sidecar)
                    session_keys_seen.add(session_key)
                # Drop in-memory registry entry too so a subsequent
                # list_attached_files() in the same process doesn't surface it.
                if session_key and session_key in self._files:
                    self._files[session_key].pop(file_id, None)
                removed_count += 1
            except OSError as exc:
                logger.warning(
                    "Best-effort ephemeral cleanup failed for %s: %s",
                    file_id, exc,
                )

        if removed_count or skipped_count:
            logger.info(
                "cleanup_ephemeral_refs: removed=%d ephemeral, kept=%d persistent",
                removed_count, skipped_count,
            )

        # Remove empty session directories so the ephemeral root stays tidy.
        for session_key in session_keys_seen:
            session_dir = os.path.join(self._ephemeral_dir, session_key)
            try:
                if os.path.isdir(session_dir) and not os.listdir(session_dir):
                    os.rmdir(session_dir)
            except OSError:
                # Concurrent uploads from the same session may have re-created
                # files inside the directory between the listdir and rmdir.
                # The background sweep will catch this on the next pass.
                pass

    def _load_session_files(self, session_key: str):
        """Load existing files from disk for a specific session.

        Sidecar metadata (.json/.content) may live under either
        ``persistent/{session_key}/`` or ``ephemeral/{session_key}/`` since
        the storage strategy is decided per-upload. We have to look in both
        so the visible file list survives across uvicorn workers (the
        in-memory ``self._files`` cache is per-process, but the on-disk
        layout is shared).
        """
        try:
            session_path = None
            loaded_strategy = STORAGE_STRATEGY_PERSISTENT
            for base_dir, strategy in (
                (self._persistent_dir, STORAGE_STRATEGY_PERSISTENT),
                (self._ephemeral_dir, STORAGE_STRATEGY_EPHEMERAL),
            ):
                if not os.path.exists(base_dir):
                    continue
                try:
                    # session_key embeds caller-supplied ids: never probe a path
                    # outside the storage dir (filesystem oracle).
                    candidate = resolve_within(base_dir, session_key)
                except UnsafePathError:
                    return
                if os.path.isdir(candidate):
                    session_path = candidate
                    loaded_strategy = strategy
                    # Prefer persistent if it exists; ephemeral is only checked
                    # when persistent does not have the session.
                    break
            if session_path is None:
                return

            # Initialize session if not exists
            if session_key not in self._files:
                self._files[session_key] = {}

            # Load files for this session
            for filename in os.listdir(session_path):
                if filename.endswith('.json'):
                    file_id = filename[:-5]  # Remove .json extension
                    metadata_file = os.path.join(session_path, filename)
                    content_file = os.path.join(session_path, f"{file_id}.content")

                    if os.path.exists(content_file):
                        try:
                            with open(metadata_file, 'r') as f:
                                metadata = json.load(f)

                            with open(content_file, 'r', encoding='utf-8') as f:
                                content = f.read()

                            # Recreate FileReference with visual feedback data
                            file_ref = FileReference(
                                file_id=metadata['file_id'],
                                filename=metadata['filename'],
                                file_type=metadata['file_type'],
                                content=content,
                                file_path=metadata.get('file_path'),
                                file_size_bytes=metadata.get('file_size_bytes'),
                                conversation_id=metadata.get('conversation_id')
                            )
                            # Re-stamp the lifecycle markers that the original
                            # upload set on the in-memory ref. Without these
                            # cleanup_ephemeral_refs cannot tell ephemeral
                            # refs apart from persistent ones when the chat
                            # happens in a later request than the upload.
                            file_ref.storage_strategy = loaded_strategy
                            file_ref._session_key = session_key
                            
                            # If file_path is missing, try to regenerate it
                            if not file_ref.file_path:
                                # Search: session dir (UUID-named legacy files) and
                                # conversation dir (original-named files)
                                conv_id = metadata.get('conversation_id')
                                search_dirs = [session_path]
                                if conv_id:
                                    search_dirs.append(os.path.join(
                                        self._tmp_base_folder, "conversations", str(conv_id)
                                    ))
                                found = False
                                for search_dir in search_dirs:
                                    if not os.path.isdir(search_dir):
                                        continue
                                    for fname in os.listdir(search_dir):
                                        # Legacy: UUID prefix match; new: original filename match
                                        is_match = (
                                            fname.startswith(file_id)
                                            or fname == metadata.get('filename')
                                        )
                                        if is_match and not fname.endswith(('.json', '.content')):
                                            candidate = os.path.join(search_dir, fname)
                                            if os.path.exists(candidate):
                                                relative_path = os.path.relpath(candidate, self._tmp_base_folder)
                                                file_ref.file_path = relative_path
                                                metadata['file_path'] = relative_path
                                                with open(metadata_file, 'w') as f:
                                                    json.dump(metadata, f, indent=2)
                                                logger.info(f"Regenerated file_path for {file_id}: {relative_path}")
                                                found = True
                                                break
                                    if found:
                                        break
                            
                            self._files[session_key][file_id] = file_ref
                            logger.info(f"Loaded persistent file {file_id} for session {session_key}")
                            logger.info(f"Loaded file_path: {file_ref.file_path}")
                            
                        except Exception as e:
                            logger.error(f"Error loading file {file_id}: {str(e)}")
                            
            logger.info(
                "Loaded %d persistent files for session %s",
                len(self._files.get(session_key, {})), sanitize_for_log(session_key),
            )

        except Exception:
            logger.exception(
                "Error loading persistent files for session %s", sanitize_for_log(session_key)
            )

    async def remove_files(
        self,
        file_ids: List[str],
        agent_id: int,
        user_context: Dict = None,
        conversation_id: Optional[str] = None,
    ) -> None:
        """Remove several files (metadata + stored bytes) from one session."""
        session_key = self._get_session_key(agent_id, user_context, conversation_id)
        for file_id in file_ids:
            self._files.get(session_key, {}).pop(file_id, None)
            await self._remove_file_from_disk(session_key, file_id)

    def delete_conversation_storage(
        self,
        agent_id: int,
        user_context: Dict = None,
        conversation_id: Optional[str] = None,
    ) -> None:
        """Delete every file of a conversation: its session metadata and its working directory."""
        session_key = self._get_session_key(agent_id, user_context, conversation_id)
        self._files.pop(session_key, None)
        paths = [os.path.join(self._persistent_dir, session_key)]
        if conversation_id:
            paths.append(os.path.join(self._tmp_base_folder, "conversations", str(conversation_id)))
        for path in paths:
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
            except Exception as e:
                logger.error(f"Error deleting conversation storage {path}: {e}")

    def delete_agent_storage(self, agent_id: int, conversation_ids: List[int]) -> None:
        """Delete every file stored for an agent: all its sessions and its conversations' working directories."""
        # Session keys are "agent_{id}_user_…" / "agent_{id}_anonymous"; the trailing "_" keeps agent 1 from matching 12.
        prefix = f"agent_{agent_id}_"
        paths = []
        if os.path.isdir(self._persistent_dir):
            paths.extend(
                os.path.join(self._persistent_dir, name)
                for name in os.listdir(self._persistent_dir)
                if name.startswith(prefix)
            )
        paths.extend(
            os.path.join(self._tmp_base_folder, "conversations", str(conversation_id))
            for conversation_id in conversation_ids
        )
        for path in paths:
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
            except OSError as e:
                logger.error(f"Error deleting agent storage {path}: {e}")

    async def _remove_file_from_disk(self, session_key: str, file_id: str):
        """Remove file from disk"""
        try:
            session_dir = resolve_within(self._persistent_dir, session_key)
            metadata_file = resolve_within(session_dir, f"{file_id}.json")
            content_file = resolve_within(session_dir, f"{file_id}.content")

            # Read metadata BEFORE deleting it to locate the original file
            # (original files stored in conversations/ dir have a relative file_path)
            if os.path.exists(metadata_file):
                try:
                    metadata = await read_json(metadata_file)
                    file_path = metadata.get('file_path')
                    if file_path:
                        # file_path is read back from a sidecar, so it must
                        # still resolve inside TMP_BASE_FOLDER before deleting.
                        abs_path = resolve_within(self._tmp_base_folder, file_path)
                        if os.path.isfile(abs_path):
                            os.remove(abs_path)
                            logger.info(f"Removed original file {abs_path}")
                except Exception as e:
                    logger.error(f"Error reading metadata to locate original file: {e}")
                os.remove(metadata_file)

            if os.path.exists(content_file):
                os.remove(content_file)

            # Fallback: also remove any file with the file_id prefix inside session_dir
            if os.path.exists(session_dir):
                for filename in os.listdir(session_dir):
                    if filename.startswith(file_id) and not filename.endswith(('.json', '.content')):
                        original_file = resolve_within(session_dir, filename)
                        if os.path.isfile(original_file):
                            os.remove(original_file)
                            logger.info(f"Removed original file {filename}")

            logger.info(f"Removed file {file_id} from disk")

        except Exception as e:
            logger.error(f"Error removing file from disk: {str(e)}")

    async def sync_output_files(
        self,
        working_dir: str,
        agent_id: int,
        user_context: Dict = None,
        conversation_id: Optional[str] = None,
        exclude_filenames: set = None,
    ) -> List["FileReference"]:
        """
        Scan working_dir for files that are not yet registered and register them
        as output FileReferences.  Called after each agent execution turn so that
        files saved by the python_repl tool appear automatically in the UI panel.

        Args:
            working_dir: Directory where the sandbox writes output files
            agent_id: ID of the agent
            user_context: User context
            conversation_id: Conversation scope
            exclude_filenames: Set of filenames that existed before the current
                execution turn — these are skipped to avoid registering stale
                files left over from a previous conversation.

        Returns:
            List of newly registered FileReferences (may be empty)
        """
        try:
            if not os.path.exists(working_dir):
                return []

            _exclude = exclude_filenames if exclude_filenames is not None else set()

            # When exclude_filenames is provided we already know which files
            # existed before the current execution turn, so we can skip the
            # expensive _load_session_files() call that reads every historical
            # file into memory.  This avoids O(N) memory/IO overhead when the
            # persistent directory has accumulated thousands of files from
            # previous agent calls (e.g. vision agent via public API).
            session_key = self._get_session_key(agent_id, user_context, conversation_id)
            if exclude_filenames is None:
                if session_key not in self._files:
                    self._load_session_files(session_key)

                registered_paths = {
                    ref.file_path
                    for ref in self._files.get(session_key, {}).values()
                    if ref.file_path
                }
            else:
                registered_paths = set()

            newly_registered: List[FileReference] = []
            for fname in os.listdir(working_dir):
                # Skip hidden files and Python temp scripts
                if fname.startswith('.') or fname.endswith('.py'):
                    continue
                # Skip files that existed before the current execution turn
                if fname in _exclude:
                    continue
                abs_path = os.path.join(working_dir, fname)
                if not os.path.isfile(abs_path):
                    continue
                rel_path = os.path.relpath(abs_path, self._tmp_base_folder).replace(os.sep, '/')
                if rel_path in registered_paths:
                    continue
                ref = await self.register_output_file(
                    file_path=abs_path,
                    agent_id=agent_id,
                    user_context=user_context,
                    conversation_id=conversation_id,
                )
                if ref:
                    newly_registered.append(ref)

            if newly_registered:
                logger.info(
                    "sync_output_files: registered %d new file(s) in %s for session %s",
                    len(newly_registered), working_dir, session_key,
                )
            return newly_registered

        except Exception as e:
            logger.error("sync_output_files error: %s", e)
            return []

    async def resolve_chat_files(
        self,
        files: Optional[List[UploadFile]],
        file_reference_ids: Optional[List[str]],
        agent_id: int,
        user_context: Dict,
        conversation_id: Optional[int],
        has_memory: bool = False,
    ) -> List["FileReference"]:
        """Upload new files and merge with the existing attached files for a chat turn.

        This is the single canonical implementation that replaces the three
        near-identical helpers previously scattered across the internal and
        public-API routers.

        Args:
            files: New files uploaded with the current request (may be None or empty).
            file_reference_ids: Optional list of file_id strings the caller wants to
                include.  When None all currently attached files are included; when
                an empty list is provided no pre-existing files are included.
            agent_id: ID of the agent receiving the files.
            user_context: Caller context dict (``user_id``, ``app_id``, …).
            conversation_id: Optional conversation ID used to scope file storage.
            has_memory: Whether the target agent persists conversation state.
                Propagated to :meth:`upload_file` so it can pick the right
                storage strategy. Callers should pass ``agent.has_memory``;
                the default ``False`` keeps callers that have not been
                migrated yet backward-compatible (their uploads will be
                treated as ephemeral and cleaned up by the worker).

        Returns:
            Ordered list of :class:`FileReference` objects ready to pass to
            ``AgentExecutionService.execute_agent_chat_with_file_refs``.
            Refs from new uploads carry a ``storage_strategy`` attribute so
            the caller can invoke :meth:`cleanup_ephemeral_refs` in a
            ``finally`` block.
        """
        all_refs: List[FileReference] = []
        uploaded_ids: set = set()

        # 1. Upload any newly-attached files
        if files:
            for upload_file in files:
                if upload_file.filename:
                    try:
                        file_ref = await self.upload_file(
                            file=upload_file,
                            agent_id=agent_id,
                            user_context=user_context,
                            conversation_id=conversation_id,
                            has_memory=has_memory,
                        )
                        # Tells agent execution to send the full content this
                        # turn — the file was never indexed by an attach step.
                        file_ref.uploaded_this_turn = True
                        all_refs.append(file_ref)
                        uploaded_ids.add(file_ref.file_id)
                    except Exception as exc:
                        logger.error(
                            "Error uploading file %s: %s", upload_file.filename, exc
                        )

        # 2. Fetch existing attached files (scoped to conversation when available)
        existing_files = await self.list_attached_files(
            agent_id=agent_id,
            user_context=user_context,
            conversation_id=str(conversation_id) if conversation_id else None,
        )

        # 3. Optionally filter to a specific subset
        if file_reference_ids is not None:
            requested_ids = set(file_reference_ids)
            existing_files = [
                f for f in existing_files if f["file_id"] in requested_ids
            ]
            logger.info(
                "Filtered to %d file(s) based on file_reference_ids", len(existing_files)
            )

        # 4. Append existing files not already added via upload.
        #    Prefer the in-memory FileReference (already populated by step 2's
        #    list_attached_files -> _load_session_files): it carries the
        #    ``storage_strategy`` and ``_session_key`` annotations that the
        #    cleanup pass needs. Rebuilding from the dict would drop those.
        session_key = self._get_session_key(
            agent_id,
            user_context,
            str(conversation_id) if conversation_id else None,
        )
        cached_refs = self._files.get(session_key, {})
        for file_data in existing_files:
            file_id = file_data["file_id"]
            if file_id in uploaded_ids:
                continue
            cached = cached_refs.get(file_id)
            if cached is not None:
                all_refs.append(cached)
            else:
                all_refs.append(
                    FileReference(
                        file_id=file_id,
                        filename=file_data["filename"],
                        file_type=file_data["file_type"],
                        content=file_data["content"],
                        file_path=file_data.get("file_path"),
                    )
                )

        return all_refs

    def get_file_stats(self) -> Dict[str, Any]:
        """Get file management statistics"""
        try:
            file_types = {}
            total_size = 0
            total_files = 0
            
            for session_files in self._files.values():
                for file_ref in session_files.values():
                    file_type = file_ref.file_type
                    file_types[file_type] = file_types.get(file_type, 0) + 1
                    total_size += len(file_ref.content)
                    total_files += 1
            
            return {
                "total_files": total_files,
                "total_sessions": len(self._files),
                "file_types": file_types,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2)
            }
            
        except Exception as e:
            logger.error(f"Error getting file stats: {str(e)}")
            return {} 