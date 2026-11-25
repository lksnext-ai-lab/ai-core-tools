"""``pymupdf4llm`` PDF loader: section-aware chunks, slower but higher quality.

pymupdf4llm (layout mode) rebuilds the reading order (multi-column pages), turns
headings into Markdown ``#`` lines and tables into Markdown tables, and drops
page headers/footers (option ``remove_headers_footers``). This loader then:

1. groups the text into sections following the heading hierarchy, which carries
   across page breaks;
2. splits each section with a ``RecursiveCharacterTextSplitter`` (size + overlap),
   so a chunk never mixes two sections and never exceeds ``chunk_size``;
3. prefixes every chunk with its section path (``[1 Intro > 1.2 Scope]``, option
   ``section_prefix``) so the heading context reaches the embedding, and records
   ``page`` (0-based, page where the chunk starts) and ``section`` in the metadata.

If the layout parser raises on a PDF, that PDF goes through the fast ``pymupdf``
loader instead (same size/overlap). A missing ``pymupdf4llm`` install raises.
"""
from __future__ import annotations

import bisect
import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from tools.document_loaders.pymupdf_loader import load_pymupdf_chunks
from utils.logger import get_logger

logger = get_logger(__name__)

SECTION_PATH_SEPARATOR = " > "
# The section prefix is capped (and never above a quarter of chunk_size) so a
# deep or very long heading path cannot eat the chunk budget; the most specific
# (last) headings are kept.
_MAX_SECTION_PREFIX_CHARS = 200
_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_BOLD_RE = re.compile(r"\*\*")
_ITALIC_RE = re.compile(r"(?<![\w_])_(?=\S)([^_\n]+?)(?<=\S)_(?![\w_])")
_STRIKE_RE = re.compile(r"~~")
_HTML_INLINE_RE = re.compile(r"</?(?:u|b|i|em|strong|mark|sup|sub|span)\b[^>]*>", re.IGNORECASE)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)  # e.g. "<!-- Start of picture text -->"
_HTML_BREAK_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_LEADER_RE = re.compile(r"(?:\.\s?){5,}|_{5,}")  # TOC dot leaders, form blanks
_PICTURE_RE = re.compile(r"^.*==> picture \[.*\] intentionally omitted <==.*$", re.MULTILINE)
_EMPTY_TABLE_ROW_RE = re.compile(r"^\|[\s|]*\|$")
_SPACES_RE = re.compile(r"[ \t]{2,}")


def _strip_inline_markup(text: str) -> str:
    """Remove Markdown/HTML emphasis that pymupdf4llm adds; it is noise for embeddings.

    pymupdf4llm writes bold as ``**`` and italic as ``_x_``; ``__`` is left alone
    so identifiers such as ``__init__`` survive.
    """
    text = _HTML_BREAK_RE.sub(" ", text)
    text = _HTML_INLINE_RE.sub("", text)
    text = _BOLD_RE.sub("", text)
    text = _ITALIC_RE.sub(r"\1", text)
    text = _STRIKE_RE.sub("", text)
    text = _LEADER_RE.sub(" ", text)
    return _SPACES_RE.sub(" ", text)


def _clean_body(text: str) -> str:
    text = _PICTURE_RE.sub("", _HTML_COMMENT_RE.sub("", text))
    lines = [_strip_inline_markup(line).rstrip() for line in text.split("\n")]
    lines = [line for line in lines if not _EMPTY_TABLE_ROW_RE.match(line.strip())]
    # Collapse the blank-line runs left by removed lines.
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


@dataclass
class _Section:
    path: tuple[str, ...]
    # (page_number, raw markdown) in reading order; a section can span pages.
    parts: list[tuple[int, str]] = field(default_factory=list)

    def add(self, page_number: int, line: str) -> None:
        if self.parts and self.parts[-1][0] == page_number:
            self.parts[-1] = (page_number, f"{self.parts[-1][1]}\n{line}")
        else:
            self.parts.append((page_number, line))


def _sections_from_pages(pages: list[str]) -> list[_Section]:
    """Group page Markdown into sections by heading, keeping the heading hierarchy."""
    sections: list[_Section] = []
    stack: list[tuple[int, str]] = []
    current = _Section(path=())
    for page_number, page_text in enumerate(pages):
        for line in page_text.split("\n"):
            match = _HEADING_RE.match(line.strip())
            title = _strip_inline_markup(match.group(2)).strip() if match else ""
            if not title:
                current.add(page_number, line)
                continue
            sections.append(current)
            level = len(match.group(1))
            stack = [entry for entry in stack if entry[0] < level] + [(level, title)]
            current = _Section(path=tuple(entry[1] for entry in stack))
    sections.append(current)
    return sections


