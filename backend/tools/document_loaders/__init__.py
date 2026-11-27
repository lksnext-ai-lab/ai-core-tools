"""Per-silo indexing configuration and the registry of PDF loaders.

Every silo stores how its content is chunked (``chunk_size``/``chunk_overlap``,
applied to every file type and to raw content) and which PDF loader it uses
(``pdf_loader``) with that loader's own options (``pdf_loader_options``).

Adding a PDF loader:

1. implement it in this package as a function ``(file_path, chunk_size,
   chunk_overlap, options) -> list[Document]`` whose chunks never exceed
   ``chunk_size`` (the indexing pass re-splits anything longer);
2. describe its options with a Pydantic model (``extra="forbid"``; bool, int,
   float or str fields with defaults) — the frontend renders them from
   ``pdf_loader_catalog()``;
3. register a ``PdfLoaderSpec`` in ``_PDF_LOADERS``;
4. add its labels to the frontend locales (``silos.indexing.pdfLoaders.<key>``
   and ``silos.indexing.loaderOptions.<option>``).
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from langchain_core.documents import Document
from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError as PydanticValidationError
from tools.document_loaders.pymupdf4llm_loader import Pymupdf4llmLoader
from tools.document_loaders.pymupdf_loader import load_pymupdf_chunks
from utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_CHUNK_SIZE = 2000
DEFAULT_CHUNK_OVERLAP = 400
MIN_CHUNK_SIZE = 200
MAX_CHUNK_SIZE = 8000
DEFAULT_PDF_LOADER = "pymupdf"


class InvalidIndexingConfigError(ValueError):
    """A chunking value or PDF loader setting a caller tried to store is not valid."""


class NoOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Pymupdf4llmOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_prefix: bool = True
    remove_headers_footers: bool = True


@dataclass(frozen=True)
class PdfLoaderSpec:
    key: str
    options_model: type[BaseModel]
    load: Callable[[str, int, int, BaseModel], list[Document]]


def _load_pymupdf(file_path: str, chunk_size: int, chunk_overlap: int, _options: BaseModel) -> list[Document]:
    return load_pymupdf_chunks(file_path, chunk_size, chunk_overlap)


def _load_pymupdf4llm(file_path: str, chunk_size: int, chunk_overlap: int, options: BaseModel) -> list[Document]:
    return Pymupdf4llmLoader(file_path, chunk_size, chunk_overlap, **options.model_dump()).load_chunks()


_PDF_LOADERS: dict[str, PdfLoaderSpec] = {
    spec.key: spec
    for spec in (
        PdfLoaderSpec("pymupdf", NoOptions, _load_pymupdf),
        PdfLoaderSpec("pymupdf4llm", Pymupdf4llmOptions, _load_pymupdf4llm),
    )
}

_OPTION_TYPES = {bool: "boolean", int: "integer", float: "number", str: "string"}


def pdf_loader_catalog() -> list[dict[str, Any]]:
    """Loaders and their options for the silo/repository forms."""
    return [
        {
            "key": spec.key,
            "is_default": spec.key == DEFAULT_PDF_LOADER,
            "options": [
                {"name": name, "type": _OPTION_TYPES[info.annotation], "default": info.default}
                for name, info in spec.options_model.model_fields.items()
            ],
        }
        for spec in _PDF_LOADERS.values()
    ]


def validate_chunking(chunk_size: int, chunk_overlap: int) -> None:
    if not MIN_CHUNK_SIZE <= chunk_size <= MAX_CHUNK_SIZE:
        raise InvalidIndexingConfigError(
            f"chunk_size must be between {MIN_CHUNK_SIZE} and {MAX_CHUNK_SIZE}"
        )
    if not 0 <= chunk_overlap <= chunk_size // 2:
        raise InvalidIndexingConfigError("chunk_overlap must be between 0 and half of chunk_size")


def normalize_pdf_loader_options(pdf_loader: str, options: Mapping[str, Any] | None) -> dict[str, Any]:
    """Validate a loader key and its options; return the options with defaults filled in."""
    spec = _PDF_LOADERS.get(pdf_loader)
    if spec is None:
        raise InvalidIndexingConfigError(
            f"Unknown pdf_loader '{pdf_loader}'. Available: {', '.join(_PDF_LOADERS)}"
        )
    try:
        return spec.options_model.model_validate(dict(options or {})).model_dump()
    except PydanticValidationError as exc:
        fields = ", ".join(str(error["loc"][0]) for error in exc.errors() if error.get("loc"))
        raise InvalidIndexingConfigError(
            f"Invalid pdf_loader_options for '{pdf_loader}': {fields or 'invalid value'}"
        ) from exc


def _typed(value: Any, expected: type, default: Any) -> Any:
    """``value`` if it has the expected type (bool is not an int here), else ``default``."""
    if isinstance(value, bool) and expected is int:
        return default
    return value if isinstance(value, expected) else default


@dataclass(frozen=True)
class IndexingConfig:
    """How one silo chunks its content; ``IndexingConfig()`` is the default for new silos."""

    chunk_size: int = DEFAULT_CHUNK_SIZE
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
    pdf_loader: str = DEFAULT_PDF_LOADER
    pdf_loader_options: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def for_silo(cls, silo: Any) -> IndexingConfig:
        """Read a silo's stored settings; values that are no longer valid fall back to defaults.

        Stored settings were validated when written, so this only trips on a loader
        removed from the registry or a hand-edited row — indexing then keeps working
        with defaults instead of failing every document.
        """
        if silo is None:
            return cls()
        chunk_size = _typed(getattr(silo, "chunk_size", None), int, DEFAULT_CHUNK_SIZE)
        chunk_overlap = _typed(getattr(silo, "chunk_overlap", None), int, DEFAULT_CHUNK_OVERLAP)
        try:
            validate_chunking(chunk_size, chunk_overlap)
        except InvalidIndexingConfigError:
            logger.warning("Silo %s has invalid chunking settings; using defaults", getattr(silo, "silo_id", None))
            chunk_size, chunk_overlap = DEFAULT_CHUNK_SIZE, DEFAULT_CHUNK_OVERLAP

        pdf_loader = _typed(getattr(silo, "pdf_loader", None), str, DEFAULT_PDF_LOADER) or DEFAULT_PDF_LOADER
        try:
            options = normalize_pdf_loader_options(
                pdf_loader, _typed(getattr(silo, "pdf_loader_options", None), Mapping, None)
            )
        except InvalidIndexingConfigError:
            logger.warning(
                "Silo %s has an invalid PDF loader setting (%s); using %s",
                getattr(silo, "silo_id", None), pdf_loader, DEFAULT_PDF_LOADER,
            )
            pdf_loader, options = DEFAULT_PDF_LOADER, normalize_pdf_loader_options(DEFAULT_PDF_LOADER, None)
        return cls(chunk_size, chunk_overlap, pdf_loader, options)

    def load_pdf_chunks(self, file_path: str) -> list[Document]:
        spec = _PDF_LOADERS[self.pdf_loader]
        options = spec.options_model.model_validate(dict(self.pdf_loader_options))
        return spec.load(file_path, self.chunk_size, self.chunk_overlap, options)
