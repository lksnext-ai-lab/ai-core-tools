from api.pydantic.pydantic import AppPath
from pydantic import BaseModel

class AgentPath(AppPath):
    agent_id: int

class ChatRequest(BaseModel):
    question: str

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

