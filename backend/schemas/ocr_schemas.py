from pydantic import BaseModel
from typing import Optional, Dict, Any

# ==================== OCR SCHEMAS ====================

class OCRResponseSchema(BaseModel):
    """Schema for OCR response"""
    result: dict
    agent_id: int
    metadata: dict
    extracted_text: Optional[str] = None
