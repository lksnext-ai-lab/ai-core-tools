from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row
import logging
import os

logger = logging.getLogger(__name__)

class CheckpointerCacheService:
    """
    Service to manage a shared AsyncConnectionPool for LangGraph's PostgreSQL checkpointer.

    The pool is created once at application startup (via initialize_pool) and shared across
    all requests. This avoids creating a new TCP connection per request, which caused OOM
    kills in Kubernetes due to resource accumulation.
    """

    _db_uri = None
    _pool: AsyncConnectionPool = None
    _checkpointer: AsyncPostgresSaver = None
    _is_setup_done = False

    @classmethod
    def _get_db_uri(cls) -> str:
        """Get database URI from environment variables"""
        if cls._db_uri is None:
            cls._db_uri = os.getenv('SQLALCHEMY_DATABASE_URI', 'postgresql://iacoretoolsdev:iacoretoolsdev@localhost:5432/iacoretoolsdev')
        return cls._db_uri

    @classmethod
    async def initialize_pool(cls):
        """
        Initialize the shared AsyncConnectionPool and checkpointer.
        Must be called during application startup (FastAPI lifespan).
        """
        db_uri = cls._get_db_uri()
        logger.info(f"Initializing checkpointer connection pool (DB: {db_uri.split('@')[1] if '@' in db_uri else 'hidden'})")

        cls._pool = AsyncConnectionPool(
            conninfo=db_uri,
            min_size=2,
            max_size=10,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
            },
        )
        await cls._pool.open(wait=True)

        cls._checkpointer = AsyncPostgresSaver(conn=cls._pool)
        await cls._checkpointer.setup()
        cls._is_setup_done = True

        logger.info("Checkpointer connection pool initialized successfully")

    @classmethod
    async def close_pool(cls):
        """
        Close the shared connection pool.
        Must be called during application shutdown (FastAPI lifespan).
        """
        if cls._pool is not None:
            await cls._pool.close()
            logger.info("Checkpointer connection pool closed")
        cls._pool = None
        cls._checkpointer = None
        cls._is_setup_done = False

    @classmethod
    async def get_async_checkpointer(cls) -> AsyncPostgresSaver:
        """
        Return the shared AsyncPostgresSaver backed by the connection pool.

        The pool automatically checks out and returns connections per operation,
        so no per-request lifecycle management is needed.

        Returns:
            AsyncPostgresSaver instance
        """
        if cls._checkpointer is None:
            raise RuntimeError(
                "Checkpointer pool not initialized. "
                "Call CheckpointerCacheService.initialize_pool() during application startup."
            )
        return cls._checkpointer

    @classmethod
    async def invalidate_checkpointer_async(cls, agent_id: int, session_id: str = "default"):
        """
        Delete checkpoints for a specific thread (session).

        The thread_id format must match the one used during agent execution:
        f"thread_{agent_id}_{session_id}"

        Args:
            agent_id: Agent ID
            session_id: Session ID (e.g., "oauth_9_2", "api_1_abc123")
        """
        try:
            checkpointer = await cls.get_async_checkpointer()

            thread_id = f"thread_{agent_id}_{session_id}"
            await checkpointer.adelete_thread(thread_id)

            logger.info(f"Deleted checkpoints for thread {thread_id} (agent {agent_id}, session {session_id})")
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

        Args:
            agent_id: Agent ID (required to build correct thread_id)
            session_id: Session ID to clear
        """
        try:
            await cls.invalidate_checkpointer_async(agent_id, session_id)
            logger.info(f"Deleted checkpoints for session {session_id} (agent {agent_id})")
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
            checkpointer = await cls.get_async_checkpointer()

            thread_id = f"thread_{agent_id}_{session_id}"
            config = {"configurable": {"thread_id": thread_id}}

            state_tuple = await checkpointer.aget_tuple(config)

            if state_tuple and state_tuple.checkpoint:
                channel_values = state_tuple.checkpoint.get("channel_values", {})
                messages = channel_values.get("messages", [])

                history = []
                for msg in messages:
                    if hasattr(msg, 'type'):
                        msg_type = msg.type
                        if msg_type in ['human', 'user']:
                            role = 'user'
                        elif msg_type in ['ai', 'assistant']:
                            role = 'agent'

                            content = msg.content if hasattr(msg, 'content') else str(msg)

                            if isinstance(content, list):
                                content_str = str(content)
                            else:
                                content_str = str(content) if content else ""

                            if hasattr(msg, 'tool_calls') and msg.tool_calls and not content_str.strip():
                                continue

                            if content_str.strip().startswith('[') and 'tool_use' in content_str:
                                continue

                        elif msg_type == 'system':
                            continue
                        elif msg_type == 'tool':
                            continue
                        else:
                            role = msg_type

                        content = msg.content if hasattr(msg, 'content') else str(msg)

                        if isinstance(content, list):
                            content_str = str(content)
                        else:
                            content_str = str(content) if content else ""

                        if not content_str or not content_str.strip():
                            continue

                        history.append({
                            "role": role,
                            "content": content_str
                        })

                logger.info(f"Retrieved {len(history)} messages from thread {thread_id}")
                return history
            else:
                logger.info(f"No conversation history found for thread {thread_id}")
                return []

        except Exception as e:
            logger.error(f"Error retrieving conversation history: {str(e)}")
            return []
