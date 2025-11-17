import uuid
import hashlib
from typing import List, Optional, Dict
from numpy import isin
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
from datetime import datetime

from models.conversation import Conversation
from models.agent import Agent
from schemas.conversation_schemas import ConversationCreate, ConversationUpdate
from services.agent_cache_service import CheckpointerCacheService
from utils.logger import get_logger
from lks_idprovider import AuthContext

logger = get_logger(__name__)


class ConversationService:
    """Service for managing user conversations with agents"""
    
    @staticmethod
    def create_conversation(
        db: Session,
        agent_id: int,
        user_context: Dict,
        title: Optional[str] = None
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
        
        if api_key:
            # Hash the API key for tracking (without storing the actual key)
            api_key_hash = hashlib.md5(api_key.encode()).hexdigest()
        
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
        user_context: Dict
    ) -> Optional[Conversation]:
        """
        Get a conversation by ID with user validation
        
        Args:
            db: Database session
            conversation_id: ID of the conversation
            user_context: User context for validation
            
        Returns:
            Conversation object or None if not found/unauthorized
        """
        conversation = db.query(Conversation).filter(
            Conversation.conversation_id == conversation_id
        ).first()
        
        if not conversation:
            return None
        
        # Validate user access
        if not ConversationService._validate_user_access(conversation, user_context):
            logger.warning(f"Unauthorized access attempt to conversation {conversation_id}")
            return None
        
        return conversation
    
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
        
        # Filter by user
        user_id = user_context.identity.id
        
        if user_id:
            query = query.filter(Conversation.user_id == user_id)
        elif isinstance(user_context, dict) and user_context.get('api_key'):
            api_key = user_context.get('api_key')
            api_key_hash = hashlib.md5(api_key.encode()).hexdigest()
            query = query.filter(Conversation.api_key_hash == api_key_hash)
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
        
        # Delete the chat history from PostgreSQL checkpointer
        try:
            # Use the full session_id as-is (don't remove the conv_ prefix)
            # The thread_id format is: thread_{agent_id}_{full_session_id}
            await CheckpointerCacheService.invalidate_checkpointer_async(
                agent_id=conversation.agent_id,
                session_id=conversation.session_id
            )
            logger.info(f"Deleted chat history for conversation {conversation_id} (thread_id: thread_{conversation.agent_id}_{conversation.session_id})")
        except Exception as e:
            logger.error(f"Error deleting chat history: {e}")
        
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
        
        # Use the full session_id as-is (don't remove the conv_ prefix)
        # The thread_id format is: thread_{agent_id}_{full_session_id}
        
        # Get history from PostgreSQL checkpointer
        history = await CheckpointerCacheService.get_conversation_history_async(
            agent_id=conversation.agent_id,
            session_id=conversation.session_id
        )
        
        return history
    
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
        if isinstance(user_context, AuthContext):
            user_id = int(user_context.identity.id)
        else:
            user_id = user_context.get('user_id')

        # Check OAuth user
        if user_id and conversation.user_id == user_id:
            return True
        
        # Check API key user
        if  isinstance(user_context, dict) and user_context.get('api_key'):
            api_key_hash = hashlib.md5(user_context['api_key'].encode()).hexdigest()
            if conversation.api_key_hash == api_key_hash:
                return True
        
        return False

