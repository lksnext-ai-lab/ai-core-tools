from api.pydantic.pydantic import AppPath
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

class SiloPath(AppPath):
    silo_id: int

class SiloSearch(BaseModel):
    query: str
    filter_metadata: Optional[dict] = {}

class SingleDocumentIndex(BaseModel):
    content: str
    metadata: Optional[dict] = {}

class MultipleDocumentIndex(BaseModel):
    documents: List[SingleDocumentIndex]

class DocResponse(BaseModel):
    page_content: str
    metadata: Dict[str, Any]

class DocsResponse(BaseModel):
    docs: List[DocResponse]

class CountResponse(BaseModel):
    count: int

class MessageResponse(BaseModel):
    message: str

class FileDocumentIndex(BaseModel):
    metadata: Optional[dict] = {}