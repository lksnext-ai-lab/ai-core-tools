from api.pydantic.pydantic import AppPath
from pydantic import BaseModel, Field
from typing import Optional

class AgentPath(AppPath):
    agent_id: int

class ChatRequest(BaseModel):
    question: str = Field(
        description="The question or query to send to the agent",
        example="What is artificial intelligence?"
    )
    search_params: dict | None = Field(
        description="Optional search parameters for vector search filtering. Use this to filter documents by metadata fields.",
        example={
            "filter": {
                "source": "documentation",
                "category": "AI",
                "language": "en"
            }
        }
    )
    attachment: Optional[str] = Field(
        default=None,
        description="Optional base64 encoded file attachment",
        example="data:application/pdf;base64,JVBERi0xLjQKJcOkw7zDtsO..."
    )
    attachment_filename: Optional[str] = Field(
        default=None,
        description="Filename of the attached file",
        example="document.pdf"
    )
    attachment_mime_type: Optional[str] = Field(
        default=None,
        description="MIME type of the attached file",
        example="application/pdf"
    )
    file_references: Optional[list[str]] = Field(
        default=None,
        description="List of file references from previously uploaded files",
        example=["550e8400-e29b-41d4-a716-446655440000", "550e8400-e29b-41d4-a716-446655440001"]
    )

class OCRRequest(BaseModel):
    agent_id: str

class Control(BaseModel):
    temperature: float
    max_tokens: int
    top_p: float
    frequency_penalty: float
    presence_penalty: float
    stop_sequence: str

class Metadata(BaseModel):
    model_name: str
    timestamp: str

class AgentResponse(BaseModel):
    input: str
    generated_text: str
    control: Control
    metadata: Metadata

class OCRResponse(BaseModel):
    text: str
    status: str
    pages_processed: int

