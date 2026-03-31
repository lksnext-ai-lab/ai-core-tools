from __future__ import annotations

import json
from contextlib import nullcontext
from typing import Any, AsyncGenerator, Optional

from models.agent import Agent
from services.a2a_service import A2AService
from utils.logger import get_logger

logger = get_logger(__name__)


class A2AExecutorService:
    """Focused execution adapter for imported external A2A agents."""

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
            "remote_skill_id": getattr(a2a_config, "remote_skill_id", None),
            "remote_skill_name": getattr(a2a_config, "remote_skill_name", None),
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
    ) -> str:
        logger.info(
            "Starting A2A execute for agent_id=%s card_url=%s skill_id=%s message_len=%s",
            agent.agent_id,
            getattr(agent.a2a_config, "card_url", None),
            getattr(agent.a2a_config, "remote_skill_id", None),
            len(message or ""),
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
                    langsmith_config=langsmith_config,
                ):
                    if event["type"] == "token":
                        final_text += event["data"]["content"]
                    elif event["type"] == "final":
                        final_text = event["data"]["content"]

                if root_run is not None:
                    root_run.end(
                        outputs={
                            "response": final_text,
                            "response_length": len(final_text),
                            "streaming": False,
                        }
                    )

        if not final_text.strip():
            logger.warning(
                "A2A execute finished with empty response for agent_id=%s skill_id=%s",
                agent.agent_id,
                getattr(agent.a2a_config, "remote_skill_id", None),
            )
        else:
            logger.info(
                "A2A execute finished for agent_id=%s response_len=%s",
                agent.agent_id,
                len(final_text),
            )
        return final_text

    async def stream(
        self,
        agent: Agent,
        message: str,
        user_context: Optional[dict[str, Any]] = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        logger.info(
            "Starting A2A stream for agent_id=%s card_url=%s skill_id=%s message_len=%s",
            agent.agent_id,
            getattr(agent.a2a_config, "card_url", None),
            getattr(agent.a2a_config, "remote_skill_id", None),
            len(message or ""),
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
                    langsmith_config=langsmith_config,
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
                        "A2A stream finished without content for agent_id=%s skill_id=%s",
                        agent.agent_id,
                        getattr(agent.a2a_config, "remote_skill_id", None),
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
        langsmith_config: Optional[dict[str, Any]] = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        try:
            import httpx
            from a2a.client import ClientConfig, ClientFactory, create_text_message_object
            from a2a.types import Message, TransportProtocol
        except ImportError as exc:
            raise RuntimeError(
                "A2A execution requires the optional 'a2a-sdk' dependency to be installed."
            ) from exc

        if not getattr(agent, "a2a_config", None):
            raise ValueError("Agent is not configured as an imported A2A agent")

        base_url, relative_card_path = A2AService.split_card_url(agent.a2a_config.card_url)
        timeout = httpx.Timeout(20.0, read=60.0)
        request_metadata = {
            "imported_skill_id": agent.a2a_config.remote_skill_id,
            "imported_skill_name": agent.a2a_config.remote_skill_name,
        }

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
                            "request_metadata": request_metadata,
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
                async with httpx.AsyncClient(
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
                        "Connected to remote A2A agent for agent_id=%s using skill_id=%s",
                        agent.agent_id,
                        agent.a2a_config.remote_skill_id,
                    )

                    async with client:
                        request_message = create_text_message_object(content=message)
                        final_text = ""
                        status_updates = 0
                        artifact_updates = 0
                        logger.info(
                            "Sending A2A message for agent_id=%s skill_id=%s metadata=%s",
                            agent.agent_id,
                            agent.a2a_config.remote_skill_id,
                            request_metadata,
                        )

                        async for response in client.send_message(
                            request_message,
                            request_metadata=request_metadata,
                        ):
                            if isinstance(response, Message):
                                text = self._message_to_text(response)
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
                                }
                            )

                        yield {"type": "final", "data": {"content": final_text.strip()}}
        except Exception:
            logger.error(
                "A2A execution failed for agent_id=%s card_url=%s skill_id=%s",
                agent.agent_id,
                getattr(agent.a2a_config, "card_url", None),
                getattr(agent.a2a_config, "remote_skill_id", None),
                exc_info=True,
            )
            raise

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
