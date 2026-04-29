from __future__ import annotations

import base64
import inspect
import json
import mimetypes
import os
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Optional
from uuid import uuid4

from models.agent import Agent
from services.a2a_service import A2AService
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class A2AMemoryContext:
    """Platform-owned memory state projected into an A2A request."""

    history: list[dict[str, str]] = field(default_factory=list)
    remote_task_id: Optional[str] = None
    remote_context_id: Optional[str] = None
    remote_task_state: Optional[str] = None
    history_length: Optional[int] = None


@dataclass
class A2AExecutionResult:
    """Normalized response payload returned by the A2A executor."""

    text: str
    remote_task_id: Optional[str] = None
    remote_context_id: Optional[str] = None
    remote_task_state: Optional[str] = None


class A2AExecutorService:
    """Focused execution adapter for imported external A2A agents."""

    TERMINAL_TASK_STATES = {"completed", "failed", "canceled", "cancelled", "rejected"}

    def _get_langsmith_config(self, agent: Agent) -> Optional[dict[str, Any]]:
        """Reuse the app-scoped LangSmith client/project setup used by local agents."""
        try:
            from tools.agentTools import get_langsmith_config
        except Exception as exc:
            logger.warning(
                "Unable to import LangSmith helper for A2A tracing on agent_id=%s: %s",
                getattr(agent, "agent_id", None),
                exc,
            )
            return None

        try:
            return get_langsmith_config(agent)
        except Exception as exc:
            logger.warning(
                "Unable to initialize LangSmith tracing for A2A agent_id=%s: %s",
                getattr(agent, "agent_id", None),
                exc,
                exc_info=True,
            )
            return None

    def _build_trace_metadata(
        self,
        agent: Agent,
        *,
        user_context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        a2a_config = getattr(agent, "a2a_config", None)
        metadata: dict[str, Any] = {
            "source_type": "a2a",
            "agent_id": getattr(agent, "agent_id", None),
            "agent_name": getattr(agent, "name", None),
            "app_id": getattr(agent, "app_id", None),
            "remote_card_url": getattr(a2a_config, "card_url", None),
            "remote_agent_id": getattr(a2a_config, "remote_agent_id", None),
            "health_status": getattr(a2a_config, "health_status", None),
            "sync_status": getattr(a2a_config, "sync_status", None),
        }
        if user_context:
            metadata["request_app_id"] = user_context.get("app_id")
            metadata["request_user_id"] = user_context.get("user_id")
        return {key: value for key, value in metadata.items() if value is not None}

    def _langsmith_tags(self) -> list[str]:
        return ["a2a", "external-agent"]

    async def execute(
        self,
        agent: Agent,
        message: str,
        user_context: Optional[dict[str, Any]] = None,
        attachment_files: Optional[list[dict[str, Any]]] = None,
        memory_context: Optional[A2AMemoryContext] = None,
    ) -> A2AExecutionResult:
        logger.info(
            "Starting A2A execute for agent_id=%s card_url=%s message_len=%s attachment_count=%s",
            agent.agent_id,
            getattr(agent.a2a_config, "card_url", None),
            len(message or ""),
            len(attachment_files or []),
        )
        langsmith_config = self._get_langsmith_config(agent)
        trace_metadata = self._build_trace_metadata(agent, user_context=user_context)

        tracing_cm = nullcontext()
        trace_cm = nullcontext()
        if langsmith_config:
            try:
                import langsmith as ls

                tracing_cm = ls.tracing_context(
                    client=langsmith_config["client"],
                    project_name=langsmith_config["project_name"],
                    enabled=True,
                    tags=self._langsmith_tags(),
                    metadata=trace_metadata,
                )
                trace_cm = ls.trace(
                    name=f"A2A Agent Invocation: {getattr(agent, 'name', 'unknown')}",
                    run_type="chain",
                    project_name=langsmith_config["project_name"],
                    client=langsmith_config["client"],
                    inputs={
                        "message": message,
                        "streaming": False,
                        "history_messages": len(memory_context.history) if memory_context else 0,
                        "continuation_task_id": (
                            memory_context.remote_task_id if memory_context else None
                        ),
                    },
                    metadata=trace_metadata,
                    tags=self._langsmith_tags(),
                )
            except ImportError:
                logger.warning(
                    "LangSmith SDK is unavailable; skipping direct A2A tracing for agent_id=%s",
                    agent.agent_id,
                )

        with tracing_cm:
            with trace_cm as root_run:
                final_text = ""
                final_result = A2AExecutionResult(text="")
                async for event in self._iterate_remote_events(
                    agent,
                    message,
                    user_context,
                    attachment_files=attachment_files,
                    langsmith_config=langsmith_config,
                    memory_context=memory_context,
                ):
                    if event["type"] == "token":
                        final_text += event["data"]["content"]
                    elif event["type"] == "final":
                        final_text = event["data"]["content"]
                        final_result = A2AExecutionResult(
                            text=final_text,
                            remote_task_id=event["data"].get("remote_task_id"),
                            remote_context_id=event["data"].get("remote_context_id"),
                            remote_task_state=event["data"].get("remote_task_state"),
                        )

                if root_run is not None:
                    root_run.end(
                        outputs={
                            "response": final_result.text,
                            "response_length": len(final_result.text),
                            "streaming": False,
                            "remote_task_id": final_result.remote_task_id,
                            "remote_context_id": final_result.remote_context_id,
                            "remote_task_state": final_result.remote_task_state,
                        }
                    )

        if not final_result.text.strip():
            logger.warning(
                "A2A execute finished with empty response for agent_id=%s",
                agent.agent_id,
            )
        else:
            logger.info(
                "A2A execute finished for agent_id=%s response_len=%s",
                agent.agent_id,
                len(final_result.text),
            )
        return final_result

    async def stream(
        self,
        agent: Agent,
        message: str,
        user_context: Optional[dict[str, Any]] = None,
        attachment_files: Optional[list[dict[str, Any]]] = None,
        memory_context: Optional[A2AMemoryContext] = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        logger.info(
            "Starting A2A stream for agent_id=%s card_url=%s message_len=%s attachment_count=%s",
            agent.agent_id,
            getattr(agent.a2a_config, "card_url", None),
            len(message or ""),
            len(attachment_files or []),
        )
        emitted_token = False
        langsmith_config = self._get_langsmith_config(agent)
        trace_metadata = self._build_trace_metadata(agent, user_context=user_context)

        tracing_cm = nullcontext()
        trace_cm = nullcontext()
        if langsmith_config:
            try:
                import langsmith as ls

                tracing_cm = ls.tracing_context(
                    client=langsmith_config["client"],
                    project_name=langsmith_config["project_name"],
                    enabled=True,
                    tags=self._langsmith_tags(),
                    metadata=trace_metadata,
                )
                trace_cm = ls.trace(
                    name=f"A2A Agent Invocation: {getattr(agent, 'name', 'unknown')}",
                    run_type="chain",
                    project_name=langsmith_config["project_name"],
                    client=langsmith_config["client"],
                    inputs={
                        "message": message,
                        "streaming": True,
                        "history_messages": len(memory_context.history) if memory_context else 0,
                        "continuation_task_id": (
                            memory_context.remote_task_id if memory_context else None
                        ),
                    },
                    metadata=trace_metadata,
                    tags=self._langsmith_tags(),
                )
            except ImportError:
                logger.warning(
                    "LangSmith SDK is unavailable; skipping direct A2A tracing for agent_id=%s",
                    agent.agent_id,
                )

        with tracing_cm:
            with trace_cm as root_run:
                final_text = ""

                async for event in self._iterate_remote_events(
                    agent,
                    message,
                    user_context,
                    attachment_files=attachment_files,
                    langsmith_config=langsmith_config,
                    memory_context=memory_context,
                ):
                    if event["type"] == "token":
                        emitted_token = True
                        final_text += event["data"]["content"]
                        yield event
                    elif event["type"] == "thinking":
                        yield event
                    elif event["type"] == "final":
                        final_text = event["data"]["content"]

                if final_text and not emitted_token:
                    yield {"type": "token", "data": {"content": final_text}}
                elif not final_text.strip():
                    logger.warning(
                        "A2A stream finished without content for agent_id=%s",
                        agent.agent_id,
                    )
                else:
                    logger.info(
                        "A2A stream finished for agent_id=%s response_len=%s emitted_token=%s",
                        agent.agent_id,
                        len(final_text),
                        emitted_token,
                    )

                if root_run is not None:
                    root_run.end(
                        outputs={
                            "response": final_text,
                            "response_length": len(final_text),
                            "streaming": True,
                            "emitted_token": emitted_token,
                        }
                    )

    async def _iterate_remote_events(
        self,
        agent: Agent,
        message: str,
        user_context: Optional[dict[str, Any]] = None,
        attachment_files: Optional[list[dict[str, Any]]] = None,
        langsmith_config: Optional[dict[str, Any]] = None,
        memory_context: Optional[A2AMemoryContext] = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        try:
            import httpx
            from a2a.client import ClientConfig, ClientFactory
            from a2a.types import Message, TransportProtocol
        except ImportError as exc:
            raise RuntimeError(
                "A2A execution requires the optional 'a2a-sdk' dependency to be installed."
            ) from exc

        if not getattr(agent, "a2a_config", None):
            raise ValueError("Agent is not configured as an imported A2A agent")

        base_url, relative_card_path = A2AService.split_card_url(agent.a2a_config.card_url)
        timeout = httpx.Timeout(20.0, read=60.0)

        try:
            trace_cm = nullcontext()
            if langsmith_config:
                try:
                    import langsmith as ls

                    trace_cm = ls.trace(
                        name="Remote A2A Call",
                        run_type="tool",
                        project_name=langsmith_config["project_name"],
                        client=langsmith_config["client"],
                        inputs={
                            "message": message,
                            "base_url": base_url,
                            "relative_card_path": relative_card_path,
                            "attachment_count": len(attachment_files or []),
                            "history_messages": len(memory_context.history) if memory_context else 0,
                            "continuation_task_id": (
                                memory_context.remote_task_id if memory_context else None
                            ),
                        },
                        metadata=self._build_trace_metadata(
                            agent,
                            user_context=user_context,
                        ),
                        tags=self._langsmith_tags() + ["remote-call"],
                    )
                except ImportError:
                    logger.warning(
                        "LangSmith SDK is unavailable; skipping nested A2A tracing for agent_id=%s",
                        agent.agent_id,
                    )

            with trace_cm as remote_run:
                async with A2AService.create_authenticated_httpx_client(
                    card_snapshot=getattr(agent.a2a_config, "remote_agent_metadata", None),
                    auth_config=getattr(agent.a2a_config, "auth_config", None),
                    timeout=timeout,
                    follow_redirects=True,
                ) as httpx_client:
                    logger.info(
                        "Connecting to remote A2A agent for agent_id=%s base_url=%s path=%s",
                        agent.agent_id,
                        base_url,
                        relative_card_path,
                    )
                    client = await ClientFactory.connect(
                        base_url,
                        client_config=ClientConfig(
                            streaming=True,
                            httpx_client=httpx_client,
                            supported_transports=[
                                TransportProtocol.jsonrpc,
                                TransportProtocol.http_json,
                            ],
                        ),
                        relative_card_path=relative_card_path,
                    )
                    logger.info(
                        "Connected to remote A2A agent for agent_id=%s remote_agent_id=%s",
                        agent.agent_id,
                        getattr(agent.a2a_config, "remote_agent_id", None),
                    )

                    async with client:
                        request_message = self._build_request_message(
                            message,
                            attachment_files=attachment_files,
                            memory_context=memory_context,
                        )
                        latest_remote_state = self._initial_remote_state(memory_context)
                        final_text = ""
                        status_updates = 0
                        artifact_updates = 0
                        logger.info(
                            "A2A continuity context for agent_id=%s resume=%s history_messages=%s stored_task_id=%s stored_context_id=%s stored_task_state=%s",
                            agent.agent_id,
                            self._can_resume_remote_task(memory_context),
                            len(memory_context.history) if memory_context else 0,
                            latest_remote_state.get("remote_task_id"),
                            latest_remote_state.get("remote_context_id"),
                            latest_remote_state.get("remote_task_state"),
                        )
                        logger.info(
                            "Sending A2A message for agent_id=%s attachment_count=%s",
                            agent.agent_id,
                            max(len(request_message.parts) - 1, 0),
                        )

                        send_kwargs = self._build_send_message_kwargs(
                            client,
                            memory_context=memory_context,
                        )
                        async for response in client.send_message(request_message, **send_kwargs):
                            if isinstance(response, Message):
                                message_remote_state = self._extract_remote_state_from_message(response)
                                latest_remote_state = self._merge_remote_state(
                                    latest_remote_state,
                                    message_remote_state,
                                )
                                text = self._message_to_text(response)
                                logger.info(
                                    "A2A message response state for agent_id=%s task_id=%s context_id=%s",
                                    agent.agent_id,
                                    message_remote_state.get("remote_task_id"),
                                    message_remote_state.get("remote_context_id"),
                                )
                                logger.debug(
                                    "Received direct A2A message response for agent_id=%s content_len=%s",
                                    agent.agent_id,
                                    len(text),
                                )
                                if text:
                                    final_text = text
                                    yield {"type": "token", "data": {"content": text}}
                                continue

                            task, update = response
                            task_remote_state = self._extract_remote_state_from_task(task)
                            latest_remote_state = self._merge_remote_state(
                                latest_remote_state,
                                task_remote_state,
                            )
                            logger.info(
                                "A2A task response state for agent_id=%s task_id=%s context_id=%s task_state=%s update_kind=%s",
                                agent.agent_id,
                                task_remote_state.get("remote_task_id"),
                                task_remote_state.get("remote_context_id"),
                                task_remote_state.get("remote_task_state"),
                                getattr(update, "kind", None),
                            )
                            if update is not None:
                                if getattr(update, "kind", None) == "status-update":
                                    status_updates += 1
                                    state = getattr(update.status.state, "value", str(update.status.state))
                                    status_text = self._message_to_text(update.status.message)
                                    logger.info(
                                        "A2A status update for agent_id=%s state=%s message=%s",
                                        agent.agent_id,
                                        state,
                                        status_text,
                                    )
                                    payload = status_text or f"Remote agent status: {state}"
                                    yield {
                                        "type": "thinking",
                                        "data": {
                                            "content": payload,
                                            "message": payload,
                                        },
                                    }
                                elif getattr(update, "kind", None) == "artifact-update":
                                    artifact_updates += 1
                                    artifact_text = self._artifact_to_text(update.artifact)
                                    logger.debug(
                                        "A2A artifact update for agent_id=%s content_len=%s",
                                        agent.agent_id,
                                        len(artifact_text),
                                    )
                                    if artifact_text:
                                        final_text = artifact_text
                                        yield {"type": "token", "data": {"content": artifact_text}}

                            task_text = self._task_to_text(task)
                            if task_text:
                                logger.debug(
                                    "A2A task snapshot for agent_id=%s content_len=%s",
                                    agent.agent_id,
                                    len(task_text),
                                )
                                final_text = task_text

                        if remote_run is not None:
                            remote_run.end(
                                outputs={
                                    "response": final_text.strip(),
                                    "response_length": len(final_text.strip()),
                                    "status_update_count": status_updates,
                                    "artifact_update_count": artifact_updates,
                                    "remote_task_id": latest_remote_state.get("remote_task_id"),
                                    "remote_context_id": latest_remote_state.get("remote_context_id"),
                                    "remote_task_state": latest_remote_state.get("remote_task_state"),
                                }
                            )

                        logger.info(
                            "A2A final remote state for agent_id=%s task_id=%s context_id=%s task_state=%s response_len=%s",
                            agent.agent_id,
                            latest_remote_state.get("remote_task_id"),
                            latest_remote_state.get("remote_context_id"),
                            latest_remote_state.get("remote_task_state"),
                            len(final_text.strip()),
                        )
                        yield {
                            "type": "final",
                            "data": {
                                "content": final_text.strip(),
                                **latest_remote_state,
                            },
                        }
        except Exception:
            logger.error(
                "A2A execution failed for agent_id=%s card_url=%s",
                agent.agent_id,
                getattr(agent.a2a_config, "card_url", None),
                exc_info=True,
            )
            raise

    def _build_request_message(
        self,
        message: str,
        *,
        attachment_files: Optional[list[dict[str, Any]]] = None,
        memory_context: Optional[A2AMemoryContext] = None,
    ) -> Any:
        try:
            from a2a.types import FilePart, FileWithBytes, Message, Part, Role, TextPart
        except ImportError as exc:
            raise RuntimeError(
                "A2A execution requires the optional 'a2a-sdk' dependency to be installed."
            ) from exc

        projected_message = self._compose_request_text(message, memory_context)
        parts = [Part(TextPart(text=projected_message or ""))]
        for file_data in attachment_files or []:
            file_part = self._build_file_part(
                file_data,
                FilePart=FilePart,
                FileWithBytes=FileWithBytes,
            )
            if file_part is not None:
                parts.append(Part(file_part))

        message_kwargs: dict[str, Any] = {
            "role": Role.user,
            "parts": parts,
            "messageId": str(uuid4()),
        }
        if self._can_resume_remote_task(memory_context):
            message_kwargs["taskId"] = memory_context.remote_task_id
            message_kwargs["contextId"] = memory_context.remote_context_id

        return Message(**message_kwargs)

    def _compose_request_text(
        self,
        message: str,
        memory_context: Optional[A2AMemoryContext],
    ) -> str:
        return message or ""

    def _build_send_message_kwargs(
        self,
        client: Any,
        *,
        memory_context: Optional[A2AMemoryContext],
    ) -> dict[str, Any]:
        """Pass optional send configuration only when the SDK client supports it."""
        kwargs: dict[str, Any] = {}
        param_names, accepts_kwargs = self._get_callable_parameter_names(client.send_message)

        send_configuration = self._build_send_configuration(memory_context)
        if send_configuration is not None:
            for candidate_name in (
                "configuration",
                "send_configuration",
                "message_configuration",
                "message_send_configuration",
            ):
                if candidate_name in param_names or accepts_kwargs:
                    kwargs[candidate_name] = send_configuration
                    break

        return kwargs

    def _build_send_configuration(
        self,
        memory_context: Optional[A2AMemoryContext],
    ) -> Any | None:
        if not memory_context or memory_context.history_length is None:
            return None

        try:
            from a2a.types import MessageSendConfiguration
        except ImportError:
            return None

        return MessageSendConfiguration(historyLength=memory_context.history_length)

    def _get_callable_parameter_names(self, func: Any) -> tuple[set[str], bool]:
        try:
            signature = inspect.signature(func)
        except (TypeError, ValueError):
            return set(), True

        names = set(signature.parameters.keys())
        accepts_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        return names, accepts_kwargs

    def _can_resume_remote_task(self, memory_context: Optional[A2AMemoryContext]) -> bool:
        if not memory_context:
            return False
        if not memory_context.remote_task_id or not memory_context.remote_context_id:
            return False

        state = (memory_context.remote_task_state or "").strip().lower()
        if not state:
            return True
        return state not in self.TERMINAL_TASK_STATES

    def _initial_remote_state(
        self,
        memory_context: Optional[A2AMemoryContext],
    ) -> dict[str, Optional[str]]:
        return {
            "remote_task_id": memory_context.remote_task_id if memory_context else None,
            "remote_context_id": memory_context.remote_context_id if memory_context else None,
            "remote_task_state": memory_context.remote_task_state if memory_context else None,
        }

    def _merge_remote_state(
        self,
        current: dict[str, Optional[str]],
        update: dict[str, Optional[str]],
    ) -> dict[str, Optional[str]]:
        merged = dict(current)
        for key, value in update.items():
            if value:
                merged[key] = value
        return merged

    def _extract_remote_state_from_task(self, task: Any) -> dict[str, Optional[str]]:
        if task is None:
            return {}

        task_status = getattr(task, "status", None)
        raw_state = getattr(task_status, "state", None)
        task_state = getattr(raw_state, "value", raw_state)
        if task_state is not None:
            task_state = str(task_state)

        return {
            "remote_task_id": self._get_first_attr(task, "id", "taskId", "task_id"),
            "remote_context_id": self._get_first_attr(task, "contextId", "context_id"),
            "remote_task_state": task_state,
        }

    def _extract_remote_state_from_message(self, message: Any) -> dict[str, Optional[str]]:
        if message is None:
            return {}

        return {
            "remote_task_id": self._get_first_attr(message, "taskId", "task_id"),
            "remote_context_id": self._get_first_attr(message, "contextId", "context_id"),
            "remote_task_state": None,
        }

    def _get_first_attr(self, obj: Any, *names: str) -> Any:
        for name in names:
            value = getattr(obj, name, None)
            if value is not None:
                return value
        return None

    def _build_file_part(
        self,
        file_data: dict[str, Any],
        *,
        FilePart: Any,
        FileWithBytes: Any,
    ) -> Any | None:
        absolute_path = self._resolve_attachment_path(file_data)
        if not absolute_path:
            logger.warning(
                "Skipping A2A attachment without readable file path: file_id=%s filename=%s",
                file_data.get("file_id"),
                file_data.get("filename"),
            )
            return None

        try:
            with open(absolute_path, "rb") as handle:
                encoded_bytes = base64.b64encode(handle.read()).decode("utf-8")
        except OSError as exc:
            logger.warning(
                "Failed to read A2A attachment %s from %s: %s",
                file_data.get("filename") or absolute_path,
                absolute_path,
                exc,
            )
            return None

        filename = file_data.get("filename") or os.path.basename(absolute_path)
        mime_type = self._resolve_attachment_mime_type(file_data, absolute_path)

        return FilePart(
            file=FileWithBytes(
                bytes=encoded_bytes,
                mimeType=mime_type,
                name=filename,
            ),
            metadata={
                "file_id": file_data.get("file_id"),
                "file_type": file_data.get("type"),
            },
        )

    def _resolve_attachment_path(self, file_data: dict[str, Any]) -> str | None:
        raw_path = (file_data.get("file_path") or "").strip()
        if not raw_path:
            return None

        if os.path.isabs(raw_path):
            return raw_path if os.path.exists(raw_path) else None

        from utils.config import get_app_config

        tmp_base_folder = os.path.abspath(get_app_config()["TMP_BASE_FOLDER"])
        candidate = os.path.abspath(os.path.join(tmp_base_folder, raw_path.lstrip("/\\")))
        if candidate != tmp_base_folder and not candidate.startswith(f"{tmp_base_folder}{os.sep}"):
            logger.warning("Rejected A2A attachment path outside TMP_BASE_FOLDER: %s", raw_path)
            return None

        return candidate if os.path.exists(candidate) else None

    def _resolve_attachment_mime_type(
        self,
        file_data: dict[str, Any],
        absolute_path: str,
    ) -> str:
        mime_type = file_data.get("mime_type")
        if isinstance(mime_type, str) and mime_type.strip():
            return mime_type.strip()

        guessed_mime, _ = mimetypes.guess_type(file_data.get("filename") or absolute_path)
        if guessed_mime:
            return guessed_mime

        file_type = file_data.get("type")
        if file_type == "image":
            return "image/jpeg"
        if file_type == "pdf":
            return "application/pdf"
        if file_type == "text":
            return "text/plain"
        return "application/octet-stream"

    def _task_to_text(self, task: Any) -> str:
        if task is None:
            return ""

        status_message = self._message_to_text(getattr(task.status, "message", None))
        artifact_texts = [self._artifact_to_text(artifact) for artifact in (task.artifacts or [])]
        artifact_texts = [text for text in artifact_texts if text]

        parts = [text for text in [status_message, *artifact_texts] if text]
        return "\n\n".join(parts)

    def _artifact_to_text(self, artifact: Any) -> str:
        if artifact is None:
            return ""
        rendered_parts = [self._part_to_text(part) for part in getattr(artifact, "parts", []) or []]
        rendered_parts = [part for part in rendered_parts if part]
        header = getattr(artifact, "name", None) or getattr(artifact, "description", None)
        body = "\n".join(rendered_parts)
        return "\n".join(part for part in [header, body] if part)

    def _message_to_text(self, message: Any) -> str:
        if message is None:
            return ""
        parts = [self._part_to_text(part) for part in getattr(message, "parts", []) or []]
        parts = [part for part in parts if part]
        return "\n".join(parts)

    def _part_to_text(self, part: Any) -> str:
        root = getattr(part, "root", part)
        if root is None:
            return ""

        if hasattr(root, "text"):
            return root.text or ""
        if hasattr(root, "data"):
            return json.dumps(root.data, ensure_ascii=True)
        if hasattr(root, "file"):
            file_name = getattr(root.file, "name", None)
            file_uri = getattr(root.file, "file_with_uri", None)
            if file_name and file_uri:
                return f"{file_name}: {file_uri}"
            if file_name:
                return file_name

        logger.debug("Unsupported A2A part payload: %s", type(root))
        return ""
