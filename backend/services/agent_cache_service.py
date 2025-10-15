from models.agent import Agent
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
import logging
import os

logger = logging.getLogger(__name__)

class CheckpointerCacheService:
    """
    Service to manage Async PostgreSQL checkpointer for LangGraph agents.
    The checkpointer is created within each event loop to ensure proper async context.
    """
    
    # Store the connection string instead of the checkpointer instance
    _db_uri = None
    _is_setup_done = False

    @classmethod
    def _get_db_uri(cls) -> str:
        """Get database URI from environment variables"""
        if cls._db_uri is None:
            cls._db_uri = os.getenv('SQLALCHEMY_DATABASE_URI', 'postgresql://iacoretoolsdev:iacoretoolsdev@localhost:5432/iacoretoolsdev')
        return cls._db_uri

    @classmethod
    async def get_async_checkpointer(cls):
        """
        Create and return an AsyncPostgresSaver for the current event loop.
        This must be called within an async context (event loop).
        
        Returns:
            AsyncPostgresSaver instance (context manager entered)
        """
        db_uri = cls._get_db_uri()
        
        setup_needed = not cls._is_setup_done
        
        if setup_needed:
            logger.info(f"Initializing Async PostgreSQL checkpointer with URI: {db_uri.split('@')[1] if '@' in db_uri else 'hidden'}")
        
        # Create a new checkpointer context manager for this event loop
        checkpointer_cm = AsyncPostgresSaver.from_conn_string(db_uri)
        # Enter the async context manager
        checkpointer = await checkpointer_cm.__aenter__()
        
        # Setup tables if first time (idempotent operation)
        if setup_needed:
            try:
                await checkpointer.setup()
                logger.info("PostgreSQL checkpointer tables created/verified")
                logger.info("✓ Async checkpointer is ready to persist agent memory to PostgreSQL")
                cls._is_setup_done = True
            except Exception as e:
                logger.debug(f"Checkpointer setup (tables may already exist): {str(e)}")
                cls._is_setup_done = True
        
        return checkpointer, checkpointer_cm

    @classmethod
    def get_cached_checkpointer(cls, agent_id: int = None, session_id: str = "default"):
        """
        Legacy method for backward compatibility.
        Returns None - the actual checkpointer will be created in the async context.
        
        Args:
            agent_id: Agent ID (kept for backward compatibility)
            session_id: Session ID (kept for backward compatibility)
            
        Returns:
            None (checkpointer will be created in async context)
        """
        logger.info(f"Checkpointer will be created in async context for agent {agent_id} (session: {session_id})")
        return None

    @classmethod
    def cache_checkpointer(cls, agent_id: int = None, checkpointer = None, session_id: str = "default"):
        """
        This method is kept for backward compatibility but doesn't do anything.
        
        Args:
            agent_id: Agent ID (ignored)
            checkpointer: Checkpointer instance (ignored)
            session_id: Session ID (ignored)
        """
        logger.info(f"Using async PostgreSQL checkpointer (agent: {agent_id}, session: {session_id})")

    @classmethod
    async def invalidate_checkpointer_async(cls, agent_id: int, session_id: str = "default"):
        """
        Delete checkpoints for a specific thread (session) - async version.
        
        The thread_id format must match the one used during agent execution:
        f"thread_{agent_id}_{session_id}"
        
        Args:
            agent_id: Agent ID
            session_id: Session ID (e.g., "oauth_9_2", "api_1_abc123")
        """
        try:
            # Create a temporary checkpointer to delete the thread
            checkpointer, checkpointer_cm = await cls.get_async_checkpointer()
            
            try:
                # Generate thread_id that EXACTLY matches the one used in agent_execution_service.py
                # Format: "thread_{agent_id}_{session_id}"
                thread_id = f"thread_{agent_id}_{session_id}"
                
                # Delete the thread from PostgreSQL
                await checkpointer.adelete_thread(thread_id)
                
                logger.info(f"Deleted checkpoints for thread {thread_id} (agent {agent_id}, session {session_id})")
            finally:
                # Clean up the checkpointer
                await checkpointer_cm.__aexit__(None, None, None)
            
        except Exception as e:
            logger.error(f"Error invalidating checkpointer: {str(e)}")

    @classmethod
    def invalidate_checkpointer(cls, agent_id: int, session_id: str = "default"):
        """
        Delete checkpoints for a specific thread (session) - sync wrapper.
        
        Args:
            agent_id: Agent ID
            session_id: Session ID
        """
        import asyncio
        try:
            asyncio.run(cls.invalidate_checkpointer_async(agent_id, session_id))
        except Exception as e:
            logger.error(f"Error invalidating checkpointer: {str(e)}")

    @classmethod
    def invalidate_all(cls):
        """
        Clear all checkpointer data.
        Note: This doesn't delete the database tables, just logs a warning.
        PostgreSQL checkpointer data should be managed through database operations.
        """
        logger.warning("invalidate_all() called - PostgreSQL checkpointer data is persistent")
        logger.warning("To clear all data, use database operations or delete specific threads")

    @classmethod
    async def invalidate_session_checkpointers_async(cls, agent_id: int, session_id: str = "default"):
        """
        Clear checkpoints for a specific session - async version.
        
        Note: This is a wrapper around invalidate_checkpointer_async.
        Kept for backward compatibility but requires agent_id now.
        
        Args:
            agent_id: Agent ID (required to build correct thread_id)
            session_id: Session ID to clear
        """
        try:
            # Use the standard invalidate method which has correct thread_id format
            await cls.invalidate_checkpointer_async(agent_id, session_id)
            logger.info(f"Deleted checkpoints for session {session_id} (agent {agent_id})")
        except Exception as e:
            logger.error(f"Error invalidating session checkpointers: {str(e)}")

    @classmethod
    def invalidate_session_checkpointers(cls, agent_id: int, session_id: str = "default"):
        """
        Clear checkpoints for a specific session - sync wrapper.
        
        Args:
            agent_id: Agent ID (required to build correct thread_id)
            session_id: Session ID to clear
        """
        import asyncio
        try:
            asyncio.run(cls.invalidate_session_checkpointers_async(agent_id, session_id))
        except Exception as e:
            logger.error(f"Error invalidating session checkpointers: {str(e)}")

    @classmethod
    async def get_conversation_history_async(cls, agent_id: int, session_id: str = "default"):
        """
        Retrieve conversation history from PostgreSQL checkpointer.
        
        Args:
            agent_id: Agent ID
            session_id: Session ID
            
        Returns:
            List of message dicts with role and content
        """
        try:
            # Create a temporary checkpointer to read the thread
            checkpointer, checkpointer_cm = await cls.get_async_checkpointer()
            
            try:
                # Generate thread_id that matches the one used in agent_execution_service.py
                thread_id = f"thread_{agent_id}_{session_id}"
                
                # Get the latest state for this thread
                config = {"configurable": {"thread_id": thread_id}}
                
                # Get the state tuple
                state_tuple = await checkpointer.aget_tuple(config)
                
                if state_tuple and state_tuple.checkpoint:
                    # Extract messages from checkpoint
                    channel_values = state_tuple.checkpoint.get("channel_values", {})
                    messages = channel_values.get("messages", [])
                    
                    # Convert LangChain messages to simple dicts
                    history = []
                    for msg in messages:
                        # Handle different message types
                        if hasattr(msg, 'type'):
                            msg_type = msg.type
                            if msg_type in ['human', 'user']:
                                role = 'user'
                            elif msg_type in ['ai', 'assistant']:
                                role = 'agent'
                            elif msg_type == 'system':
                                # Skip system messages in UI
                                continue
                            else:
                                role = msg_type
                            
                            content = msg.content if hasattr(msg, 'content') else str(msg)
                            
                            history.append({
                                "role": role,
                                "content": content
                            })
                    
                    logger.info(f"Retrieved {len(history)} messages from thread {thread_id}")
                    return history
                else:
                    logger.info(f"No conversation history found for thread {thread_id}")
                    return []
                    
            finally:
                # Clean up the checkpointer
                await checkpointer_cm.__aexit__(None, None, None)
            
        except Exception as e:
            logger.error(f"Error retrieving conversation history: {str(e)}")
            return [] 