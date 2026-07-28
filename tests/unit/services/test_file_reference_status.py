"""Unit tests for ``FileReference`` placeholder detection.

``_get_processing_status`` and ``_has_extractable_content`` decide whether an
attachment was really read. They tell a placeholder apart from real content by
looking at how the notice starts, because the notices this service produces are
always prefixes ("Document file: …", "File: …", "Error processing …").

The check used to be a *substring* match, which is a trap: extracted document
text can legitimately contain "File:" in its body, and that would report a
successfully-read attachment as unread.

Tests verify:
- Real extracted text is "ready", even when it contains a placeholder phrase.
- Each kind of notice is recognised as a placeholder.
"""

from __future__ import annotations

from services.file_management_service import FileReference


def _reference(content: str, file_type: str = "document") -> FileReference:
    return FileReference(
        file_id="f-1",
        filename="report.docx",
        file_type=file_type,
        content=content,
    )


class TestPlaceholderDetection:
    def test_extracted_text_is_ready(self):
        ref = _reference("Quarterly report\n\nRevenue grew by 12%.")

        assert ref.has_extractable_content is True
        assert ref.processing_status == "ready"

    def test_extracted_text_containing_placeholder_phrase_is_still_ready(self):
        # The document itself talks about files — a substring match would have
        # declared this successfully-read document unread.
        ref = _reference(
            "Attachment policy\n\nFile: contract.pdf must be signed.\n"
            "Support for macros is not implemented in this template."
        )

        assert ref.has_extractable_content is True
        assert ref.processing_status == "ready"

    def test_unsupported_format_notice_is_not_content(self):
        ref = _reference(
            "Document file: budget.xlsx (text extraction is not supported for .xlsx)"
        )

        assert ref.has_extractable_content is False
        assert ref.processing_status == "uploaded"

    def test_empty_document_notice_is_not_content(self):
        ref = _reference(
            "Document file: empty.docx (no extractable text: it may be empty or "
            "contain only images)"
        )

        assert ref.has_extractable_content is False
        assert ref.processing_status == "uploaded"

    def test_error_notice_is_reported_as_error(self):
        ref = _reference("Error processing document broken.docx: the file could not be read")

        assert ref.has_extractable_content is False
        assert ref.processing_status == "error"

    def test_image_is_ready_without_text_extraction(self):
        ref = _reference(
            "Image file: chart.png (OCR processing not implemented)", file_type="image"
        )

        assert ref.processing_status == "ready"
        assert ref.has_extractable_content is False
