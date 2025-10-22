import uuid
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from fastapi import HTTPException

from utils.logger import get_logger

logger = get_logger(__name__)


class Session:
    """
    Lightweight session tracking for agent conversations.
    
    The actual conversation history is stored in PostgreSQL via LangGraph's checkpointer.
    This class only tracks session metadata for timeout management and thread_id generation.
    """
    
    def __init__(self, session_id: str, agent_id: int, user_context: Dict):
        self.id = session_id                    # Used to generate thread_id for PostgreSQL
        self.agent_id = agent_id                # Agent identifier
        self.user_context = user_context        # User context for validation
        self.created_at = datetime.utcnow()     # Session creation timestamp
        self.last_accessed = datetime.utcnow()  # Last interaction timestamp (for timeout)
    
    def touch(self):
        """Update last accessed timestamp to keep session alive"""
        self.last_accessed = datetime.utcnow()
    
    def is_expired(self, timeout: timedelta) -> bool:
        """Check if session has exceeded the timeout period"""
        return datetime.utcnow() - self.last_accessed > timeout


class SessionManagementService:
    """Unified session management - used by both public and internal APIs"""
    
    # Global instance to ensure sessions persist across requests
    _instance = None
    _sessions: Dict[str, Session] = {}
    _session_timeout = timedelta(hours=24)  # 24 hour timeout
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SessionManagementService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        # No need to initialize _sessions here since it's a class variable
        pass
    
    async def get_user_session(
        self, 
        agent_id: int, 
        user_context: Dict,
        conversation_id: str = None
    ) -> Optional[Session]:
        """
        Get or create user session for memory-enabled agents
        
        Args:
            agent_id: ID of the agent
            user_context: User context (api_key, user_id, etc.)
            
        Returns:
            Session object or None if session not found/expired
        """
        try:
            # Generate session ID based on user context
            session_id = self._generate_session_id(agent_id, user_context, conversation_id)
            
            logger.info(f"Looking for session {session_id}, total sessions: {len(self.__class__._sessions)}")
            logger.info(f"Available sessions: {list(self.__class__._sessions.keys())}")
            
            # Check if session exists and is not expired
            if session_id in self.__class__._sessions:
                session = self.__class__._sessions[session_id]
                logger.info(f"Found existing session {session_id}")
                
                # Check if session is expired
                if datetime.utcnow() - session.last_accessed > self.__class__._session_timeout:
                    # Remove expired session
                    del self.__class__._sessions[session_id]
                    logger.info(f"Removed expired session {session_id}")
                    return None
                
                # Update last accessed time
                session.last_accessed = datetime.utcnow()
                return session
            
            # Create new session
            session = Session(session_id, agent_id, user_context)
            self.__class__._sessions[session_id] = session
            
            logger.info(f"Created new session {session_id} for agent {agent_id}")
            logger.info(f"Total sessions after creation: {len(self.__class__._sessions)}")
            return session
            
        except Exception as e:
            logger.error(f"Error getting user session: {str(e)}")
            return None
    
    async def touch_session(self, session_id: str):
        """
        Update session last accessed timestamp to keep it alive
        
        Args:
            session_id: Session ID
        """
        try:
            if session_id in self.__class__._sessions:
                session = self.__class__._sessions[session_id]
                session.touch()
                logger.debug(f"Updated last accessed time for session {session_id}")
            else:
                logger.warning(f"Session {session_id} not found for touch update")
                
        except Exception as e:
            logger.error(f"Error touching session: {str(e)}")
    
    async def reset_user_session(
        self, 
        agent_id: int, 
        user_context: Dict
    ) -> bool:
        """
        Reset user session by removing it from memory.
        The PostgreSQL checkpointer must be cleared separately via CheckpointerCacheService.
        
        Args:
            agent_id: ID of the agent
            user_context: User context
            
        Returns:
            True if reset successful, False if session not found
        """
        try:
            session_id = self._generate_session_id(agent_id, user_context, user_context.get("conversation_id"))
            
            if session_id in self.__class__._sessions:
                # Remove session from memory
                del self.__class__._sessions[session_id]
                logger.info(f"Deleted session {session_id} for agent {agent_id}")
                return True
            else:
                logger.warning(f"Session {session_id} not found for reset")
                return False
                
        except Exception as e:
            logger.error(f"Error resetting user session: {str(e)}")
            return False
    
    
    def _generate_session_id(self, agent_id: int, user_context: Dict, conversation_id: str = None) -> str:
        """
        Generate unique session ID based on agent and user context
        
        Args:
            agent_id: ID of the agent
            user_context: User context (api_key, user_id, etc.)
            conversation_id: Optional custom conversation ID
            
        Returns:
            Unique session ID
        """
        # If conversation_id is provided, use it as the session ID
        if conversation_id:
            return f"conv_{agent_id}_{conversation_id}"
        
        # Create a unique identifier based on user context
        if "user_id" in user_context:
            # OAuth user
            user_id = user_context["user_id"]
            return f"oauth_{agent_id}_{user_id}"
        elif "api_key" in user_context:
            # API key user - use API key hash for uniqueness
            import hashlib
            api_key_hash = hashlib.md5(user_context["api_key"].encode()).hexdigest()[:8]
            return f"api_{agent_id}_{api_key_hash}"
        else:
            # Fallback - use timestamp
            return f"anon_{agent_id}_{int(datetime.utcnow().timestamp())}"
    
    def cleanup_expired_sessions(self):
        """Clean up expired sessions (should be called periodically)"""
        try:
            current_time = datetime.utcnow()
            expired_sessions = []
            
            for session_id, session in self.__class__._sessions.items():
                if current_time - session.last_accessed > self.__class__._session_timeout:
                    expired_sessions.append(session_id)
            
            for session_id in expired_sessions:
                del self.__class__._sessions[session_id]
                logger.info(f"Cleaned up expired session {session_id}")
                
        except Exception as e:
            logger.error(f"Error cleaning up expired sessions: {str(e)}")
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get session management statistics"""
        try:
            current_time = datetime.utcnow()
            active_sessions = 0
            expired_sessions = 0
            
            for session in self.__class__._sessions.values():
                if current_time - session.last_accessed <= self.__class__._session_timeout:
                    active_sessions += 1
                else:
                    expired_sessions += 1
            
            return {
                "total_sessions": len(self.__class__._sessions),
                "active_sessions": active_sessions,
                "expired_sessions": expired_sessions,
                "session_timeout_hours": self.__class__._session_timeout.total_seconds() / 3600
            }
            
        except Exception as e:
            logger.error(f"Error getting session stats: {str(e)}")
            return {} 