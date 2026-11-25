"""Indexing settings shared by silos and repositories (stored on the silo, see tools.document_loaders)."""
from typing import Any

from pydantic import BaseModel, Field
from tools.document_loaders import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_PDF_LOADER,
    MAX_CHUNK_SIZE,
    MIN_CHUNK_SIZE,
    pdf_loader_catalog,
)

INDEXING_SETTING_FIELDS = ("chunk_size", "chunk_overlap", "pdf_loader", "pdf_loader_options")


class PdfLoaderOptionSchema(BaseModel):
    name: str
    type: str  # boolean | integer | number | string
    default: Any = None


class PdfLoaderSchema(BaseModel):
    key: str
    is_default: bool = False
    options: list[PdfLoaderOptionSchema] = []


class IndexingOptionsSchema(BaseModel):
    """What the forms can choose from, with limits and defaults."""
    pdf_loaders: list[PdfLoaderSchema]
    min_chunk_size: int = MIN_CHUNK_SIZE
    max_chunk_size: int = MAX_CHUNK_SIZE
    default_chunk_size: int = DEFAULT_CHUNK_SIZE
    default_chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
    default_pdf_loader: str = DEFAULT_PDF_LOADER

    @classmethod
    def build(cls) -> "IndexingOptionsSchema":
        return cls(pdf_loaders=[PdfLoaderSchema(**loader) for loader in pdf_loader_catalog()])


class IndexingSettingsInput(BaseModel):
    """Optional indexing fields of a create/update request.

    Omitted fields keep the stored value (defaults on creation). Changing ``pdf_loader``
    without ``pdf_loader_options`` resets the options to that loader's defaults. The
    overlap must be at most half of the chunk size. Existing chunks are not re-split:
    reindex to apply new settings to content already indexed.
    """
    chunk_size: int | None = Field(default=None, ge=MIN_CHUNK_SIZE, le=MAX_CHUNK_SIZE)
    chunk_overlap: int | None = Field(default=None, ge=0)
    pdf_loader: str | None = None
    pdf_loader_options: dict[str, Any] | None = None

    def indexing_settings(self) -> dict[str, Any]:
        """Only the indexing fields the caller actually sent."""
        return {name: getattr(self, name) for name in INDEXING_SETTING_FIELDS if name in self.model_fields_set}
