"""Structure-aware PDF loader with a raw PyMuPDF fallback."""
from typing import Any, Iterator, Optional
import re

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document


def _pdf_line_text(line: dict) -> str:
    return "".join(span.get("text", "") for span in line.get("spans", [])).strip()


def _pdf_block_paragraphs(block: dict) -> list[str]:
    """Rebuild paragraphs from text lines, using vertical gaps within a PDF block."""
    paragraphs: list[str] = []
    current_lines: list[str] = []
    previous_bbox = None

    for line in block.get("lines", []):
        text = _pdf_line_text(line)
        if not text:
            continue

        bbox = line.get("bbox")
        if current_lines and bbox and previous_bbox:
            line_height = max(1.0, previous_bbox[3] - previous_bbox[1])
            vertical_gap = bbox[1] - previous_bbox[3]
            if vertical_gap > max(2.0, line_height * 0.45):
                paragraphs.append(" ".join(current_lines))
                current_lines = []

        if current_lines and current_lines[-1].endswith("-") and text[:1].islower():
            current_lines[-1] = current_lines[-1][:-1] + text
        else:
            current_lines.append(text)
        previous_bbox = bbox

    if current_lines:
        paragraphs.append(" ".join(current_lines))
    return paragraphs


def _is_pdf_heading(block: dict, text: str, median_font_size: float) -> bool:
    """Use short, prominent PDF text blocks as section headings."""
    if len(text) > 180 or re.search(r"[.!?]$", text):
        return False

    spans = [
        span
        for line in block.get("lines", [])
        for span in line.get("spans", [])
        if span.get("text", "").strip()
    ]
    prominent = any(
        span.get("size", 0) >= median_font_size * 1.15
        or span.get("flags", 0) & 16
        for span in spans
    )
    letters = [char for char in text if char.isalpha()]
    is_uppercase = bool(letters) and all(char.isupper() for char in letters)
    return prominent or (len(text) <= 100 and is_uppercase)


class PdfLoader(BaseLoader):
    """Load PDF text as page-aware, structure-preserving LangChain documents."""

    def __init__(self, file_path: str, chunk_size: int):
        self.file_path = file_path
        self.chunk_size = chunk_size
        self.structured = False

    def lazy_load(self) -> Iterator[Document]:
        documents = self._load_structured_documents()
        if documents is not None:
            self.structured = True
            yield from documents
            return

        from langchain_community.document_loaders import PyMuPDFLoader

        yield from PyMuPDFLoader(self.file_path).load()

    def _load_structured_documents(self) -> Optional[list[Document]]:
        import fitz

        documents: list[Document] = []
        found_text_blocks = False
        with fitz.open(self.file_path) as pdf:
            for page_number, page in enumerate(pdf):
                page_data = page.get_text("dict", sort=True)
                blocks = page_data.get("blocks")
                if not isinstance(blocks, list):
                    return None

                text_blocks = [
                    (block_number, block)
                    for block_number, block in enumerate(blocks)
                    if block.get("type") == 0 and block.get("lines")
                ]
                if not text_blocks:
                    continue
                found_text_blocks = True

                font_sizes = [
                    span.get("size", 0)
                    for _, block in text_blocks
                    for line in block.get("lines", [])
                    for span in line.get("spans", [])
                    if span.get("text", "").strip() and span.get("size", 0) > 0
                ]
                median_font_size = (
                    sorted(font_sizes)[len(font_sizes) // 2] if font_sizes else 0
                )
                current_section = None
                current_text: list[str] = []
                current_blocks: list[int] = []

                def flush_chunk() -> None:
                    if not current_text:
                        return
                    metadata: dict[str, Any] = {
                        "page": page_number,
                        "pdf_blocks": sorted(set(current_blocks)),
                    }
                    if current_section:
                        metadata["section"] = current_section
                    documents.append(Document(
                        page_content="\n\n".join(current_text),
                        metadata=metadata,
                    ))
                    current_text.clear()
                    current_blocks.clear()

                for block_number, block in text_blocks:
                    for paragraph in _pdf_block_paragraphs(block):
                        if not paragraph:
                            continue

                        if _is_pdf_heading(block, paragraph, median_font_size):
                            flush_chunk()
                            current_section = paragraph

                        if len(paragraph) > self.chunk_size:
                            flush_chunk()
                            current_text.append(paragraph)
                            current_blocks.append(block_number)
                            flush_chunk()
                            continue

                        candidate = "\n\n".join([*current_text, paragraph])
                        if len(candidate) > self.chunk_size:
                            flush_chunk()
                        current_text.append(paragraph)
                        current_blocks.append(block_number)

                flush_chunk()

        return documents if found_text_blocks else None
