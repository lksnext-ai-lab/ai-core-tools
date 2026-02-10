"""Import schemas for conflict resolution and import operations."""

from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum


# ==================== ENUMS ====================


class ConflictMode(str, Enum):
    """Import conflict resolution modes"""

    FAIL = "fail"  # Return 409 if exists
    RENAME = "rename"  # Auto-rename to "{name} (imported {date})"
    OVERRIDE = "override"  # Replace existing configuration


class ComponentType(str, Enum):
    """Exportable component types"""

    AI_SERVICE = "ai_service"
    EMBEDDING_SERVICE = "embedding_service"
    OUTPUT_PARSER = "output_parser"
    MCP_CONFIG = "mcp_config"
    SILO = "silo"
    REPOSITORY = "repository"
    AGENT = "agent"
    APP = "app"


# ==================== REQUEST/RESPONSE SCHEMAS ====================


class ImportRequestSchema(BaseModel):
    """Import request parameters"""

    conflict_mode: ConflictMode = ConflictMode.FAIL
    new_name: Optional[str] = None  # For rename mode
    app_id: Optional[int] = None  # Target app for component imports


class ValidateImportResponseSchema(BaseModel):
    """Import validation response"""

    component_type: ComponentType
    component_name: str
    has_conflict: bool  # True if component with same name exists
    warnings: List[str] = []
    missing_dependencies: List[str] = []  # e.g., "AI Service: GPT-4 not found"
    requires_embedding_service_selection: bool = False  # For silos without bundled service
    requires_ai_service_selection: bool = False  # For agents without bundled AI service


class ImportSummarySchema(BaseModel):
    """Import operation summary"""

    component_type: ComponentType
    component_id: Optional[int] = None
    component_name: str
    mode: Optional[ConflictMode] = None
    created: bool = False
    warnings: List[str] = []
    next_steps: List[str] = []


class ImportResponseSchema(BaseModel):
    """Import operation response"""

    success: bool
    message: str
    summary: Optional[ImportSummarySchema] = None
