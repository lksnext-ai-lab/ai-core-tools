import uuid
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from fastapi import HTTPException

from utils.logger import get_logger

logger = get_logger(__name__)


class Session:
    """Represents a user session for an agent"""
    
    def __init__(self, session_id: str, agent_id: int, user_context: Dict):
        self.id = session_id
        self.agent_id = agent_id
        self.user_context = user_context
        self.messages: List[Dict] = []
        self.created_at = datetime.utcnow()
        self.last_accessed = datetime.utcnow()
        self.memory = None  # Initialize memory attribute
    
    def add_message(self, user_message: str, agent_response: str):
        """Add a message pair to the session"""
        self.messages.append({
            "timestamp": datetime.utcnow().isoformat(),
            "user_message": user_message,
            "agent_response": agent_response
        })
        self.last_accessed = datetime.utcnow()
    
    def get_conversation_history(self) -> List[Dict]:
        """Get conversation history"""
        return self.messages.copy()
    
    def clear_history(self):
        """Clear conversation history"""
        self.messages = []
        self.last_accessed = datetime.utcnow()
    
    def set_memory(self, memory):
        """Set the LangChain memory object for this session"""
        self.memory = memory
    
    def get_memory(self):
        """Get the LangChain memory object for this session"""
        # Handle existing sessions that might not have the memory attribute
        if not hasattr(self, 'memory'):
            self.memory = None
        return self.memory


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
        user_context: Dict
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
            session_id = self._generate_session_id(agent_id, user_context)
            
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
    
    async def add_message_to_session(
        self, 
        session_id: str, 
        user_message: str, 
        agent_response: str
    ):
        """
        Add message to session history
        
        Args:
            session_id: Session ID
            user_message: User's message
            agent_response: Agent's response
        """
        try:
            logger.info(f"Adding message to session {session_id}, total sessions: {len(self.__class__._sessions)}")
            logger.info(f"Available sessions: {list(self.__class__._sessions.keys())}")
            
            if session_id in self.__class__._sessions:
                session = self.__class__._sessions[session_id]
                session.add_message(user_message, agent_response)
                logger.info(f"Added message to session {session_id}, messages count: {len(session.messages)}")
            else:
                logger.warning(f"Session {session_id} not found for message addition")
                
        except Exception as e:
            logger.error(f"Error adding message to session: {str(e)}")
    
    async def reset_user_session(
        self, 
        agent_id: int, 
        user_context: Dict
    ) -> bool:
        """
        Reset user session (clear conversation history)
        
        Args:
            agent_id: ID of the agent
            user_context: User context
            
        Returns:
            True if reset successful
        """
        try:
            session_id = self._generate_session_id(agent_id, user_context)
            
            if session_id in self.__class__._sessions:
                session = self.__class__._sessions[session_id]
                session.clear_history()
                logger.info(f"Reset session {session_id} for agent {agent_id}")
                return True
            else:
                logger.warning(f"Session {session_id} not found for reset")
                return False
                
        except Exception as e:
            logger.error(f"Error resetting user session: {str(e)}")
            return False
    
    async def get_conversation_history(
        self, 
        agent_id: int, 
        user_context: Dict
    ) -> List[Dict]:
        """
        Get conversation history for a user session
        
        Args:
            agent_id: ID of the agent
            user_context: User context
            
        Returns:
            List of conversation messages
        """
        try:
            session_id = self._generate_session_id(agent_id, user_context)
            
            if session_id in self.__class__._sessions:
                session = self.__class__._sessions[session_id]
                return session.get_conversation_history()
            else:
                return []
                
        except Exception as e:
            logger.error(f"Error getting conversation history: {str(e)}")
            return []
    
    def _generate_session_id(self, agent_id: int, user_context: Dict) -> str:
        """
        Generate unique session ID based on agent and user context
        
        Args:
            agent_id: ID of the agent
            user_context: User context (api_key, user_id, etc.)
            
        Returns:
            Unique session ID
        """
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