from pydantic import BaseModel
from typing import Any, Dict, Literal, Optional, Union, List


# ==================== STREAMING SCHEMAS ====================


class StreamEventSchema(BaseModel):
    """Schema for a single SSE stream event.

    Used for OpenAPI documentation — at runtime events are serialised
    manually as ``data: {json}\n\n`` strings.
    """

    type: Literal[
        "token",
        "tool_start",
        "tool_end",
        "thinking",
        "metadata",
        "error",
        "done",
    ]
    data: Dict[str, Any]


class TokenEventData(BaseModel):
    content: str


class ToolStartEventData(BaseModel):
    tool_name: str
    tool_input: Optional[str] = None


class ToolEndEventData(BaseModel):
    tool_name: str
    tool_output: Optional[str] = None


class ThinkingEventData(BaseModel):
    message: str


class MetadataEventData(BaseModel):
    conversation_id: Optional[int] = None
    agent_id: Optional[int] = None
    agent_name: Optional[str] = None
    has_memory: bool = False


class ErrorEventData(BaseModel):
    message: str


class FileInfo(BaseModel):
    file_id: str
    filename: str
    file_type: str


class DoneEventData(BaseModel):
    response: Union[str, Dict[str, Any], List[Any]]
    files: Optional[List[FileInfo]] = None
