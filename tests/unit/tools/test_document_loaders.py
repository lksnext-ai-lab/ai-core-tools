"""Registry of PDF loaders and per-silo indexing settings (tools.document_loaders)."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from langchain_core.documents import Document
from tools.document_loaders import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_PDF_LOADER,
    IndexingConfig,
    InvalidIndexingConfigError,
    normalize_pdf_loader_options,
    pdf_loader_catalog,
    validate_chunking,
)


def test_defaults():
    assert (DEFAULT_CHUNK_SIZE, DEFAULT_CHUNK_OVERLAP, DEFAULT_PDF_LOADER) == (2000, 400, "pymupdf")
    assert IndexingConfig() == IndexingConfig(2000, 400, "pymupdf", {})


def test_catalog_lists_loaders_with_typed_options():
    catalog = {loader["key"]: loader for loader in pdf_loader_catalog()}

    assert set(catalog) == {"pymupdf", "pymupdf4llm"}
    assert catalog["pymupdf"] == {"key": "pymupdf", "is_default": True, "options": []}
    assert catalog["pymupdf4llm"]["options"] == [
        {"name": "section_prefix", "type": "boolean", "default": True},
        {"name": "remove_headers_footers", "type": "boolean", "default": True},
    ]


@pytest.mark.parametrize(("size", "overlap"), [(199, 0), (8001, 0), (1000, 501), (1000, -1)])
def test_invalid_chunking_is_rejected(size, overlap):
    with pytest.raises(InvalidIndexingConfigError):
        validate_chunking(size, overlap)


@pytest.mark.parametrize(("size", "overlap"), [(200, 0), (8000, 4000), (1000, 500)])
def test_chunking_limits_are_inclusive(size, overlap):
    validate_chunking(size, overlap)


def test_options_are_completed_with_defaults():
    assert normalize_pdf_loader_options("pymupdf4llm", {"section_prefix": False}) == {
        "section_prefix": False, "remove_headers_footers": True,
    }
    assert normalize_pdf_loader_options("pymupdf", None) == {}


@pytest.mark.parametrize(
    ("loader", "options"),
    [("nope", None), ("pymupdf", {"section_prefix": True}), ("pymupdf4llm", {"section_prefix": "maybe"})],
)
def test_unknown_loader_or_option_is_rejected(loader, options):
    with pytest.raises(InvalidIndexingConfigError):
        normalize_pdf_loader_options(loader, options)


def test_for_silo_reads_the_stored_settings():
    silo = SimpleNamespace(
        silo_id=1, chunk_size=1500, chunk_overlap=300, pdf_loader="pymupdf4llm",
        pdf_loader_options={"section_prefix": False},
    )

    assert IndexingConfig.for_silo(silo) == IndexingConfig(
        1500, 300, "pymupdf4llm", {"section_prefix": False, "remove_headers_footers": True},
    )


def test_for_silo_falls_back_to_defaults_on_invalid_stored_values():
    silo = SimpleNamespace(
        silo_id=1, chunk_size=10, chunk_overlap=300, pdf_loader="removed-loader", pdf_loader_options={"x": 1},
    )

    assert IndexingConfig.for_silo(silo) == IndexingConfig()
    assert IndexingConfig.for_silo(None) == IndexingConfig()


def test_load_pdf_chunks_dispatches_to_the_configured_loader():
    page = Document(page_content="Plain page text. " * 300, metadata={"page": 0})
    with (
        patch("langchain_community.document_loaders.PyMuPDFLoader") as fast,
        patch("pymupdf4llm.to_markdown", return_value=[{"text": "# Title\n\nStructured text."}]) as structured,
    ):
        fast.return_value.load.return_value = [page]
        fast_chunks = IndexingConfig(1000, 100).load_pdf_chunks("a.pdf")
        structured_chunks = IndexingConfig(1000, 100, "pymupdf4llm").load_pdf_chunks("a.pdf")

    assert len(fast_chunks) > 1 and all(len(c.page_content) <= 1000 for c in fast_chunks)
    assert structured.call_count == 1
    assert structured_chunks[0].metadata["section"] == "Title"
