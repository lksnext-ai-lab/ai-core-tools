from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# ==================== MEDIA SCHEMAS ====================

class MediaResponse(BaseModel):
    media_id: int
    name: str
    source_type: str
    source_url: Optional[str]
    duration: Optional[float]
    language: Optional[str]
    status: str
    error_message: Optional[str]
    created_at: datetime
    processed_at: Optional[datetime]
    folder_id: Optional[int]

class MediaListResponse(BaseModel):
    media: List[MediaResponse]
    total: int

class MediaUploadResponse(BaseModel):
    message: str
    created_media: List[MediaResponse]
    failed_files: List[dict]

class MediaStatusResponse(BaseModel):
    media_id: int
    status: str
    error_message: Optional[str]
    processed_at: Optional[datetime]