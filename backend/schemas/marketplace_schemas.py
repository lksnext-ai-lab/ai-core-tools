from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, List
from datetime import datetime


# ==================== CONSTANTS ====================

MARKETPLACE_CATEGORIES = [
    "Productivity",
    "Research",
    "Writing",
    "Code",
    "Data Analysis",
    "Customer Support",
    "Education",
    "Other",
]


# ==================== PROFILE SCHEMAS ====================

class MarketplaceProfileSchema(BaseModel):
    """Response schema for marketplace profile data (visible to EDITOR+)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: int
    display_name: Optional[str] = None
    short_description: Optional[str] = None
    long_description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    icon_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    published_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MarketplaceProfileCreateUpdateSchema(BaseModel):
    """Request schema for creating/updating a marketplace profile (EDITOR+)."""
    display_name: Optional[str] = Field(None, max_length=255)
    short_description: Optional[str] = Field(None, max_length=200)
    long_description: Optional[str] = None  # Markdown
    category: Optional[str] = Field(None, max_length=50)
    tags: Optional[List[str]] = Field(None)
    icon_url: Optional[str] = Field(None, max_length=500)
    cover_image_url: Optional[str] = Field(None, max_length=500)

    @field_validator('tags')
    @classmethod
    def validate_tags(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is not None and len(v) > 5:
            raise ValueError('Maximum 5 tags allowed')
        return v

    @field_validator('category')
    @classmethod
    def validate_category(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in MARKETPLACE_CATEGORIES:
            raise ValueError(
                f'Invalid category. Must be one of: {", ".join(MARKETPLACE_CATEGORIES)}'
            )
        return v


# ==================== VISIBILITY SCHEMA ====================

class MarketplaceVisibilityUpdateSchema(BaseModel):
    """Request schema for updating an agent's marketplace visibility."""
    marketplace_visibility: str  # "unpublished", "private", "public"

    @field_validator('marketplace_visibility')
    @classmethod
    def validate_visibility(cls, v: str) -> str:
        valid_values = {"unpublished", "private", "public"}
        if v not in valid_values:
            raise ValueError(
                f'Invalid visibility. Must be one of: {", ".join(sorted(valid_values))}'
            )
        return v


# ==================== CONSUMER-FACING CATALOG SCHEMAS ====================

class MarketplaceAgentCardSchema(BaseModel):
    """
    Consumer-facing card for the marketplace catalog.
    Excludes all sensitive agent internals (system prompt, API keys, tool configs).
    """
    model_config = ConfigDict(from_attributes=True)

    agent_id: int
    display_name: str  # Resolved: profile.display_name or agent.name
    short_description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    icon_url: Optional[str] = None
    app_name: str  # Publisher app name
    app_id: int
    has_knowledge_base: bool = False  # True if agent has a silo (RAG)
    published_at: Optional[datetime] = None


class MarketplaceAgentDetailSchema(BaseModel):
    """
    Full marketplace agent detail page.
    Includes long description and cover image but still no sensitive data.
    """
    model_config = ConfigDict(from_attributes=True)

    agent_id: int
    display_name: str
    short_description: Optional[str] = None
    long_description: Optional[str] = None  # Markdown
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    icon_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    app_name: str
    app_id: int
    has_knowledge_base: bool = False
    has_memory: bool = False  # Whether conversations persist
    published_at: Optional[datetime] = None


class MarketplaceCatalogResponseSchema(BaseModel):
    """Paginated catalog response for marketplace listings."""
    agents: List[MarketplaceAgentCardSchema]
    total: int
    page: int
    page_size: int
    total_pages: int


# ==================== CONVERSATION SCHEMAS ====================

class MarketplaceConversationSchema(BaseModel):
    """Consumer's conversation entry in the marketplace context."""
    model_config = ConfigDict(from_attributes=True)

    conversation_id: int
    agent_id: int
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_message: Optional[str] = None
    message_count: int
    agent_display_name: str  # Resolved display name
    agent_icon_url: Optional[str] = None


class MarketplaceConversationListSchema(BaseModel):
    """List of consumer's marketplace conversations."""
    conversations: List[MarketplaceConversationSchema]
    total: int
