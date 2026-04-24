from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from schemas.embedding_service_schemas import EmbeddingServiceOptionSchema


class SiloListItemSchema(BaseModel):
    """Schema for silo list items"""
    silo_id: int
    name: str
    description: Optional[str] = None
    type: Optional[str] = None
    created_at: Optional[datetime] = None
    docs_count: int
    vector_db_type: Optional[str] = None
    is_frozen: bool = False

    model_config = ConfigDict(from_attributes=True)


class SiloDetailSchema(BaseModel):
    """Schema for detailed silo information"""
    silo_id: int
    name: str
    description: Optional[str] = None
    type: Optional[str] = None
    created_at: Optional[datetime] = None
    docs_count: int
    vector_db_type: Optional[str] = None
    # Current values for editing
    metadata_definition_id: Optional[int] = None
    embedding_service_id: Optional[int] = None
    # Form data
    output_parsers: List[Dict[str, Any]]
    embedding_services: List[EmbeddingServiceOptionSchema]
    vector_db_options: List[Dict[str, Any]] = []
    # Metadata definition fields for playground
    metadata_fields: Optional[List[Dict[str, Any]]] = None
    is_frozen: bool = False

    model_config = ConfigDict(from_attributes=True)


class CreateSiloSchema(BaseModel):
    """Schema for creating a new silo (vector_db_type is settable on creation only)"""
    name: str
    description: Optional[str] = None
    type: Optional[str] = None
    output_parser_id: Optional[int] = None
    embedding_service_id: Optional[int] = None
    vector_db_type: Optional[str] = None


class UpdateSiloSchema(BaseModel):
    """Schema for updating an existing silo (vector_db_type and embedding_service_id are immutable after creation)"""
    name: str
    description: Optional[str] = None
    type: Optional[str] = None
    output_parser_id: Optional[int] = None


# Kept for backward compatibility with the public API router
CreateUpdateSiloSchema = CreateSiloSchema


class SiloSearchSchema(BaseModel):
    """Schema for searching within a silo.

    `limit` — max results. Defaults to DEFAULT_SEARCH_LIMIT (100), capped at MAX_SEARCH_LIMIT (200).
    `search_type` — one of "similarity" (default), "similarity_score_threshold", "mmr".
    `score_threshold` — float 0-1, only meaningful when search_type="similarity_score_threshold".
    `fetch_k` — candidate pool size for MMR, only meaningful when search_type="mmr".
    `lambda_mult` — diversity factor 0-1 for MMR (1=max relevance, 0=max diversity). Default 0.5.
    """
    query: str
    limit: Optional[int] = None
    filter_metadata: Optional[Dict[str, Any]] = None
    search_type: str = "similarity"
    score_threshold: Optional[float] = None
    fetch_k: Optional[int] = None
    lambda_mult: Optional[float] = None

    @field_validator("search_type")
    @classmethod
    def validate_search_type(cls, v: str) -> str:
        allowed = {"similarity", "similarity_score_threshold", "mmr"}
        if v not in allowed:
            raise ValueError(f"search_type must be one of {sorted(allowed)}, got '{v}'")
        return v

    @model_validator(mode="after")
    def validate_param_consistency(self) -> "SiloSearchSchema":
        if self.score_threshold is not None and self.search_type != "similarity_score_threshold":
            raise ValueError(
                "score_threshold is only valid when search_type='similarity_score_threshold'"
            )
        if (self.fetch_k is not None or self.lambda_mult is not None) and self.search_type != "mmr":
            raise ValueError(
                "fetch_k and lambda_mult are only valid when search_type='mmr'"
            )
        return self