class Pymupdf4llmLoader(BaseLoader):
    """Load a PDF as section-aware chunks; see the module docstring."""

    def __init__(
        self,
        file_path: str,
        chunk_size: int,
        chunk_overlap: int,
        *,
        section_prefix: bool = True,
        remove_headers_footers: bool = True,
    ):
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        self.file_path = file_path
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.section_prefix = section_prefix
        self.remove_headers_footers = remove_headers_footers
        self.used_fallback = False
        self._splitters: dict[int, RecursiveCharacterTextSplitter] = {}

    def lazy_load(self) -> Iterator[Document]:
        """Yield one unsplit Document per section (BaseLoader contract)."""
        pages = self._markdown_pages()
        if pages is None:
            from langchain_community.document_loaders import PyMuPDFLoader

            yield from PyMuPDFLoader(self.file_path).lazy_load()
            return
        for section in _sections_from_pages(pages):
            text = _clean_body("\n\n".join(part for _, part in section.parts))
            if text:
                yield Document(page_content=text, metadata=self._metadata(section, section.parts[0][0], len(pages)))

    def load_chunks(self) -> list[Document]:
        """Return the final chunks, each at most ``chunk_size`` characters."""
        pages = self._markdown_pages()
        if pages is None:
            return load_pymupdf_chunks(self.file_path, self.chunk_size, self.chunk_overlap)

        chunks: list[Document] = []
        for section in _sections_from_pages(pages):
            chunks.extend(self._chunk_section(section, len(pages)))
        return chunks

    def _markdown_pages(self) -> list[str] | None:
        # Outside the try on purpose: a missing or mismatched pymupdf4llm/pymupdf
        # install is a deployment error and must fail loudly, not silently index
        # every PDF through the fallback. Deferred because it loads the layout model.
        import pymupdf4llm

        try:
            pages = pymupdf4llm.to_markdown(
                self.file_path,
                page_chunks=True,
                header=not self.remove_headers_footers,
                footer=not self.remove_headers_footers,
                use_ocr=False,
                write_images=False,
                embed_images=False,
                show_progress=False,
            )
            return [page.get("text", "") for page in pages]
        except Exception as exc:  # noqa: BLE001 - any parser failure -> plain text extraction
            logger.warning(
                "pymupdf4llm failed on %s (%s); falling back to plain PyMuPDF text",
                self.file_path, type(exc).__name__,
            )
            self.used_fallback = True
            return None

    def _chunk_section(self, section: _Section, total_pages: int) -> list[Document]:
        # Clean each page part on its own so the page offsets stay exact.
        texts: list[str] = []
        offsets: list[int] = []
        pages: list[int] = []
        position = 0
        for page_number, raw in section.parts:
            cleaned = _clean_body(raw)
            if not cleaned:
                continue
            if texts:
                position += 2  # the "\n\n" joining the parts
            offsets.append(position)
            pages.append(page_number)
            texts.append(cleaned)
            position += len(cleaned)
        if not texts:
            return []
        text = "\n\n".join(texts)

        prefix = self._section_prefix(section.path)
        budget = self.chunk_size - len(prefix)
        splitter = self._splitter(budget)
        overlap = self._overlap_for(budget)
        documents: list[Document] = []
        start = 0
        previous_length = 0
        for chunk in splitter.split_text(text):
            # Same offset walk as TextSplitter(add_start_index=True): a chunk can
            # only start after the previous one minus the overlap, which keeps
            # repeated passages from mapping back to their first occurrence.
            search_from = max(0, start + previous_length - overlap)
            found = text.find(chunk, search_from)
            start = found if found >= 0 else search_from
            previous_length = len(chunk)
            page_number = pages[bisect.bisect_right(offsets, start) - 1]
            documents.append(Document(
                page_content=f"{prefix}{chunk}",
                metadata=self._metadata(section, page_number, total_pages),
            ))
        return documents

    def _splitter(self, chunk_size: int) -> RecursiveCharacterTextSplitter:
        if chunk_size not in self._splitters:
            self._splitters[chunk_size] = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=self._overlap_for(chunk_size),
                separators=_SEPARATORS,
                keep_separator="end",
            )
        return self._splitters[chunk_size]

    def _overlap_for(self, chunk_size: int) -> int:
        return min(self.chunk_overlap, chunk_size // 2)

    def _section_prefix(self, path: tuple[str, ...]) -> str:
        if not path or not self.section_prefix:
            return ""
        max_label = min(_MAX_SECTION_PREFIX_CHARS, self.chunk_size // 4) - 4  # "[", "]", "\n\n"
        if max_label < 1:
            return ""
        label = SECTION_PATH_SEPARATOR.join(path)
        if len(label) > max_label:
            label = "…" + label[-(max_label - 1):] if max_label > 1 else "…"
        return f"[{label}]\n\n"

    @staticmethod
    def _metadata(section: _Section, page_number: int, total_pages: int) -> dict:
        metadata: dict = {"page": page_number, "total_pages": total_pages}
        if section.path:
            metadata["section"] = SECTION_PATH_SEPARATOR.join(section.path)
        return metadata
