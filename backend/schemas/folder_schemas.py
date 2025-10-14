from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


class FolderListItemSchema(BaseModel):
    """Schema for folder list items"""
    folder_id: int
    name: str
    parent_folder_id: Optional[int] = None
    create_date: Optional[datetime] = None
    status: Optional[str] = None
    subfolder_count: int = 0
    resource_count: int = 0
    
    model_config = ConfigDict(from_attributes=True)


class FolderDetailSchema(BaseModel):
    """Schema for detailed folder information"""
    folder_id: int
    name: str
    parent_folder_id: Optional[int] = None
    create_date: Optional[datetime] = None
    status: Optional[str] = None
    repository_id: int
    subfolders: List['FolderDetailSchema'] = []
    resources: List[Dict[str, Any]] = []
    folder_path: str = ""
    
    model_config = ConfigDict(from_attributes=True)


class FolderTreeSchema(BaseModel):
    """Schema for recursive folder tree structure"""
    folder_id: int
    name: str
    parent_folder_id: Optional[int] = None
    create_date: Optional[datetime] = None
    status: Optional[str] = None
    repository_id: int
    subfolders: List['FolderTreeSchema'] = []
    resource_count: int = 0
    folder_path: str = ""
    
    model_config = ConfigDict(from_attributes=True)


class CreateFolderSchema(BaseModel):
    """Schema for creating a new folder"""
    name: str
    parent_folder_id: Optional[int] = None


class UpdateFolderSchema(BaseModel):
    """Schema for updating a folder"""
    name: str


class MoveFolderSchema(BaseModel):
    """Schema for moving a folder"""
    new_parent_folder_id: Optional[int] = None


class FoldersResponseSchema(BaseModel):
    """Schema for folders list response"""
    folders: List[FolderListItemSchema]
    total_count: int


class FolderResponseSchema(BaseModel):
    """Schema for single folder response"""
    folder: FolderDetailSchema


class FolderTreeResponseSchema(BaseModel):
    """Schema for folder tree response"""
    folders: List[FolderTreeSchema]


# Update forward references
FolderDetailSchema.model_rebuild()
FolderTreeSchema.model_rebuild()
