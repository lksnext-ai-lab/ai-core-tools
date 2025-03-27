from pydantic import BaseModel, Field
from typing import Optional, List
from flask_openapi3 import FileStorage
from pydantic import RootModel

from api.pydantic.repos_pydantic import RepoPath

class ResourcePath(RepoPath):
    resource_id: int


class ResourceSchema(BaseModel):
    resource_id: int
    name: str
    uri: str
    type: Optional[str]
    status: Optional[str]
    repository_id: int
    
    class Config:
        from_attributes = True 

class CreateResourceForm(BaseModel):
    name: str = Field(..., description="Resource name")
    type: Optional[str] = Field(None, description="Resource type")
    status: Optional[str] = Field(None, description="Resource status")
    file: FileStorage = Field(..., description="Uploaded file")

class ResourceListResponse(RootModel):
    root: List[ResourceSchema]

class ResourceResponse(BaseModel):
    message: str
    resource: ResourceSchema

class MessageResponse(BaseModel):
    message: str