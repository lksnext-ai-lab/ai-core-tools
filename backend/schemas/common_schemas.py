from pydantic import BaseModel, ConfigDict
from typing import Optional

# ==================== COMMON RESPONSE SCHEMAS ====================

class MessageResponseSchema(BaseModel):
    """Schema for simple message responses"""
    message: str
    success: bool = True


class ErrorResponseSchema(BaseModel):
    """Schema for error responses"""
    error: str
    detail: Optional[str] = None
    success: bool = False


class SuccessResponseSchema(BaseModel):
    """Schema for success responses"""
    success: bool = True
    message: str


class PaginationSchema(BaseModel):
    """Schema for pagination metadata"""
    page: int
    per_page: int
    total: int
    pages: int
    has_prev: bool
    has_next: bool


class PaginatedResponseSchema(BaseModel):
    """Schema for paginated responses"""
    items: list
    pagination: PaginationSchema
    
    model_config = ConfigDict(from_attributes=True)
