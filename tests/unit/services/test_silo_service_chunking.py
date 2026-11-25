"""Unit tests for chunking in SiloService: extract_documents_from_file (FR-10) and index_single_content (FR-11).

All external dependencies are mocked — no DB, filesystem, or vector store access.
"""
import itertools
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document
from services.silo_service import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    SiloService,
)
from tools.document_loaders import IndexingConfig
from tools.document_loaders.pymupdf4llm_loader import Pymupdf4llmLoader


def _make_silo(silo_id: int = 7) -> MagicMock:
    silo = MagicMock()
    silo.silo_id = silo_id
    silo.embedding_service_id = 1
    silo.embedding_service = MagicMock(name="mock-embedding-service", end_of_service_at=None)
    return silo


def _make_vector_store() -> MagicMock:
    vs = MagicMock()
    vs.index_documents.return_value = None
    return vs


def _long_text(n_chars: int = CHUNK_SIZE * 3) -> str:
    """Return a realistic multi-paragraph text longer than CHUNK_SIZE."""
    paragraph = (
        "The quick brown fox jumped over the lazy dog near the riverbank. "
        "Scientists discovered a new species in the Amazon rainforest yesterday. "
    )
    full = "\n\n".join([paragraph.strip()] * (n_chars // len(paragraph) + 2))
    return full[:n_chars]


class TestDomainContentChunking:
    """FR-11: Long web-page text must be chunked; metadata propagated to every chunk."""

    def _call_index_single(self, content: str, metadata: dict, silo_id: int = 7):
        silo = _make_silo(silo_id)
        vs = _make_vector_store()
        db = MagicMock()

        with (
            patch("services.silo_service.SiloRepository.get_by_id", return_value=silo),
            patch("services.silo_service.SiloRepository.get_embedding_service_by_id", return_value=silo.embedding_service),
            patch("services.silo_service._get_vector_store", return_value=vs),
        ):
            SiloService.index_single_content(silo_id, content, metadata, db)

        assert vs.index_documents.called, "index_documents was never called"
        call_args = vs.index_documents.call_args
        indexed_docs: list[Document] = call_args[0][1]
        return indexed_docs

    def test_long_content_produces_multiple_chunks(self):
        """A text longer than CHUNK_SIZE must be split into >1 chunk."""
        content = _long_text(CHUNK_SIZE * 3)
        metadata = {"url": "https://example.com/page", "domain_id": 42}

        docs = self._call_index_single(content, metadata, silo_id=7)

        assert len(docs) > 1, (
            f"Expected >1 chunk for {len(content)}-char text with CHUNK_SIZE={CHUNK_SIZE}, "
            f"got {len(docs)}"
        )

    def test_all_chunks_carry_url_metadata(self):
        """Every chunk produced from domain content must include the 'url' key."""
        content = _long_text(CHUNK_SIZE * 3)
        metadata = {"url": "https://example.com/page", "domain_id": 42}

        docs = self._call_index_single(content, metadata, silo_id=7)

        for i, doc in enumerate(docs):
            assert "url" in doc.metadata, f"Chunk {i} missing 'url' in metadata"
            assert doc.metadata["url"] == "https://example.com/page", (
                f"Chunk {i} has wrong 'url': {doc.metadata['url']}"
            )

    def test_all_chunks_carry_domain_id_metadata(self):
        """Every chunk produced from domain content must include the 'domain_id' key."""
        content = _long_text(CHUNK_SIZE * 3)
        metadata = {"url": "https://example.com/page", "domain_id": 42}

        docs = self._call_index_single(content, metadata, silo_id=7)

        for i, doc in enumerate(docs):
            assert "domain_id" in doc.metadata, f"Chunk {i} missing 'domain_id'"
            assert doc.metadata["domain_id"] == 42, (
                f"Chunk {i} has wrong 'domain_id': {doc.metadata['domain_id']}"
            )

    def test_all_chunks_carry_silo_id_metadata(self):
        """Every chunk produced must include 'silo_id' matching the target silo."""
        content = _long_text(CHUNK_SIZE * 3)
        metadata = {"url": "https://example.com/page", "domain_id": 42}

        docs = self._call_index_single(content, metadata, silo_id=7)

        for i, doc in enumerate(docs):
            assert "silo_id" in doc.metadata, f"Chunk {i} missing 'silo_id'"
            assert doc.metadata["silo_id"] == 7, (
                f"Chunk {i} has wrong 'silo_id': {doc.metadata['silo_id']}"
            )

    def test_chunk_content_is_non_empty(self):
        """No chunk should be empty after splitting."""
        content = _long_text(CHUNK_SIZE * 3)
        metadata = {"url": "https://example.com/page", "domain_id": 42}

        docs = self._call_index_single(content, metadata, silo_id=7)

        for i, doc in enumerate(docs):
            assert doc.page_content.strip(), f"Chunk {i} has empty page_content"

    def test_short_content_produces_single_chunk(self):
        """Text shorter than CHUNK_SIZE must produce exactly 1 chunk with intact metadata."""
        short_content = "This is a short web-page snippet that fits in one chunk."
        assert len(short_content) < CHUNK_SIZE
        metadata = {"url": "https://example.com/short", "domain_id": 99}

        docs = self._call_index_single(short_content, metadata, silo_id=5)

        assert len(docs) == 1
        assert docs[0].metadata["url"] == "https://example.com/short"
        assert docs[0].metadata["domain_id"] == 99
        assert docs[0].metadata["silo_id"] == 5
        assert docs[0].page_content == short_content

    def test_chunk_at_exact_size_boundary_is_not_resplit(self):
        """Idempotency invariant: a chunk of exactly CHUNK_SIZE chars produces 1 chunk.

        The file-upload path re-feeds already-split chunks (each <= CHUNK_SIZE)
        through this splitter; this test pins the boundary so a future change to
        the constants or the splitter class cannot silently break that invariant.
        """
        content_at_limit = "A" * CHUNK_SIZE
        metadata = {"url": "https://example.com/boundary", "domain_id": 1}

        docs = self._call_index_single(content_at_limit, metadata, silo_id=7)

        assert len(docs) == 1, (
            f"A chunk of exactly CHUNK_SIZE={CHUNK_SIZE} chars must not be re-split, "
            f"got {len(docs)} chunks"
        )
        assert docs[0].page_content == content_at_limit

    def test_caller_metadata_cannot_override_silo_id(self):
        """A 'silo_id' key inside caller metadata must not override the silo_id parameter."""
        metadata = {"url": "https://example.com/x", "silo_id": 999}

        docs = self._call_index_single("Some short content.", metadata, silo_id=7)

        assert docs[0].metadata["silo_id"] == 7

    def test_index_multiple_content_chunks_each_document(self):
        """index_multiple_content with two long documents must produce >2 total chunks."""
        silo = _make_silo(3)
        vs = _make_vector_store()
        db = MagicMock()

        long_text = _long_text(CHUNK_SIZE * 2)
        documents = [
            {"content": long_text, "metadata": {"url": "https://example.com/a", "domain_id": 1}},
            {"content": long_text, "metadata": {"url": "https://example.com/b", "domain_id": 1}},
        ]

        with (
            patch("services.silo_service.SiloRepository.get_by_id", return_value=silo),
            patch("services.silo_service.SiloRepository.get_embedding_service_by_id", return_value=silo.embedding_service),
            patch("services.silo_service._get_vector_store", return_value=vs),
        ):
            SiloService.index_multiple_content(3, documents, db)

        indexed_docs = vs.index_documents.call_args[0][1]
        assert len(indexed_docs) > 2, (
            f"Expected >2 total chunks from 2 long documents, got {len(indexed_docs)}"
        )

    def test_metadata_isolation_between_documents(self):
        """Chunks from document A must not carry the URL of document B."""
        silo = _make_silo(3)
        vs = _make_vector_store()
        db = MagicMock()

        long_text = _long_text(CHUNK_SIZE * 2)
        documents = [
            {"content": long_text, "metadata": {"url": "https://example.com/a", "domain_id": 10}},
            {"content": long_text, "metadata": {"url": "https://example.com/b", "domain_id": 20}},
        ]

        with (
            patch("services.silo_service.SiloRepository.get_by_id", return_value=silo),
            patch("services.silo_service.SiloRepository.get_embedding_service_by_id", return_value=silo.embedding_service),
            patch("services.silo_service._get_vector_store", return_value=vs),
        ):
            SiloService.index_multiple_content(3, documents, db)

        indexed_docs = vs.index_documents.call_args[0][1]
        urls = {doc.metadata["url"] for doc in indexed_docs}
        assert urls == {"https://example.com/a", "https://example.com/b"}
        for doc in indexed_docs:
            if doc.metadata["url"] == "https://example.com/a":
                assert doc.metadata["domain_id"] == 10
            else:
                assert doc.metadata["domain_id"] == 20


def _sentences(label: str, count: int) -> str:
    """Distinct sentences, so every chunk occurs once in the source text."""
    return " ".join(f"{label} sentence number {i} describes the pump station." for i in range(count))


# A silo using the pymupdf4llm loader with 1000/200 chunks.
_STRUCTURED = IndexingConfig(chunk_size=1000, chunk_overlap=200, pdf_loader="pymupdf4llm")


class TestPymupdf4llmLoaderChunking:
    """With the pymupdf4llm loader, PDFs are chunked by section, size and overlap."""

    last_to_markdown_kwargs: dict | None = None

    @classmethod
    def _extract(cls, pages: list[str], base_metadata: dict | None = None, indexing: IndexingConfig = _STRUCTURED):
        with patch("pymupdf4llm.to_markdown", return_value=[{"text": text} for text in pages]) as to_markdown:
            docs = SiloService.extract_documents_from_file(
                file_path="fake.pdf", file_extension=".pdf", base_metadata=base_metadata, indexing=indexing,
            )
        cls.last_to_markdown_kwargs = to_markdown.call_args.kwargs
        return docs

    def test_loader_implements_langchain_base_loader(self):
        assert issubclass(Pymupdf4llmLoader, BaseLoader)

    def test_chunks_respect_size_and_overlap(self):
        docs = self._extract([f"# Scope\n\n{_sentences('Scope', 80)}"])

        assert len(docs) > 2
        assert all(len(doc.page_content) <= _STRUCTURED.chunk_size for doc in docs)
        for previous, current in itertools.pairwise(docs):
            tail = previous.page_content[-40:]
            assert tail in current.page_content, "consecutive chunks must overlap"

    def test_section_path_follows_heading_hierarchy_across_pages(self):
        docs = self._extract([
            f"# 1 Plan\n\n## 1.1 Phases\n\n{_sentences('Phase', 30)}",
            f"{_sentences('Continued', 30)}\n\n# 2 Team\n\n{_sentences('Team', 5)}",
        ])

        sections = [doc.metadata["section"] for doc in docs]
        assert sections[0] == "1 Plan > 1.1 Phases"
        assert sections[-1] == "2 Team"
        continued = [doc for doc in docs if "Continued sentence number 29" in doc.page_content]
        assert continued and continued[0].metadata["section"] == "1 Plan > 1.1 Phases"
        assert continued[0].metadata["page"] == 2
        assert docs[0].page_content.startswith("[1 Plan > 1.1 Phases]")

    def test_page_and_base_metadata(self):
        docs = self._extract(
            [_sentences("First", 30), _sentences("Second", 30)],
            base_metadata={"resource_id": 42},
        )

        # page = page where the chunk starts (1-based once extracted)
        pages = [doc.metadata["page"] for doc in docs]
        assert pages == sorted(pages) and pages[0] == 1 and pages[-1] == 2
        second_only = [doc for doc in docs if doc.page_content.startswith("Second")]
        assert second_only and all(doc.metadata["page"] == 2 for doc in second_only)
        assert all(doc.metadata["total_pages"] == 2 for doc in docs)
        assert all(doc.metadata["resource_id"] == 42 for doc in docs)
        assert all("section" not in doc.metadata for doc in docs), "text before any heading has no section"

    def test_inline_markup_is_removed_but_identifiers_survive(self):
        docs = self._extract([(
            "## **Results** _overview_\n\n"
            "**_Abstract_** —the <u>token</u> spend<br>grows. <!-- Start of picture text -->"
            " Call __init__ from my_module_name to load the pump data, then report it."
        )])

        assert docs[0].metadata["section"] == "Results overview"
        content = docs[0].page_content
        for noise in ("**", "<u>", "<br>", "<!--", "_Abstract_"):
            assert noise not in content
        assert "Abstract —the token spend grows." in content
        assert "__init__" in content and "my_module_name" in content

    def test_numeric_table_rows_survive_cleaning(self):
        docs = self._extract([(
            "# Budget\n\nYearly budget of the water service per district:\n\n"
            "|Year|Cost|\n|---|---|\n|2024|35|\n|2025|12.5|\n||||"
        )])

        content = docs[0].page_content
        assert "|2024|35|" in content and "|2025|12.5|" in content
        assert "||||" not in content

    def test_second_indexing_pass_does_not_resplit(self):
        docs = self._extract([f"# Scope\n\n{_sentences('Scope', 80)}"])

        indexed = SiloService._create_documents_for_indexing(
            4, [{"content": doc.page_content, "metadata": doc.metadata} for doc in docs], _STRUCTURED,
        )

        assert [doc.page_content for doc in indexed] == [doc.page_content for doc in docs]
        assert all(doc.metadata["silo_id"] == 4 for doc in indexed)

    def test_long_heading_path_prefix_is_capped(self):
        long_title = "Very long heading " * 30
        docs = self._extract([f"# {long_title}\n\n{_sentences('Body', 40)}"])

        prefix = docs[0].page_content.split("\n", 1)[0]
        assert prefix.startswith("[…") and len(prefix) <= 200
        assert all(len(doc.page_content) <= _STRUCTURED.chunk_size for doc in docs)

    def test_parser_failure_falls_back_to_plain_pymupdf_text(self):
        loaded_page = Document(page_content=_sentences("Fallback", 60), metadata={"page": 0, "source": "x.pdf"})
        with (
            patch("pymupdf4llm.to_markdown", side_effect=RuntimeError("layout failed")),
            patch("langchain_community.document_loaders.PyMuPDFLoader") as loader,
        ):
            loader.return_value.load.return_value = [loaded_page]
            pdf_loader = Pymupdf4llmLoader("fake.pdf", chunk_size=1000, chunk_overlap=200)
            docs = pdf_loader.load_chunks()

        assert pdf_loader.used_fallback
        assert len(docs) > 1
        assert all(len(doc.page_content) <= _STRUCTURED.chunk_size for doc in docs)
        assert all(doc.metadata["page"] == 0 for doc in docs)

    def test_missing_pymupdf4llm_fails_instead_of_falling_back(self):
        with (
            patch.dict("sys.modules", {"pymupdf4llm": None}),
            patch("langchain_community.document_loaders.PyMuPDFLoader") as loader,
            pytest.raises(ImportError),
        ):
            Pymupdf4llmLoader("fake.pdf", chunk_size=1000, chunk_overlap=200).load_chunks()

        loader.assert_not_called()

    def test_scanned_pdf_without_text_yields_no_chunks(self):
        assert self._extract(["", "\n\n"]) == []

    def test_overlap_must_be_smaller_than_chunk_size(self):
        with pytest.raises(ValueError):
            Pymupdf4llmLoader("fake.pdf", chunk_size=100, chunk_overlap=100)

    def test_real_pdf_is_chunked_by_section(self, tmp_path):
        import pymupdf

        path = tmp_path / "two_pages.pdf"
        pdf = pymupdf.open()
        for page_number in range(2):
            page = pdf.new_page()
            top = 72
            if page_number == 0:
                page.insert_text((72, top), "1 Introduction", fontsize=20, fontname="hebo")
                top += 40
            page.insert_textbox(
                pymupdf.Rect(72, top, 520, 780), _sentences(f"Page{page_number}", 40), fontsize=11,
            )
        pdf.save(path)
        pdf.close()

        docs = SiloService.extract_documents_from_file(str(path), ".pdf", indexing=_STRUCTURED)

        assert {doc.metadata["page"] for doc in docs} == {1, 2}
        assert all(doc.metadata.get("section") == "1 Introduction" for doc in docs)
        assert all(len(doc.page_content) <= _STRUCTURED.chunk_size for doc in docs)

    def test_section_prefix_can_be_disabled(self):
        indexing = IndexingConfig(1000, 200, "pymupdf4llm", {"section_prefix": False})
        docs = self._extract([f"# Scope\n\n{_sentences('Scope', 5)}"], indexing=indexing)

        assert docs[0].page_content.startswith("Scope sentence number 0")
        assert docs[0].metadata["section"] == "Scope"

    def test_headers_and_footers_are_removed_unless_disabled(self):
        self._extract([_sentences("Body", 3)])
        assert self.last_to_markdown_kwargs["header"] is False
        assert self.last_to_markdown_kwargs["footer"] is False

        indexing = IndexingConfig(1000, 200, "pymupdf4llm", {"remove_headers_footers": False})
        self._extract([_sentences("Body", 3)], indexing=indexing)
        assert self.last_to_markdown_kwargs["header"] is True
        assert self.last_to_markdown_kwargs["footer"] is True


class TestPdfLoaderSelection:
    """The silo's IndexingConfig picks the PDF loader and the chunk size for every file type."""

    def test_default_config_uses_the_fast_pymupdf_loader(self):
        page = Document(page_content=_sentences("Page", 100), metadata={"page": 0, "source": "x.pdf"})
        with (
            patch("pymupdf4llm.to_markdown") as to_markdown,
            patch("langchain_community.document_loaders.PyMuPDFLoader") as loader,
        ):
            loader.return_value.load.return_value = [page]
            docs = SiloService.extract_documents_from_file("fake.pdf", ".pdf")

        to_markdown.assert_not_called()
        assert len(docs) > 1
        assert all(len(doc.page_content) <= CHUNK_SIZE for doc in docs)
        assert all(doc.metadata["page"] == 1 for doc in docs)
        assert all("section" not in doc.metadata for doc in docs)

    def test_chunk_size_of_the_silo_applies_to_text_files(self):
        source = Document(page_content=_sentences("Text", 60), metadata={})
        with patch("langchain_community.document_loaders.TextLoader") as loader:
            loader.return_value.load.return_value = [source]
            small = SiloService.extract_documents_from_file("f.txt", ".txt", indexing=IndexingConfig(500, 100))
            large = SiloService.extract_documents_from_file("f.txt", ".txt", indexing=IndexingConfig(3000, 300))

        assert all(len(doc.page_content) <= 500 for doc in small)
        assert len(small) > len(large)

    def test_indexing_pass_uses_the_silo_chunk_size(self):
        content = [{"content": _sentences("Raw", 60), "metadata": {}}]

        small = SiloService._create_documents_for_indexing(1, content, IndexingConfig(500, 100))
        default = SiloService._create_documents_for_indexing(1, content)

        assert all(len(doc.page_content) <= 500 for doc in small)
        assert all(len(doc.page_content) <= CHUNK_SIZE for doc in default)
        assert len(small) > len(default)

    def test_text_file_keeps_existing_loader_and_split_behavior(self):
        source = Document(page_content="A short text file with readable content.", metadata={})
        with patch("langchain_community.document_loaders.TextLoader") as loader:
            loader.return_value.load.return_value = [source]
            docs = SiloService.extract_documents_from_file("fake.txt", ".txt")

        assert len(docs) == 1
        assert docs[0].page_content == source.page_content
        loader.assert_called_once_with("fake.txt", encoding="utf-8")


def test_chunk_size_constant_is_positive():
    assert CHUNK_SIZE > 0


def test_chunk_overlap_less_than_chunk_size():
    assert CHUNK_OVERLAP < CHUNK_SIZE
