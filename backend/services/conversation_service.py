import asyncio
import uuid
import ast
import json
import re
from typing import List, Optional, Dict
from numpy import isin
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
from datetime import datetime

from models.conversation import Conversation, ConversationSource
from repositories.conversation_repository import ConversationRepository
from models.agent import Agent
from schemas.conversation_schemas import ConversationCreate, ConversationUpdate
from services.agent_cache_service import CheckpointerCacheService
from utils.logger import get_logger
from utils.security import hash_api_key
from lks_idprovider import AuthContext

logger = get_logger(__name__)

# Strong refs to fire-and-forget checkpoint cleanups so they are not garbage-collected mid-run.
_pending_cleanups: set = set()


async def _resolve_image_placeholders(
    content: str,
    agent_id: int,
    user_context: dict,
    conversation_id: str = None,
) -> str:
    """Replace [IMAGE:{block_id}] markers with inline file:// markdown.

    When an AI message contained an image_generation_call block the cache
    service now emits [IMAGE:{block_id}] instead of plain text.  We resolve
    that marker to the registered FileReference so the frontend can render
    the image inline.  Falls back to '[Imagen generada]' when the file is
    not found (e.g. older messages saved before block_id was embedded in
    the filename).
    """
    if "[IMAGE:" not in content:
        return content

    from services.file_management_service import FileManagementService
    file_service = FileManagementService()
    # Try conversation-scoped first; fall back to global session for legacy files
    files = await file_service.list_attached_files(agent_id, user_context, conversation_id)
    if not files and conversation_id:
        files = await file_service.list_attached_files(agent_id, user_context, None)

    def replace_marker(m: re.Match) -> str:
        block_id = m.group(1)
        for f in files:
            fname = f.get("filename", "")
            # The filename was generated as generated_image_{block_id[:48]}.png
            if block_id[:48] in fname:
                file_id = f.get("file_id", "")
                return f"![{fname}](file://{file_id})"
        return "[Imagen generada]"

    return re.sub(r'\[IMAGE:([^\]]+)\]', replace_marker, content)


