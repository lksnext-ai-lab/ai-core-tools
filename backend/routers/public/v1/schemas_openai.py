from pydantic import BaseModel, ConfigDict, Field
from typing import Annotated, List, Literal, Optional, Dict, Any, Union


class ContentPartText(BaseModel):
    type: Literal["text"]
    text: str


class ImageUrlDetail(BaseModel):
    url: str
    detail: Optional[Literal["auto", "low", "high"]] = "auto"


class ContentPartImageUrl(BaseModel):
    type: Literal["image_url"]
    image_url: ImageUrlDetail


class InputAudioData(BaseModel):
    data: str  # base64-encoded audio
    format: Literal["wav", "mp3"]


class ContentPartInputAudio(BaseModel):
    type: Literal["input_audio"]
    input_audio: InputAudioData


class FileData(BaseModel):
    file_data: Optional[str] = None   # base64-encoded file content
    file_id: Optional[str] = None     # reference to a previously uploaded file
    filename: Optional[str] = None


class ContentPartFile(BaseModel):
    type: Literal["file"]
    file: FileData


ChatCompletionContentPart = Annotated[
    Union[ContentPartText, ContentPartImageUrl, ContentPartInputAudio, ContentPartFile],
    Field(discriminator="type"),
]


class OpenAIMessage(BaseModel):
    role: str
    content: Union[str, List[ChatCompletionContentPart]]
    name: Optional[str] = None

class OpenAIChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str
    messages: List[OpenAIMessage]
    stream: Optional[bool] = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    max_completion_tokens: Optional[int] = None
    top_p: Optional[float] = None
    n: Optional[int] = None
    stop: Optional[Union[str, List[str]]] = None
    seed: Optional[int] = None
    user: Optional[str] = None
    safety_identifier: Optional[str] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    response_format: Optional[dict] = None
    stream_options: Optional[dict] = None
    logprobs: Optional[bool] = None
    top_logprobs: Optional[int] = None
    tools: Optional[list] = None
    tool_choice: Optional[Any] = None

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
    system_fingerprint: Optional[str] = None
    response_format: Optional[dict] = None
    choices: List[OpenAIChoice]
    usage: OpenAITokenUsage
