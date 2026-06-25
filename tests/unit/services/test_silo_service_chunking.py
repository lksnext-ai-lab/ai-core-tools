"""Unit tests for chunking in SiloService: extract_documents_from_file (FR-10) and index_single_content (FR-11).

All external dependencies are mocked — no DB, filesystem, or vector store access.
"""
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from services.silo_service import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    SiloService,
)


def _make_silo(silo_id: int = 7) -> MagicMock:
    silo = MagicMock()
    silo.silo_id = silo_id
    silo.embedding_service_id = 1
    silo.embedding_service = MagicMock(name="mock-embedding-service")
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


class TestExtractDocumentsFromFileSplitter:
    """AC-16: extract_documents_from_file must use RecursiveCharacterTextSplitter."""

    def _make_page_doc(self, text: str, page: int = 0) -> Document:
        return Document(page_content=text, metadata={"page": page, "source": "/tmp/test.pdf"})

    def test_uses_recursive_splitter_not_character_splitter(self):
        """RecursiveCharacterTextSplitter splits at paragraph boundaries before the hard limit.

        A text with a clear \\n\\n boundary before CHUNK_SIZE must be split there,
        not at the character limit — which is what CharacterTextSplitter would do.
        """
        para_a = "Alpha " * 67  # ~402 chars
        para_b = "Beta  " * 117  # ~702 chars
        text = para_a.strip() + "\n\n" + para_b.strip()
        assert len(text) > CHUNK_SIZE

        page_doc = self._make_page_doc(text, page=0)

        with patch("langchain_community.document_loaders.PyMuPDFLoader") as MockLoader:
            mock_loader_instance = MagicMock()
            mock_loader_instance.load.return_value = [page_doc]
            MockLoader.return_value = mock_loader_instance

            docs = SiloService.extract_documents_from_file(
                file_path="/tmp/fake.pdf",
                file_extension=".pdf",
                base_metadata={"resource_id": 1, "silo_id": 3},
            )

        assert len(docs) >= 2, (
            f"Expected >=2 chunks for a {len(text)}-char text, got {len(docs)}"
        )
        assert len(docs[0].page_content) < CHUNK_SIZE, (
            "First chunk must split at the paragraph boundary, not at the character limit"
        )
        assert "Beta" not in docs[0].page_content

    def test_paragraph_boundary_is_preferred_split_point(self):
        """RecursiveCharacterTextSplitter splits at \\n\\n before splitting mid-sentence."""
        para_a = ("Sentence one about the topic. " * 14).rstrip()  # ~420 chars
        para_b = ("Sentence two about the topic. " * 24).rstrip()  # ~720 chars
        text = para_a + "\n\n" + para_b
        assert len(text) > CHUNK_SIZE

        page_doc = self._make_page_doc(text)

        with patch("langchain_community.document_loaders.PyMuPDFLoader") as MockLoader:
            mock_loader_instance = MagicMock()
            mock_loader_instance.load.return_value = [page_doc]
            MockLoader.return_value = mock_loader_instance

            docs = SiloService.extract_documents_from_file(
                file_path="/tmp/fake.pdf",
                file_extension=".pdf",
            )

        assert len(docs) >= 2
        assert len(docs[0].page_content) <= CHUNK_SIZE + CHUNK_OVERLAP, (
            f"First chunk too large: {len(docs[0].page_content)} chars"
        )

    def test_base_metadata_attached_to_every_chunk(self):
        """base_metadata keys must appear on every chunk produced by extract_documents_from_file."""
        text = ("Word " * 300).strip()
        assert len(text) > CHUNK_SIZE

        page_doc = self._make_page_doc(text)

        with patch("langchain_community.document_loaders.PyMuPDFLoader") as MockLoader:
            mock_loader_instance = MagicMock()
            mock_loader_instance.load.return_value = [page_doc]
            MockLoader.return_value = mock_loader_instance

            base_meta = {"resource_id": 42, "silo_id": 9, "name": "test.pdf"}
            docs = SiloService.extract_documents_from_file(
                file_path="/tmp/fake.pdf",
                file_extension=".pdf",
                base_metadata=base_meta,
            )

        assert len(docs) >= 2
        for i, doc in enumerate(docs):
            for key, value in base_meta.items():
                assert key in doc.metadata, f"Chunk {i} missing '{key}' from base_metadata"
                assert doc.metadata[key] == value, (
                    f"Chunk {i}: '{key}' expected {value!r}, got {doc.metadata[key]!r}"
                )

    def test_short_file_produces_single_chunk(self):
        """A file whose text fits within CHUNK_SIZE must produce exactly one chunk."""
        text = "Short document content."
        assert len(text) < CHUNK_SIZE

        page_doc = self._make_page_doc(text)

        with patch("langchain_community.document_loaders.PyMuPDFLoader") as MockLoader:
            mock_loader_instance = MagicMock()
            mock_loader_instance.load.return_value = [page_doc]
            MockLoader.return_value = mock_loader_instance

            docs = SiloService.extract_documents_from_file(
                file_path="/tmp/fake.pdf",
                file_extension=".pdf",
                base_metadata={"resource_id": 1, "silo_id": 1},
            )

        assert len(docs) == 1
        assert docs[0].page_content == text

    def test_page_number_offset_applied(self):
        """The 'page' metadata value from PDFs must be incremented by 1 (1-based)."""
        text = "Content on page zero."
        page_doc = self._make_page_doc(text, page=0)

        with patch("langchain_community.document_loaders.PyMuPDFLoader") as MockLoader:
            mock_loader_instance = MagicMock()
            mock_loader_instance.load.return_value = [page_doc]
            MockLoader.return_value = mock_loader_instance

            docs = SiloService.extract_documents_from_file(
                file_path="/tmp/fake.pdf",
                file_extension=".pdf",
            )

        assert len(docs) == 1
        assert docs[0].metadata["page"] == 1


def test_chunk_size_constant_is_positive():
    assert CHUNK_SIZE > 0


def test_chunk_overlap_less_than_chunk_size():
    assert CHUNK_OVERLAP < CHUNK_SIZE
