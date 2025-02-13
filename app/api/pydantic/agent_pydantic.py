from app.api.pydantic.pydantic import AppPath
from pydantic import BaseModel
class AgentPath(AppPath):
    agent_id: int

class ChatRequest(BaseModel):
    question: str

class OCRRequest(BaseModel):
    agent_id: str

