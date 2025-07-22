from models.agent import Agent
from langgraph.checkpoint.memory import InMemorySaver
import logging

logger = logging.getLogger(__name__)

class CheckpointerCacheService:
    # Use a class-level dictionary to store checkpointer instances
    # Key format: "agent_id" (simplified for FastAPI)
    _checkpointer_instances = {}

    @classmethod
    def _get_cache_key(cls, agent_id: int, session_id: str = "default") -> str:
        """Generate cache key using session ID and agent ID"""
        return f"{session_id}:{agent_id}"

    @classmethod
    def get_cached_checkpointer(cls, agent_id: int, session_id: str = "default") -> InMemorySaver:
        """Get checkpointer instance from memory cache"""
        cache_key = cls._get_cache_key(agent_id, session_id)
        return cls._checkpointer_instances.get(cache_key)

    @classmethod
    def cache_checkpointer(cls, agent_id: int, checkpointer: InMemorySaver, session_id: str = "default"):
        """Store checkpointer instance in memory cache"""
        cache_key = cls._get_cache_key(agent_id, session_id)
        cls._checkpointer_instances[cache_key] = checkpointer
        logger.info(f"Cached checkpointer for agent {agent_id} in session {session_id}")

    @classmethod
    def invalidate_checkpointer(cls, agent_id: int, session_id: str = "default"):
        """Remove checkpointer instance from cache"""
        cache_key = cls._get_cache_key(agent_id, session_id)
        if cache_key in cls._checkpointer_instances:
            del cls._checkpointer_instances[cache_key]
            logger.info(f"Invalidated checkpointer for agent {agent_id} in session {session_id}")

    @classmethod
    def invalidate_all(cls):
        """Clear entire checkpointer cache"""
        cls._checkpointer_instances.clear()
        logger.info("Cleared entire checkpointer cache")

    @classmethod
    def invalidate_session_checkpointers(cls, session_id: str = "default"):
        """Clear all checkpointers for a specific session"""
        keys_to_remove = [key for key in cls._checkpointer_instances.keys() if key.startswith(f"{session_id}:")]
        for key in keys_to_remove:
            del cls._checkpointer_instances[key]
        
        logger.info(f"Invalidated all checkpointers for session {session_id}") 