from flask import session
from model.agent import Agent
import logging
import weakref

logger = logging.getLogger(__name__)

class AgentCacheService:
    # Use a class-level dictionary to store agents in memory
    _agent_instances = {}

    @classmethod
    def get_cached_agent(cls, agent_id: int):
        """Get agent instance from memory cache"""
        return cls._agent_instances.get(str(agent_id))

    @classmethod
    def cache_agent(cls, agent_id: int, agent_instance):
        """Store agent instance in memory cache"""
        cls._agent_instances[str(agent_id)] = agent_instance
        logger.info(f"Cached agent {agent_id}")

    @classmethod
    def invalidate_agent(cls, agent_id: int):
        """Remove agent instance from cache"""
        if str(agent_id) in cls._agent_instances:
            del cls._agent_instances[str(agent_id)]
            logger.info(f"Invalidated agent {agent_id} cache")

    @classmethod
    def invalidate_all(cls):
        """Clear entire agent cache"""
        cls._agent_instances.clear()
        logger.info("Cleared entire agent cache")
