from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# ==================== MEDIA SCHEMAS ====================

class MediaResponse(BaseModel):
    media_id: int
    name: str
    source_type: str
    source_url: Optional[str] = None
    duration: Optional[float] = None  # Duration in seconds for audio/video
    language: Optional[str] = None  # Detected language for text media
    status: str
    error_message: Optional[str] = None
    create_date: datetime
    processed_at: Optional[datetime] = None
    folder_id: Optional[int] = None

class MediaListResponse(BaseModel):
    media: List[MediaResponse]
    total: int

class MediaUploadResponse(BaseModel):
    message: str
    created_media: List[MediaResponse]
    failed_files: List[dict]

    class Config:
        from_attributes = True

class MediaStatusResponse(BaseModel):
    media_id: int
    status: str
    error_message: Optional[str] = None
    processed_at: Optional[datetime] = None