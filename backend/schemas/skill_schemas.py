from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Any
from datetime import datetime


# ==================== SKILL FILE SCHEMAS ====================

class SkillFileSchema(BaseModel):
    """Schema for a supporting file bundled with a Skill package."""
    file_id: int
    path: str
    media_type: Optional[str] = None
    content_text: Optional[str] = None
    checksum_sha256: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CreateSkillFileSchema(BaseModel):
    """Schema for creating a SkillFile record."""
    path: str
    media_type: Optional[str] = None
    content_text: Optional[str] = None
    # content_bytes is handled separately (binary upload)
    checksum_sha256: Optional[str] = None


# ==================== SKILL SCHEMAS ====================

class SkillListItemSchema(BaseModel):
    """Schema for skill list items"""
    skill_id: int
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = ""
    runtime: Optional[str] = None
    is_builtin: bool = False
    created_at: Optional[datetime] = None
    is_frozen: bool = False

    model_config = ConfigDict(from_attributes=True)


class SkillDetailSchema(BaseModel):
    """Schema for detailed skill information"""
    skill_id: int
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = ""
    content: str
    # dependencies removed in v2 (field still exists in DB for backward compatibility)
    allowed_tools: Optional[List[str]] = None
    runtime: Optional[str] = None
    bootstrap_script_path: Optional[str] = None
    runtime_options: Optional[Any] = None
    is_builtin: bool = False
    files: List[SkillFileSchema] = []
    created_at: Optional[datetime] = None
    is_frozen: bool = False

    model_config = ConfigDict(from_attributes=True)


class CreateUpdateSkillSchema(BaseModel):
    """Schema for creating or updating a skill"""
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = ""
    content: str
    # dependencies removed in v2 (silently dropped if present for backward compatibility)
    allowed_tools: Optional[List[str]] = None
    runtime: Optional[str] = None
    bootstrap_script_path: Optional[str] = None
    runtime_options: Optional[Any] = None
    files: Optional[List[CreateSkillFileSchema]] = None

