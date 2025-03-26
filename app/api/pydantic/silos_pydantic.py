from api.pydantic.pydantic import AppPath
from pydantic import BaseModel
from typing import Optional

class SiloPath(AppPath):
    silo_id: int


class SiloSearch(BaseModel):
    query: str
    filter_metadata: Optional[dict] = {}

class SiloIndexBody(BaseModel):
    content: str
    metadata: Optional[dict] = {}