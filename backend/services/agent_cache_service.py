from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row
from psycopg.errors import UniqueViolation
import logging
import os

logger = logging.getLogger(__name__)


# Providers reject a checkpoint with a dangling tool_calls entry (an
# AIMessage whose tool call never got a matching ToolMessage — e.g. the
# backend crashed mid-tool-execution) with different wording depending on
# the exact API surface hit. Live-reproduced against OpenAI (gpt-4o-mini,
# chat completions): killing the backend mid-tool-call and resuming the
# conversation raises "An assistant message with 'tool_calls' must be
# followed by tool messages responding to each 'tool_call_id'. The
# following tool_call_ids did not have response messages: ..." — not the
# "No tool output found for function call" phrasing this used to match
# exclusively, which meant the recovery path below never triggered for
# this (the common) case.
_MISSING_TOOL_OUTPUT_MARKERS = (
    "No tool output found for function call",
    "did not have response messages",
)


def is_missing_tool_output_error(exc: BaseException) -> bool:
    """Return True when a provider rejects a stale incomplete tool-call checkpoint."""
    text = str(exc)
    return any(marker in text for marker in _MISSING_TOOL_OUTPUT_MARKERS)


def _content_blocks_to_str(blocks: list) -> str:
    """Convert a LangChain multimodal content block list to a display string.

    Handles text, image_url and image_generation_call block types so that
    conversation history never shows raw Python repr of the block list.
    """
    text_parts = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type", "")
        if block_type == "text":
            text = block.get("text", "").strip()
            if text:
                text_parts.append(text)
        elif block_type == "image_generation_call":
            block_id = block.get("id", "")
            text_parts.append(f"[IMAGE:{block_id}]" if block_id else "[Imagen generada]")
        elif block_type == "image_url":
            # For Gemini-generated images the URL is a data URI; derive a stable
            # ID from a content hash so _resolve_image_placeholders can match
            # the registered file (saved as generated_image_{hash}.png).
            url = (block.get("image_url") or {}).get("url", "")
            if url.startswith("data:image/") and ";base64," in url:
                import hashlib as _hl
                import base64 as _b64
                b64_data = url.split(";base64,", 1)[1]
                img_hash = _hl.sha256(_b64.b64decode(b64_data)).hexdigest()[:16]
                text_parts.append(f"[IMAGE:{img_hash}]")
            # External-URL images are not resolved; skip silently.
    return " ".join(text_parts) if text_parts else ""

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
            max_lifetime=1800,   # recycle connections after 30 min
            max_idle=300,        # close connections idle longer than 5 min
            reconnect_timeout=30,  # retry broken connections for up to 30 s
            open=False,          # open explicitly below (constructor open is deprecated)
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
            },
        )
        await cls._pool.open(wait=True)

        cls._checkpointer = AsyncPostgresSaver(conn=cls._pool)
        try:
            await cls._checkpointer.setup()
        except UniqueViolation:
            logger.warning("Checkpointer migrations already applied, skipping setup")
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
    async def get_rollback_checkpoint_id(
        cls, agent_id: int, session_id: str, *, max_lookback: int = 25
    ) -> str | None:
        """
        Walk back through a thread's checkpoint history and return the
        checkpoint_id of the most recent checkpoint that is actually safe
        to resume from — i.e. its message list does not end in an
        AIMessage with unresolved ``tool_calls``.

        Used to recover from a stale/incomplete tool-call checkpoint (the
        provider rejects a dangling ``tool_calls`` entry, e.g. "No tool
        output found for function call" or "... did not have response
        messages: ...") without data loss: LangGraph checkpoints are
        immutable and ordered, so retrying the turn with an earlier
        checkpoint_id set in the config forks the thread from that
        known-good state — new checkpoints get written after it, the
        broken ones are simply never read again, and no earlier
        conversation history is touched (unlike
        ``invalidate_checkpointer_async``, which deletes the entire
        thread and is only appropriate for an explicit user-initiated
        conversation reset).

        Naively taking "the one checkpoint before the latest" is NOT
        sufficient and was live-reproduced to fail: LangGraph can write
        more than one checkpoint while the dangling tool_calls message is
        still the last one in the state (e.g. one when the model node
        adds it, another when the tools node begins execution before
        being interrupted), so the immediate predecessor can carry the
        exact same broken state as the checkpoint that just failed. This
        walks back past every checkpoint still carrying that pending
        tool call, not just one.

        Args:
            agent_id: Agent ID
            session_id: Session ID (matches the thread_id used during execution)
            max_lookback: Maximum number of checkpoints to inspect before
                giving up (bounds the walk on a pathologically long thread).

        Returns:
            The checkpoint_id of the first clean checkpoint found, or None
            if none exists within ``max_lookback`` (nothing safe to roll
            back to).
        """
        try:
            checkpointer = await cls.get_async_checkpointer()

            thread_id = f"thread_{agent_id}_{session_id}"
            config = {"configurable": {"thread_id": thread_id}}

            seen_latest = False
            async for checkpoint_tuple in checkpointer.alist(config, limit=max_lookback):
                if not seen_latest:
                    # The most recent checkpoint is the one that just failed
                    # to replay — it's broken by definition, always skip it
                    # without inspecting it.
                    seen_latest = True
                    continue
                if cls._ends_with_pending_tool_call(checkpoint_tuple):
                    continue
                return checkpoint_tuple.config["configurable"]["checkpoint_id"]
            return None
        except Exception as e:
            logger.error(
                f"Error computing rollback checkpoint for agent {agent_id} "
                f"session {session_id}: {str(e)}"
            )
            return None

    @staticmethod
    def _ends_with_pending_tool_call(checkpoint_tuple) -> bool:
        """True when any AIMessage anywhere in a checkpoint's message list
        has a tool_call whose id is never answered by a later ToolMessage
        — i.e. this message list is NOT safe to hand back to the provider.

        Checking only the *last* message is not enough: once a retry
        appends a new HumanMessage on top of an already-broken state
        (rather than fixing it), the list ends in a clean HumanMessage
        while an unresolved AIMessage(tool_calls=...) still sits earlier
        in the same list with nothing between it and the new message —
        live-reproduced as exactly this shape, and OpenAI's chat
        completions API validates the *entire* message list, not just the
        tail, and rejects it identically.
        """
        messages = (checkpoint_tuple.checkpoint or {}).get("channel_values", {}).get(
            "messages"
        ) or []
        for i, msg in enumerate(messages):
            if getattr(msg, "type", None) != "ai":
                continue
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                continue
            pending_ids = {
                tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                for tc in tool_calls
            }
            answered_ids = {
                getattr(later, "tool_call_id", None)
                for later in messages[i + 1 :]
                if getattr(later, "type", None) == "tool"
            }
            if not pending_ids <= answered_ids:
                return True
        return False

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
                                content_str = _content_blocks_to_str(content)
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
                            content_str = _content_blocks_to_str(content)
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
