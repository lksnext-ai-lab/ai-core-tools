import base64
import httpx
import ipaddress
import mimetypes
import socket
import tempfile
import time
import uuid
import json
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Annotated
from urllib.parse import urlparse

from db.database import get_db
from models.app import App
from services.agent_execution_service import AgentExecutionService
from services.agent_streaming_service import AgentStreamingService
from services.agent_service import AgentService
from services.file_management_service import FileManagementService
from utils.logger import get_logger

from .auth import get_openai_api_key_auth, validate_api_key_for_app, create_api_key_user_context
from .schemas_openai import (
    OpenAIChatCompletionRequest,
    OpenAIChatCompletionResponse,
    OpenAIModelListResponse,
    OpenAIModel,
    OpenAIChoice,
    OpenAIChoiceMessage,
    OpenAITokenUsage
)

logger = get_logger(__name__)
openai_router = APIRouter()

# Maximum bytes we will ever buffer from a remote image URL, regardless of
# what the app's max_file_size_mb is configured to.  This acts as an absolute
# hard ceiling so a misconfigured or unlimited app cannot be abused for a
# large-download amplification attack.
_MAX_IMAGE_DOWNLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


def _validate_image_url(url: str) -> None:
    """Raise HTTPException(400) for URLs that could be used for SSRF.

    Checks performed:
    - Scheme must be http or https (blocks file://, ftp://, gopher://, etc.).
    - Hostname must resolve and must not be a private, loopback, link-local,
      multicast, or otherwise reserved address (RFC 1918 / RFC 4193 / etc.).
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail=f"Image URL scheme '{parsed.scheme}' is not allowed. Only http/https URLs are accepted.",
        )

    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="Image URL has no hostname.")

    try:
        # Resolve to an IP address (IPv4 or IPv6).
        addr_str = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)[0][4][0]
        addr = ipaddress.ip_address(addr_str)
    except (socket.gaierror, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Image URL hostname could not be resolved: {exc}",
        )

    if (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    ):
        raise HTTPException(
            status_code=400,
            detail="Image URL resolves to a private or reserved IP address and is not allowed.",
        )

def get_app_by_identifier(db: Session, app_identifier: str) -> App:
    if app_identifier.isdigit():
        app = db.query(App).filter(App.app_id == int(app_identifier)).first()
    else:
        app = db.query(App).filter(App.slug == app_identifier).first()
    
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    if not app.enable_openai_api:
        raise HTTPException(status_code=403, detail="OpenAI API exposure is disabled for this App")
    return app

@openai_router.get(
    "/models", 
    response_model=OpenAIModelListResponse,
    tags=["OpenAI Compatible API"],
    summary="List available models",
    description="Lists the currently available memoryless agents that can be used with the OpenAI-compatible chat completions endpoint."
)
async def list_models(
    app_id: str,
    api_key: Annotated[str, Depends(get_openai_api_key_auth)],
    db: Annotated[Session, Depends(get_db)]
):
    app = get_app_by_identifier(db, app_id)
    validate_api_key_for_app(app.app_id, api_key, db)
    
    # We only return memoryless agents
    agent_service = AgentService()
    agents = agent_service.get_agents(db, app.app_id)
    
    models = []
    for agent in agents:
        if not agent.has_memory:
            models.append(OpenAIModel(
                id=str(agent.agent_id),
                created=int(agent.create_date.timestamp()) if hasattr(agent, 'create_date') and agent.create_date else int(time.time()),
                owned_by=app.name
            ))
            
    return OpenAIModelListResponse(data=models)

@openai_router.post(
    "/chat/completions",
    tags=["OpenAI Compatible API"],
    summary="Create chat completion",
    description="Creates a model response for the given chat conversation. Supports streaming with `stream=True`. Only works with memoryless agents.",
    responses={
        200: {
            "description": "Successful chat completion response. Returns standard JSON schema if stream is false, or an SSE event stream if stream is true.",
            "model": OpenAIChatCompletionResponse,
            "content": {
                "text/event-stream": {"schema": {"type": "string"}}
            }
        }
    }
)
async def chat_completions(
    app_id: str,
    request: OpenAIChatCompletionRequest,
    api_key: Annotated[str, Depends(get_openai_api_key_auth)],
    db: Annotated[Session, Depends(get_db)]
):
    app = get_app_by_identifier(db, app_id)
    validate_api_key_for_app(app.app_id, api_key, db)

    # Explicitly reject unsupported OpenAI knobs that would otherwise be silently ignored.
    unsupported_params: List[str] = []
    if getattr(request, "temperature", None) is not None:
        unsupported_params.append("temperature")
    if getattr(request, "max_tokens", None) is not None:
        unsupported_params.append("max_tokens")
    if unsupported_params:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported parameter(s) for this endpoint: "
                + ", ".join(unsupported_params)
                + ". This OpenAI-compatible endpoint currently uses the agent's "
                "configured settings for these values."
            ),
        )
    
    try:
        agent_id = int(request.model)
    except ValueError:
        raise HTTPException(status_code=400, detail="Model must be the agent ID")
        
    agent_service = AgentService()
    agent = agent_service.get_agent(db, agent_id)
    
    if not agent or agent.app_id != app.app_id:
        raise HTTPException(status_code=404, detail="Agent not found")
        
    if agent.has_memory:
        raise HTTPException(
            status_code=400, 
            detail="Agent has memory enabled. OpenAI API only supports memoryless agents."
        )
        
    user_context = create_api_key_user_context(app.app_id, api_key)
    
    if not request.messages:
        raise HTTPException(status_code=400, detail="Messages array cannot be empty")
        
    # Process multipart messages and accumulate file references
    formatted_message = ""
    file_references = []
    file_service = FileManagementService()

    # First, filter out system messages
    non_system_messages = [msg for msg in request.messages if msg.role != "system"]
    
    history_texts = []
    latest_message_text = ""
    latest_role = "user"
    
    for i, msg in enumerate(non_system_messages):
        is_last = (i == len(non_system_messages) - 1)
        if is_last:
            latest_role = msg.role
            
        msg_text = ""
        if isinstance(msg.content, str):
            msg_text = msg.content
        elif isinstance(msg.content, list):
            part_texts = []
            for part in msg.content:
                if part.get("type") == "text":
                    part_texts.append(part.get("text", ""))
                elif part.get("type") == "image_url":
                    image_url_obj = part.get("image_url", {})
                    url = image_url_obj.get("url", "")
                    img_data = None
                    ext = ".jpg"
                    
                    max_image_size_mb: int = getattr(app, 'max_file_size_mb', 0) or 0

                    if url.startswith("data:image/"):
                        try:
                            header, base64_data = url.split(",", 1)
                            mime_type = header.split(";")[0].replace("data:", "")
                            ext = mimetypes.guess_extension(mime_type) or ".jpg"
                            img_data = base64.b64decode(base64_data)
                        except Exception as e:
                            logger.error(f"Failed to parse base64 image: {e}")
                            continue
                    elif url.startswith("http"):
                        try:
                            _validate_image_url(url)
                            byte_cap = (
                                max_image_size_mb * 1024 * 1024
                                if max_image_size_mb > 0
                                else _MAX_IMAGE_DOWNLOAD_BYTES
                            )
                            chunks: list[bytes] = []
                            total = 0
                            async with httpx.AsyncClient() as client:
                                async with client.stream("GET", url, timeout=10.0) as resp:
                                    resp.raise_for_status()
                                    content_type = resp.headers.get("content-type", "image/jpeg")
                                    ext = mimetypes.guess_extension(content_type) or ".jpg"
                                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                                        total += len(chunk)
                                        if total > byte_cap:
                                            raise HTTPException(
                                                status_code=413,
                                                detail=(
                                                    f"Remote image exceeds the maximum allowed size "
                                                    f"({byte_cap // (1024 * 1024)}MB)."
                                                ),
                                            )
                                        chunks.append(chunk)
                            img_data = b"".join(chunks)
                        except HTTPException:
                            raise
                        except Exception as e:
                            logger.error(f"Failed to download image URL {url}: {e}")
                            continue

                    if img_data:
                        if max_image_size_mb > 0:
                            img_size_mb = len(img_data) / (1024 * 1024)
                            if img_size_mb > max_image_size_mb:
                                raise HTTPException(
                                    status_code=413,
                                    detail=(
                                        f"Image size ({img_size_mb:.2f}MB) exceeds the maximum "
                                        f"allowed ({max_image_size_mb}MB) for this app."
                                    ),
                                )
                        try:
                            temp_f = tempfile.SpooledTemporaryFile(max_size=1024*1024*10)
                            temp_f.write(img_data)
                            temp_f.seek(0)
                            upload_file = UploadFile(file=temp_f, filename=f"image_{uuid.uuid4().hex[:8]}{ext}")
                            file_ref = await file_service.upload_file(
                                file=upload_file,
                                agent_id=agent_id,
                                user_context=user_context
                            )
                            file_references.append(file_ref)
                        except Exception as e:
                            logger.error(f"Failed to process image payload: {e}")
                            
            msg_text = " ".join(part_texts)
            
        if is_last:
            latest_message_text = msg_text
        else:
            history_texts.append(f"{msg.role}: {msg_text}")
            
    # Now construct the structured formatting
    formatted_message = ""
    if history_texts:
        formatted_message += "--- Conversation History ---\n"
        formatted_message += "\n\n".join(history_texts)
        formatted_message += "\n--- End of History ---\n\n"
        
    formatted_message += f"[Latest Input]\n{latest_role}: {latest_message_text}"
        
    if request.stream:
        streaming_service = AgentStreamingService(db)
        generator = streaming_service.stream_agent_chat(
            agent_id=agent_id,
            message=formatted_message,
            file_references=file_references,
            search_params=None,
            user_context=user_context,
            conversation_id=None,
            db=db,
        )
        
        async def openai_sse_generator():
            completion_id = f"chatcmpl-{uuid.uuid4()}"
            yield f"data: {json.dumps({'id': completion_id, 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model': str(agent_id), 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"
            
            async for event in generator:
                try:
                    if event.startswith("data: "):
                        data_str = event[6:].strip()
                        event_data = json.loads(data_str)
                        if event_data.get("type") == "token":
                            chunk = {
                                "id": completion_id,
                                "object": "chat.completion.chunk",
                                "created": int(time.time()),
                                "model": str(agent_id),
                                "choices": [{"index": 0, "delta": {"content": event_data.get("data", {}).get("content", "")}, "finish_reason": None}]
                            }
                            yield f"data: {json.dumps(chunk)}\n\n"
                        elif event_data.get("type") == "error":
                            chunk = {
                                "id": completion_id,
                                "object": "chat.completion.chunk",
                                "created": int(time.time()),
                                "model": str(agent_id),
                                "choices": [{"index": 0, "delta": {"content": f"\\n\\n[Error: {event_data.get('data', {}).get('message', 'unknown error')}]"}, "finish_reason": "stop"}]
                            }
                            yield f"data: {json.dumps(chunk)}\n\n"
                        elif event_data.get("type") == "done":
                            chunk = {
                                "id": completion_id,
                                "object": "chat.completion.chunk",
                                "created": int(time.time()),
                                "model": str(agent_id),
                                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
                            }
                            yield f"data: {json.dumps(chunk)}\n\n"
                except Exception as e:
                    logger.warning(
                        "Skipping unparseable SSE event: %s — raw event: %.200r",
                        e,
                        event,
                    )
                    
            yield "data: [DONE]\n\n"
            
        return StreamingResponse(openai_sse_generator(), media_type="text/event-stream")
        
    else:
        execution_service = AgentExecutionService(db)
        result = await execution_service.execute_agent_chat_with_file_refs(
            agent_id=agent_id,
            message=formatted_message,
            file_references=file_references,
            search_params=None,
            user_context=user_context,
            conversation_id=None,
            db=db,
        )
        
        response_text = result.get("response", "")
        if isinstance(response_text, list):
            # Complex response, extract text
            text_parts = []
            for item in response_text:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            response_text = " ".join(text_parts)
        elif not isinstance(response_text, str):
            response_text = str(response_text)
            
        usage_data = result.get("metadata", {}).get("usage", {})
        prompt_tokens = usage_data.get("prompt_tokens", 0) if isinstance(usage_data, dict) else 0
        completion_tokens = usage_data.get("completion_tokens", 0) if isinstance(usage_data, dict) else 0
        
        return OpenAIChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4()}",
            created=int(time.time()),
            model=str(agent_id),
            choices=[
                OpenAIChoice(
                    index=0,
                    message=OpenAIChoiceMessage(
                        role="assistant",
                        content=response_text
                    ),
                    finish_reason="stop"
                )
            ],
            usage=OpenAITokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens
            )
        )
