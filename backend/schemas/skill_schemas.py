from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


# ==================== SKILL SCHEMAS ====================

class SkillListItemSchema(BaseModel):
    """Schema for skill list items"""
    skill_id: int
    name: str
    description: Optional[str] = ""
    created_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class SkillDetailSchema(BaseModel):
    """Schema for detailed skill information"""
    skill_id: int
    name: str
    description: Optional[str] = ""
    content: str  # Markdown instructions for the skill
    created_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class CreateUpdateSkillSchema(BaseModel):
    """Schema for creating or updating a skill"""
    name: str
    description: Optional[str] = ""
    content: str  # Markdown instructions for the skill
