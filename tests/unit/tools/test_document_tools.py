"""Unit tests for ``tools.DocumentTools.extract_text_from_document``.

Attaching a .docx to a chat used to hand the agent the literal string "Document
processing not implemented" as the file's content. The extractor must now return
the document's text, and — for formats it cannot read — a notice that plainly
says the file was not read, since the caller stores the return value as content.

Tests verify:
- A .docx is turned into its text.
- An empty .docx yields a notice, not an empty string.
- A format with no extractor (.xlsx, legacy .doc) yields a notice.
- An unreadable/corrupt file yields an error notice instead of raising.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from tools.DocumentTools import extract_text_from_document


_DOCUMENT_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>{paragraphs}</w:body>
</w:document>
"""

_PARAGRAPH_XML = "<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"


def _write_docx(path: Path, *paragraphs: str) -> Path:
    """Write a minimal WordprocessingML .docx (a zip holding word/document.xml)."""
    body = "".join(_PARAGRAPH_XML.format(text=text) for text in paragraphs)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", _DOCUMENT_XML.format(paragraphs=body))
    return path


class TestExtractTextFromDocument:
    def test_extracts_text_from_docx(self, tmp_path):
        docx = _write_docx(
            tmp_path / "report.docx",
            "Quarterly report",
            "Revenue grew by 12%.",
        )

        result = extract_text_from_document(str(docx), "report.docx")

        assert "Quarterly report" in result
        assert "Revenue grew by 12%." in result

    def test_empty_docx_returns_notice(self, tmp_path):
        docx = _write_docx(tmp_path / "empty.docx")

        result = extract_text_from_document(str(docx), "empty.docx")

        assert "no extractable text" in result

    def test_unsupported_format_returns_notice(self, tmp_path):
        spreadsheet = tmp_path / "budget.xlsx"
        spreadsheet.write_bytes(b"not really a spreadsheet")

        result = extract_text_from_document(str(spreadsheet), "budget.xlsx")

        assert "not supported" in result
        assert ".xlsx" in result

    def test_legacy_doc_returns_notice(self, tmp_path):
        legacy = tmp_path / "old.doc"
        legacy.write_bytes(b"\xd0\xcf\x11\xe0")  # OLE2 magic

        result = extract_text_from_document(str(legacy), "old.doc")

        assert "not supported" in result

    def test_corrupt_docx_returns_error_notice(self, tmp_path):
        corrupt = tmp_path / "broken.docx"
        corrupt.write_bytes(b"this is not a zip archive")

        result = extract_text_from_document(str(corrupt), "broken.docx")

        assert result.startswith("Error processing document")