class ConversationService:
    """Service for managing user conversations with agents"""
    
    @staticmethod
    def create_conversation(
        db: Session,
        agent_id: int,
        user_context: Dict,
        title: Optional[str] = None,
        source: ConversationSource = ConversationSource.PLAYGROUND,
        scheduled_task_id: Optional[int] = None,
    ) -> Conversation:
        """
        Create a new conversation for a user and agent
        
        Args:
            db: Database session
            agent_id: ID of the agent
            user_context: User context (user_id or api_key)
            title: Optional title for the conversation
            
        Returns:
            Created Conversation object
        """
        # Generate unique conversation UUID
        conversation_uuid = str(uuid.uuid4())
        session_id = f"conv_{agent_id}_{conversation_uuid}"
        
        # Extract user information from context
        user_id = user_context.get('user_id')
        api_key = user_context.get('api_key')
        api_key_hash = None
        
        # For API key users, user_id is a string like "apikey_xxx" 
        # The database expects an integer, so we set it to None for API key users
        # They are identified by api_key_hash instead
        if isinstance(user_id, str) and (user_id.startswith('apikey_') or not user_id.isdigit()):
            user_id = None
        
        if api_key:
            # Hash the API key for tracking (without storing the actual key)
            api_key_hash = hash_api_key(api_key)
        
        # Generate auto-title if not provided
        if not title:
            title = f"Conversación {datetime.utcnow().strftime('%d/%m/%Y %H:%M')}"
        
        # Create conversation
        conversation = Conversation(
            agent_id=agent_id,
            user_id=user_id,
            session_id=session_id,
            title=title,
            api_key_hash=api_key_hash,
            source=source,
            scheduled_task_id=scheduled_task_id,
            message_count=0
        )
        
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        
        logger.info(f"Created conversation {conversation.conversation_id} for agent {agent_id}")
        return conversation
    
    @staticmethod
    def get_conversation(
        db: Session,
        conversation_id: int,
        user_context: Dict,
        agent_id: int = None
    ) -> Optional[Conversation]:
        """
        Get a conversation by ID with user validation

        Args:
            db: Database session
            conversation_id: ID of the conversation
            user_context: User context for validation
            agent_id: Optional agent ID to validate the conversation belongs to this agent

        Returns:
            Conversation object or None if not found/unauthorized
        """
        query = db.query(Conversation).filter(
            Conversation.conversation_id == conversation_id
        )
        if agent_id is not None:
            query = query.filter(Conversation.agent_id == agent_id)
        conversation = query.first()
        
        if not conversation:
            return None
        
        # Validate user access
        if not ConversationService._validate_user_access(conversation, user_context):
            logger.warning(f"Unauthorized access attempt to conversation {conversation_id}")
            return None
        
        return conversation

    @staticmethod
    def get_marketplace_conversation(
        db: Session,
        conversation_id: int,
        user_id: int,
    ) -> Optional[Conversation]:
        """
        Get a marketplace conversation by ID that belongs to a specific user.

        Args:
            db: Database session
            conversation_id: Conversation ID
            user_id: Owner user ID

        Returns:
            Conversation object or None if not found
        """
        return ConversationRepository.get_marketplace_conversation(db, conversation_id, user_id)
    
    @staticmethod
    def list_conversations(
        db: Session,
        agent_id: int,
        user_context: AuthContext|dict,
        limit: int = 50,
        offset: int = 0
    ) -> tuple[List[Conversation], int]:
        """
        List conversations for a user with a specific agent
        
        Args:
            db: Database session
            agent_id: ID of the agent
            user_context: User context
            limit: Maximum number of results
            offset: Pagination offset
            
        Returns:
            Tuple of (list of conversations, total count)
        """
        # Build query with user filtering
        query = db.query(Conversation).filter(Conversation.agent_id == agent_id)
        
        # Filter by user - handle both AuthContext and dict
        if isinstance(user_context, AuthContext):
            user_id = int(user_context.identity.id)
            query = query.filter(Conversation.user_id == user_id)
        elif isinstance(user_context, dict) and user_context.get('api_key'):
            # API key users are identified by api_key_hash, not user_id
            api_key = user_context.get('api_key')
            api_key_hash = hash_api_key(api_key)
            query = query.filter(Conversation.api_key_hash == api_key_hash)
        elif isinstance(user_context, dict) and user_context.get('user_id'):
            # OAuth user via dict context
            user_id = user_context.get('user_id')
            # Ensure it's a valid integer user_id, not an API key string
            if isinstance(user_id, int) or (isinstance(user_id, str) and user_id.isdigit()):
                query = query.filter(Conversation.user_id == int(user_id))
            else:
                # Invalid user_id format
                return [], 0
        else:
            # No valid user context
            return [], 0
        
        # Get total count
        total = query.count()
        
        # Get paginated results, ordered by most recent
        conversations = query.order_by(desc(Conversation.updated_at)).offset(offset).limit(limit).all()
        
        logger.info(f"Listed {len(conversations)} conversations for agent {agent_id} (total: {total})")
        return conversations, total
    
    @staticmethod
    def update_conversation(
        db: Session,
        conversation_id: int,
        user_context: Dict,
        update_data: ConversationUpdate
    ) -> Optional[Conversation]:
        """
        Update a conversation
        
        Args:
            db: Database session
            conversation_id: ID of the conversation
            user_context: User context for validation
            update_data: Update data
            
        Returns:
            Updated Conversation object or None if not found/unauthorized
        """
        conversation = ConversationService.get_conversation(db, conversation_id, user_context)
        
        if not conversation:
            return None
        
        # Update fields
        if update_data.title is not None:
            conversation.title = update_data.title
        if update_data.last_message is not None:
            conversation.last_message = update_data.last_message
        if update_data.message_count is not None:
            conversation.message_count = update_data.message_count
        
        conversation.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(conversation)
        
        logger.info(f"Updated conversation {conversation_id}")
        return conversation
    
    @staticmethod
    def release_conversation_resources(db: Session, conversation: Conversation) -> None:
        """Drop a conversation's temp media (silo + repo + vectors) and its sandbox. Best effort."""
        conversation_id = conversation.conversation_id
        try:
            from services.playground_media_service import PlaygroundMediaService
            PlaygroundMediaService.cleanup(
                conversation.agent.app_id, conversation.agent_id, conversation.session_id, db
            )
            logger.info(
                f"Cleaned up playground media for conversation {conversation_id} "
                f"(agent {conversation.agent_id}, session {conversation.session_id})"
            )
        except Exception as e:
            logger.error(f"Error cleaning up playground media during delete: {e}")

        # Sandbox key: conv_{agent_id}_{conversation_id}
        try:
            from services.sandbox_session_service import sandbox_session_service, SandboxSessionService
            sandbox_key = SandboxSessionService.session_key(conversation.agent_id, conversation_id)
            sandbox_session_service.destroy(sandbox_key)
            conversation.sandbox_session_id = None
            conversation.sandbox_state = None
        except Exception as e:
            logger.error(f"Error destroying sandbox on conversation delete: {e}")

    @staticmethod
    async def delete_conversation_history(conversation: Conversation) -> None:
        """Delete the conversation's LangGraph checkpoints. Best effort."""
        await ConversationService.delete_thread_history(conversation.agent_id, conversation.session_id)

    @staticmethod
    async def delete_thread_history(agent_id: int, session_id: str) -> None:
        """Delete the checkpoints of thread_{agent_id}_{session_id}. Best effort."""
        try:
            await CheckpointerCacheService.invalidate_checkpointer_async(agent_id=agent_id, session_id=session_id)
            logger.info(f"Deleted chat history thread_{agent_id}_{session_id}")
        except Exception as e:
            logger.error(f"Error deleting chat history: {e}")

    @staticmethod
    async def delete_thread_histories(threads: List[tuple]) -> None:
        """Delete the checkpoints of each (agent_id, session_id) thread. Best effort."""
        for agent_id, session_id in threads:
            await ConversationService.delete_thread_history(agent_id, session_id)

    @staticmethod
    def delete_thread_histories_in_background(threads: List[tuple]) -> None:
        """Delete checkpoints from sync code: as a task on the running loop, or inline if there is none."""
        if not threads:
            return
        coro = ConversationService.delete_thread_histories(threads)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(coro)
            return
        task = loop.create_task(coro)
        _pending_cleanups.add(task)
        task.add_done_callback(_pending_cleanups.discard)

    @staticmethod
    def purge_for_agent(db: Session, agent_id: int) -> int:
        """Delete every conversation of an agent with its media, sandbox, files and checkpoints.

        Called from AgentService.delete_agent before the agent row goes. Commits.
        Returns the number of conversations deleted.
        """
        from services.file_management_service import FileManagementService

        conversations = db.query(Conversation).filter(Conversation.agent_id == agent_id).all()
        threads = []
        for conversation in conversations:
            ConversationService.release_conversation_resources(db, conversation)
            threads.append((conversation.agent_id, conversation.session_id))
        conversation_ids = [conversation.conversation_id for conversation in conversations]
        for conversation in conversations:
            db.delete(conversation)
        db.commit()

        try:
            FileManagementService().delete_agent_storage(agent_id, conversation_ids)
        except Exception as e:
            logger.error(f"Error deleting file storage of agent {agent_id}: {e}")
        ConversationService.delete_thread_histories_in_background(threads)
        logger.info(f"Deleted {len(conversations)} conversations of agent {agent_id}")
        return len(conversations)

    @staticmethod
    async def delete_conversation(
        db: Session,
        conversation_id: int,
        user_context: Dict
    ) -> bool:
        """
        Delete a conversation and its associated chat history
        
        Args:
            db: Database session
            conversation_id: ID of the conversation
            user_context: User context for validation
            
        Returns:
            True if deleted successfully, False otherwise
        """
        conversation = ConversationService.get_conversation(db, conversation_id, user_context)
        
        if not conversation:
            return False
        
        ConversationService.release_conversation_resources(db, conversation)
        await ConversationService.delete_conversation_history(conversation)

        # Delete the conversation record
        db.delete(conversation)
        db.commit()
        
        logger.info(f"Deleted conversation {conversation_id}")
        return True
    
    @staticmethod
    async def get_conversation_history(
        db: Session,
        conversation_id: int,
        user_context: Dict
    ) -> Optional[List[Dict]]:
        """
        Get the message history for a conversation
        
        Args:
            db: Database session
            conversation_id: ID of the conversation
            user_context: User context for validation
            
        Returns:
            List of messages or None if not found/unauthorized
        """
        conversation = ConversationService.get_conversation(db, conversation_id, user_context)
        
        if not conversation:
            return None
        
        # Scheduled runs and interactive runs can arrive with either the
        # canonical conversation session id or its UUID suffix, depending on
        # which session-management path created the LangGraph checkpoint.
        # Read the canonical key first and use the suffix as a compatibility
        # fallback so an existing scheduled conversation is never shown empty.
        history = await CheckpointerCacheService.get_conversation_history_async(
            agent_id=conversation.agent_id,
            session_id=conversation.session_id
        )
        if not history and conversation.session_id.startswith(f"conv_{conversation.agent_id}_"):
            session_suffix = conversation.session_id.replace(
                f"conv_{conversation.agent_id}_", "", 1
            )
            history = await CheckpointerCacheService.get_conversation_history_async(
                agent_id=conversation.agent_id,
                session_id=session_suffix,
            )
        
        if not history:
            return []
        
        cleaned_history: List[Dict] = []
        for msg in history:
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            parsed_content = content
            
            if isinstance(content, str):
                stripped_content = content.strip()
                if stripped_content.startswith("[") and "type" in stripped_content:
                    try:
                        parsed_content = json.loads(stripped_content)
                    except json.JSONDecodeError:
                        try:
                            parsed_content = ast.literal_eval(stripped_content)
                        except (ValueError, SyntaxError):
                            parsed_content = content
            
            if isinstance(parsed_content, list):
                text_parts = []
                has_image = False
                for item in parsed_content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                        elif item.get("type") == "image_url":
                            has_image = True
                display_text = " ".join(text_parts).strip()
                # Clean attached file content from multimodal text
                display_text = ConversationService._clean_attached_files_content(display_text)
                if not display_text and has_image:
                    display_text = "[Imagen adjunta]"
                clean_msg = msg.copy()
                clean_msg["content"] = display_text or msg.get("content", "")
                cleaned_history.append(clean_msg)
            else:
                # Clean attached file content from simple text messages
                clean_msg = msg.copy()
                if isinstance(parsed_content, str):
                    clean_msg["content"] = ConversationService._clean_attached_files_content(parsed_content)
                cleaned_history.append(clean_msg)

        # Resolve [IMAGE:{block_id}] placeholders to inline file:// markers.
        # The conversations endpoint user_context lacks app_id; enrich it from the agent.
        resolve_user_ctx = user_context
        if 'app_id' not in resolve_user_ctx and conversation.agent and conversation.agent.app_id:
            resolve_user_ctx = {**resolve_user_ctx, 'app_id': conversation.agent.app_id}

        resolved_history = []
        for msg in cleaned_history:
            if msg.get("role") == "agent" and isinstance(msg.get("content"), str) and "[IMAGE:" in msg["content"]:
                resolved_msg = msg.copy()
                resolved_msg["content"] = await _resolve_image_placeholders(
                    msg["content"],
                    agent_id=conversation.agent_id,
                    user_context=resolve_user_ctx,
                    conversation_id=str(conversation_id),
                )
                resolved_history.append(resolved_msg)
            else:
                resolved_history.append(msg)

        return resolved_history
    
    @staticmethod
    def _clean_attached_files_content(text: str) -> str:
        """
        Remove attached file content from message text.
        The agent execution service appends file content like:
        [Attached files:]
        --- File: filename.pdf ---
        (full content here)
        --- End of filename.pdf ---
        
        This should not be shown in the conversation history UI.
        
        Args:
            text: Message text that may contain attached file content
            
        Returns:
            Cleaned text without the file content
        """
        if not text:
            return text
        
        # Check for attached files marker
        files_marker = "\n\n[Attached files:]"
        base_folder_marker = "\n\nFiles base folder is:"
        
        # Find the earliest marker position
        marker_pos = -1
        has_files = False
        
        # Check for files base folder marker (appears before [Attached files:])
        base_pos = text.find(base_folder_marker)
        if base_pos != -1:
            marker_pos = base_pos
            has_files = True
        
        # Check for [Attached files:] marker
        files_pos = text.find(files_marker)
        if files_pos != -1:
            if marker_pos == -1 or files_pos < marker_pos:
                marker_pos = files_pos
            has_files = True
        
        if has_files and marker_pos != -1:
            # Return only the original message (before file content)
            cleaned = text[:marker_pos].strip()
            # Add indicator that files were attached
            return cleaned + " 📎"
        
        return text
    
    @staticmethod
    def increment_message_count(
        db: Session,
        conversation_id: int,
        last_message: Optional[str] = None,
        increment_by: int = 1
    ):
        """
        Increment message count and update last message for a conversation
        
        Args:
            db: Database session
            conversation_id: ID of the conversation
            last_message: Optional last message preview
            increment_by: Number to increment message count by (default 1, use 2 for user+agent)
        """
        conversation = db.query(Conversation).filter(
            Conversation.conversation_id == conversation_id
        ).first()
        
        if conversation:
            conversation.message_count += increment_by
            conversation.updated_at = datetime.utcnow()
            
            if last_message:
                # Store preview (first 200 characters)
                conversation.last_message = last_message[:200]
            
            db.commit()
    
    @staticmethod
    def _validate_user_access(conversation: Conversation, user_context: AuthContext|dict) -> bool:
        """
        Validate if a user has access to a conversation
        
        Args:
            conversation: Conversation object
            user_context: User context
            
        Returns:
            True if user has access, False otherwise
        """
        # Scheduled-task executions own their conversations; users never do.
        if conversation.scheduled_task_id is not None:
            return (
                isinstance(user_context, dict)
                and user_context.get('scheduled_task_id') == conversation.scheduled_task_id
            )

        # Check API key user first (they have user_id as string like "apikey_xxx")
        if isinstance(user_context, dict) and user_context.get('api_key'):
            api_key_hash = hash_api_key(user_context['api_key'])
            if conversation.api_key_hash == api_key_hash:
                return True
            return False
        
        # Check OAuth user (AuthContext or dict with integer user_id)
        if isinstance(user_context, AuthContext):
            user_id = int(user_context.identity.id)
        else:
            user_id = user_context.get('user_id')
            # Ensure it's a valid integer
            if isinstance(user_id, str):
                if user_id.isdigit():
                    user_id = int(user_id)
                else:
                    return False
        
        if user_id and conversation.user_id == user_id:
            return True
        
        return False
