from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Dict, List, Optional
from datetime import datetime


# ==================== SKILL SCHEMAS ====================

class SkillFileInfoSchema(BaseModel):
    """Metadata of one skill package file. Never carries file content."""
    path: str
    media_type: Optional[str] = None
    size_bytes: int = 0
    checksum_sha256: Optional[str] = None
    is_text: bool = True

    model_config = ConfigDict(from_attributes=True)


class SkillListItemSchema(BaseModel):
    """Schema for skill list items"""
    skill_id: int
    name: str
    description: Optional[str] = ""
    created_at: Optional[datetime] = None
    is_frozen: bool = False
    display_name: Optional[str] = None
    is_system: bool = False
    is_enabled: bool = True
    source: str = 'admin'
    file_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class SkillDetailSchema(BaseModel):
    """Schema for detailed skill information"""
    skill_id: int
    name: str
    description: Optional[str] = ""
    content: str  # Markdown instructions for the skill
    created_at: Optional[datetime] = None
    is_frozen: bool = False
    display_name: Optional[str] = None
    is_system: bool = False
    is_enabled: bool = True
    source: str = 'admin'
    frontmatter: Dict[str, Any] = Field(default_factory=dict)
    allowed_tools: List[str] = Field(default_factory=list)  # metadata only, never enforced
    runtime: Optional[str] = None
    bootstrap_script_path: Optional[str] = None
    runtime_options: Dict[str, Any] = Field(default_factory=dict)
    files: List[SkillFileInfoSchema] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


# utils/skill_frontmatter.py caps only the YAML frontmatter block (64 KiB); the markdown body has no cap of its
# own there (import-service ``_check_lengths`` only bounds display_name/runtime/bootstrap/description). 2,000,000
# chars (~2 MB as UTF-8 for mostly-ASCII markdown) is generous for a skill's instructions while staying an order
# of magnitude below SKILL_IMPORT_MAX_FILE_BYTES (10 MB default), so a CRUD-created skill can never produce a
# SKILL.md body larger than what the import path already accepts for an ordinary package file.
MAX_SKILL_CONTENT_LENGTH = 2_000_000


class CreateUpdateSkillSchema(BaseModel):
    """Schema for creating or updating a skill.

    Update semantics for the optional package fields (based on ``model_fields_set``):
    a field that is omitted preserves the stored value; an explicit ``null`` clears
    display_name, runtime, bootstrap_script_path, allowed_tools and runtime_options
    (blank strings for the three string fields also clear them). ``is_enabled`` is NOT NULL,
    so an explicit ``null`` is treated as omitted. ``when_to_use`` (stored in the frontmatter)
    is only written when non-null; a blank string removes it.
    """
    name: str
    description: Optional[str] = Field(default="", max_length=1024)
    content: str = Field(..., max_length=MAX_SKILL_CONTENT_LENGTH)  # Markdown instructions for the skill
    display_name: Optional[str] = Field(default=None, max_length=200)
    when_to_use: Optional[str] = None
    allowed_tools: Optional[List[str]] = None
    runtime: Optional[str] = Field(default=None, max_length=50)
    bootstrap_script_path: Optional[str] = Field(default=None, max_length=500)
    runtime_options: Optional[Dict[str, Any]] = None
    is_enabled: Optional[bool] = None


class SkillEnabledUpdateSchema(BaseModel):
    """Request body for the ``PATCH .../enabled`` toggle routes (app-scoped and system-scoped)."""
    is_enabled: bool
