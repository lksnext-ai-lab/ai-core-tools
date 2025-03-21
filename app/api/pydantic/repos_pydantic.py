from pydantic import BaseModel
from typing import Optional, List

from api.pydantic.pydantic import AppPath

class RepoPath(AppPath):
    repo_id: int


class RepositorySchema(BaseModel):
    repository_id: int
    name: Optional[str]
    type: Optional[str]
    status: Optional[str]
    app_id: Optional[int]
    silo_id: int
    
    class Config:
        from_attributes = True 

class CreateRepositoryRequest(BaseModel):
    name: str
    description: Optional[str]
