import base64
import json
import os
from tempfile import SpooledTemporaryFile
from typing import Any, Optional
from urllib.parse import quote, urlencode, urlparse

import httpx
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import DataPart, FilePart, FileWithBytes, FileWithUri, Part, TaskState, TextPart
from db.database import SessionLocal
from fastapi import UploadFile
from starlette.datastructures import Headers
from models.agent import Agent
from services.agent_streaming_service import AgentStreamingService
from services.agent_service import AgentService
from services.file_management_service import FileManagementService
from utils.logger import get_logger
from utils.security import generate_signature

logger = get_logger(__name__)


class MattinA2AAgentExecutor(AgentExecutor):
    """A2A SDK executor that bridges requests into Mattin AI agent execution."""

    TEXT_ARTIFACT_ID = "response-text"

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=context.task_id,
            context_id=context.context_id,
        )

        call_state = self._get_call_state(context)
        session, owns_session = self._get_db_session(call_state)
        temp_uploads: list[UploadFile] = []
        try:
            agent = self._load_agent(session, call_state["agent_id"], call_state["app_id"])
            message_text, upload_files = await self._extract_message_inputs(context)
            temp_uploads = upload_files

            await updater.submit()
            await updater.start_work()

            conversation_id = self._get_conversation_id(context)
            user_context = dict(call_state["user_context"])
            if conversation_id is not None:
                user_context["conversation_id"] = conversation_id
            stream_service = AgentStreamingService(session)
            include_existing_files = None if conversation_id is not None else []

            text_started = False
            final_response_text = ""
            final_conversation_id: Optional[int] = conversation_id
            stream = stream_service.stream_agent_chat(
                agent_id=agent.agent_id,
                message=message_text,
                file_references=await FileManagementService().resolve_chat_files(
                    files=upload_files or None,
                    file_reference_ids=include_existing_files,
                    agent_id=agent.agent_id,
                    user_context=user_context,
                    conversation_id=conversation_id,
                ),
                search_params=None,
                user_context=user_context,
                conversation_id=conversation_id,
                db=session,
            )

            async for raw_event in stream:
                event_type, payload = self._parse_sse_event(raw_event)
                if event_type == "metadata":
                    conv_id = payload.get("conversation_id")
                    if conv_id is not None:
                        final_conversation_id = conv_id
                        await updater.update_status(
                            TaskState.working,
                            metadata={"conversation_id": conv_id, "agent_id": agent.agent_id},
                        )
                elif event_type == "token":
                    token = payload.get("content", "")
                    final_response_text += token
                    if token:
                        await updater.add_artifact(
                            parts=[Part(root=TextPart(text=token))],
                            artifact_id=self.TEXT_ARTIFACT_ID,
                            name="response.txt",
                            append=text_started,
                            last_chunk=False,
                        )
                        text_started = True
                elif event_type == "thinking":
                    message = payload.get("message")
                    if message:
                        await updater.update_status(
                            TaskState.working,
                            metadata={"progress_message": message},
                        )
                elif event_type == "done":
                    final_conversation_id = payload.get("conversation_id", final_conversation_id)
                    response = payload.get("response", "")
                    final_response_text = self._stringify_response(response, fallback=final_response_text)
                    if not text_started and final_response_text:
                        await updater.add_artifact(
                            parts=[Part(root=TextPart(text=final_response_text))],
                            artifact_id=self.TEXT_ARTIFACT_ID,
                            name="response.txt",
                            append=False,
                            last_chunk=True,
                        )
                    files = payload.get("files") or []
                    if files:
                        await self._publish_file_artifacts(
                            updater=updater,
                            files=files,
                            agent_id=agent.agent_id,
                            user_context=user_context,
                            conversation_id=final_conversation_id,
                            base_url=call_state["base_url"],
                        )

                    message = updater.new_agent_message(
                        [Part(root=TextPart(text=final_response_text or "Completed"))],
                        metadata={"conversation_id": final_conversation_id} if final_conversation_id else None,
                    )
                    await updater.update_status(
                        TaskState.input_required,
                        message=message,
                        final=True,
                        metadata={"conversation_id": final_conversation_id} if final_conversation_id else None,
                    )
                    return
                elif event_type == "error":
                    error_message = payload.get("message", "Agent execution failed")
                    await updater.failed(
                        updater.new_agent_message([Part(root=TextPart(text=error_message))])
                    )
                    return

            await updater.update_status(
                TaskState.input_required,
                message=updater.new_agent_message(
                    [Part(root=TextPart(text=final_response_text or "Ready for next input."))],
                    metadata={"conversation_id": final_conversation_id} if final_conversation_id else None,
                ),
                final=True,
                metadata={"conversation_id": final_conversation_id} if final_conversation_id else None,
            )
        except Exception as exc:
            logger.error("A2A execution failed: %s", exc, exc_info=True)
            await updater.failed(
                updater.new_agent_message(
                    [Part(root=TextPart(text=f"A2A execution failed: {str(exc)}"))]
                )
            )
        finally:
            for upload in temp_uploads:
                try:
                    await upload.close()
                except Exception:
                    pass
            if owns_session:
                session.close()

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=context.task_id,
            context_id=context.context_id,
        )
        await updater.cancel(
            updater.new_agent_message(
                [Part(root=TextPart(text="Task cancelled by client request."))]
            )
        )

    def _get_call_state(self, context: RequestContext) -> dict[str, Any]:
        call_context = context.call_context
        if not call_context or not isinstance(call_context.state, dict):
            raise ValueError("Missing A2A call context")
        state = call_context.state.get("a2a")
        if not state:
            raise ValueError("Missing Mattin A2A routing state")
        return state

    def _get_db_session(self, call_state: dict[str, Any]):
        session = call_state.get("db_session")
        if session is not None:
            return session, False
        return SessionLocal(), True

    def _load_agent(self, db, agent_id: int, app_id: int) -> Agent:
        agent = AgentService().get_agent(db, agent_id)
        if not agent or agent.app_id != app_id or not getattr(agent, "a2a_enabled", False):
            raise ValueError("A2A agent not found")
        return agent

    def _get_conversation_id(self, context: RequestContext) -> Optional[int]:
        if context.current_task and context.current_task.metadata:
            conversation_id = context.current_task.metadata.get("conversation_id")
            if conversation_id not in (None, ""):
                return int(conversation_id)
        return None

    async def _extract_message_inputs(
        self, context: RequestContext
    ) -> tuple[str, list[UploadFile]]:
        if not context.message:
            raise ValueError("Missing A2A request payload")

        text_parts: list[str] = []
        upload_files: list[UploadFile] = []

        for part_wrapper in context.message.parts:
            part = part_wrapper.root
            if isinstance(part, TextPart):
                text_parts.append(part.text)
            elif isinstance(part, DataPart):
                text_parts.append(self._data_part_to_text(part.data))
            elif isinstance(part, FilePart):
                upload_files.append(await self._file_part_to_upload(part))
            else:
                raise ValueError(f"Unsupported A2A part type: {part.kind}")

        return "\n".join([p for p in text_parts if p]).strip(), upload_files

    def _data_part_to_text(self, data: Any) -> str:
        """Convert structured A2A data payloads into stable text for the agent."""
        try:
            serialized = json.dumps(data, ensure_ascii=True, sort_keys=True)
        except TypeError:
            serialized = json.dumps(data, ensure_ascii=True, default=str)
        return f"[Structured data]\n{serialized}"

    async def _file_part_to_upload(self, part: FilePart) -> UploadFile:
        file_value = part.file
        if isinstance(file_value, FileWithBytes):
            data = base64.b64decode(file_value.bytes)
            filename = file_value.name or "attachment"
            content_type = file_value.mime_type
        elif isinstance(file_value, FileWithUri):
            parsed = urlparse(file_value.uri)
            data = await self._download_file_bytes(file_value.uri, parsed.scheme)
            filename = file_value.name or os.path.basename(parsed.path) or "attachment"
            content_type = file_value.mime_type
        else:
            raise ValueError("Unsupported file payload")

        temp_file = SpooledTemporaryFile(max_size=1024 * 1024)
        temp_file.write(data)
        temp_file.seek(0)
        upload = UploadFile(
            file=temp_file,
            filename=filename,
            headers=Headers({"content-type": content_type}) if content_type else None,
        )
        return upload

    async def _download_file_bytes(self, uri: str, scheme: str | None) -> bytes:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(uri)
                response.raise_for_status()
                return response.content
        except httpx.HTTPError as exc:
            if scheme != "https":
                return self._build_remote_file_placeholder(uri, exc)

        logger.warning(
            "Retrying HTTPS file download without certificate verification for A2A file URI: %s",
            uri,
        )
        try:
            async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
                response = await client.get(uri)
                response.raise_for_status()
                return response.content
        except httpx.HTTPError as exc:
            return self._build_remote_file_placeholder(uri, exc)

    def _build_remote_file_placeholder(self, uri: str, exc: Exception) -> bytes:
        logger.warning(
            "Falling back to synthetic file content for unreachable A2A file URI %s: %s",
            uri,
            exc,
        )
        placeholder = {
            "uri": uri,
            "warning": "Remote file content could not be fetched; using placeholder content.",
            "error": str(exc),
        }
        return json.dumps(placeholder, ensure_ascii=True, sort_keys=True).encode("utf-8")

    def _parse_sse_event(self, raw_event: str) -> tuple[str, dict[str, Any]]:
        payload = raw_event.strip()
        if "\n" in payload:
            data_lines = [
                line[5:].strip() if line.startswith("data:") else line.strip()
                for line in payload.splitlines()
                if line.strip()
            ]
            payload = "\n".join(data_lines)
        elif payload.startswith("data:"):
            payload = payload[5:].strip()

        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            payload = self._balance_json_payload(payload)
            event = json.loads(payload)
        return event["type"], event.get("data", {})

    def _balance_json_payload(self, payload: str) -> str:
        balanced = payload
        curly_diff = balanced.count("{") - balanced.count("}")
        square_diff = balanced.count("[") - balanced.count("]")
        if square_diff > 0:
            balanced += "]" * square_diff
        if curly_diff > 0:
            balanced += "}" * curly_diff
        return balanced

    def _stringify_response(self, response: Any, fallback: str = "") -> str:
        if isinstance(response, str):
            return response
        if response in (None, ""):
            return fallback
        return json.dumps(response, ensure_ascii=True, indent=2)

    async def _publish_file_artifacts(
        self,
        updater: TaskUpdater,
        files: list[dict[str, Any]],
        agent_id: int,
        user_context: dict[str, Any],
        conversation_id: Optional[int],
        base_url: str,
    ) -> None:
        attached = await FileManagementService().list_attached_files(
            agent_id=agent_id,
            user_context=user_context,
            conversation_id=str(conversation_id) if conversation_id else None,
        )
        attached_by_id = {item["file_id"]: item for item in attached}

        for file_info in files:
            file_id = file_info.get("file_id")
            attached_file = attached_by_id.get(file_id)
            if not attached_file or not attached_file.get("file_path"):
                continue
            file_path = attached_file["file_path"].lstrip("/")
            filename = attached_file.get("filename") or file_info.get("filename") or "output"
            mime_type = attached_file.get("mime_type") or "application/octet-stream"
            download_url = self._build_download_url(
                base_url=base_url,
                file_path=file_path,
                filename=filename,
                user_id=user_context["user_id"],
            )
            await updater.add_artifact(
                parts=[
                    Part(
                        root=FilePart(
                            file=FileWithUri(
                                uri=download_url,
                                name=filename,
                                mime_type=mime_type,
                            )
                        )
                    )
                ],
                artifact_id=f"file-{file_id}",
                name=filename,
                metadata={"file_id": file_id, "mime_type": mime_type},
                append=False,
                last_chunk=True,
            )

    def _build_download_url(
        self,
        base_url: str,
        file_path: str,
        filename: str,
        user_id: str,
    ) -> str:
        sig = generate_signature(file_path, user_id)
        encoded_path = quote(f"static/{file_path}", safe="/")
        query_params = urlencode({
            "user": user_id,
            "sig": sig,
            "filename": filename,
        })
        return f"{base_url.rstrip('/')}/{encoded_path}?{query_params}"
