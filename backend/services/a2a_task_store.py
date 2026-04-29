import json
from typing import Any

from a2a.server.context import ServerCallContext
from a2a.server.tasks.task_store import TaskStore
from a2a.types import Task
from db.database import SessionLocal
from models.a2a_task import A2ATask
from models.conversation import Conversation
from repositories.a2a_task_repository import A2ATaskRepository
from utils.logger import get_logger

logger = get_logger(__name__)


class MattinA2ATaskStore(TaskStore):
    """Persistent A2A TaskStore backed by Mattin AI's database."""

    def _extract_state(self, context: ServerCallContext | None) -> dict[str, Any]:
        if context and isinstance(context.state, dict):
            return context.state.get("a2a", {})
        return {}

    def _matches_scope(self, row: A2ATask, state: dict[str, Any]) -> bool:
        app_id = state.get("app_id")
        agent_id = state.get("agent_id")
        if app_id is not None and row.app_id != app_id:
            return False
        if agent_id is not None and row.agent_id != agent_id:
            return False
        return True

    def _get_session(self, state: dict[str, Any]):
        session = state.get("db_session")
        if session is not None:
            return session, False
        return SessionLocal(), True

    def _resolve_conversation_id(self, session, conversation_id: Any):
        if conversation_id in (None, ""):
            return None

        resolved_id = int(conversation_id)
        conversation_exists = (
            session.query(Conversation.conversation_id)
            .filter(Conversation.conversation_id == resolved_id)
            .first()
            is not None
        )
        if conversation_exists:
            return resolved_id

        logger.debug(
            "Skipping A2A task conversation_id=%s because the conversation does not exist",
            resolved_id,
        )
        return None

    async def save(
        self, task: Task, context: ServerCallContext | None = None
    ) -> None:
        state = self._extract_state(context)
        session, owns_session = self._get_session(state)
        try:
            row = A2ATaskRepository.get_by_id(session, task.id)
            if row and not self._matches_scope(row, state):
                logger.warning("Refusing to overwrite out-of-scope A2A task %s", task.id)
                return

            if not row:
                if state.get("app_id") is None or state.get("agent_id") is None:
                    raise ValueError("A2A task save requires app_id and agent_id in context")
                row = A2ATask(
                    task_id=task.id,
                    context_id=task.context_id,
                    app_id=state["app_id"],
                    agent_id=state["agent_id"],
                    api_key_id=state.get("api_key_id"),
                )

            row.context_id = task.context_id
            row.api_key_id = state.get("api_key_id", row.api_key_id)
            row.status = task.status.state.value if hasattr(task.status.state, "value") else str(task.status.state)
            row.task_payload = task.model_dump(mode="json", by_alias=True, exclude_none=True)
            metadata = task.metadata or {}
            conversation_id = self._resolve_conversation_id(session, metadata.get("conversation_id"))
            if conversation_id is not None:
                row.conversation_id = conversation_id

            A2ATaskRepository.save(session, row)
        finally:
            if owns_session:
                session.close()

    async def get(
        self, task_id: str, context: ServerCallContext | None = None
    ) -> Task | None:
        state = self._extract_state(context)
        session, owns_session = self._get_session(state)
        try:
            row = A2ATaskRepository.get_by_id(session, task_id)
            if not row or not self._matches_scope(row, state):
                return None
            return Task.model_validate(row.task_payload)
        finally:
            if owns_session:
                session.close()

    async def delete(
        self, task_id: str, context: ServerCallContext | None = None
    ) -> None:
        state = self._extract_state(context)
        session, owns_session = self._get_session(state)
        try:
            row = A2ATaskRepository.get_by_id(session, task_id)
            if row and self._matches_scope(row, state):
                A2ATaskRepository.delete(session, row)
        finally:
            if owns_session:
                session.close()
