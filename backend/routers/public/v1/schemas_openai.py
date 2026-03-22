from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Dict, Any, Union

class OpenAIMessage(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]]]

class OpenAIChatCompletionRequest(BaseModel):
    model: str
    messages: List[OpenAIMessage]
    stream: Optional[bool] = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None

class OpenAIModel(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str = "mattin-ai"

class OpenAIModelListResponse(BaseModel):
    object: str = "list"
    data: List[OpenAIModel]

class OpenAIChoiceMessage(BaseModel):
    role: str = "assistant"
    content: str

class OpenAIChoice(BaseModel):
    index: int = 0
    message: OpenAIChoiceMessage
    finish_reason: str = "stop"

class OpenAITokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

class OpenAIChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[OpenAIChoice]
    usage: OpenAITokenUsage
